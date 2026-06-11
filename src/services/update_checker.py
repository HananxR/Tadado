"""GitHub Release update checker with Aliyun Drive fallback for Chinese users."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from ..version import __version__, parse_version

_GITHUB_API = "https://api.github.com/repos/HananxR/Tadado/releases/latest"

# Fixed Aliyun Drive share link for Chinese users
ALIYUN_DRIVE_URL = "https://www.alipan.com/s/E2FBppaMPZj"
_ALIYUN_REMOTE_DIR = "/Tadado"

# Regex to extract version from filenames like Tadado_setup_v0.1.2.3.exe
_VERSION_RE = re.compile(r"v(\d+\.\d+\.\d+(?:\.\d+)?)")


class UpdateChecker(QObject):
    """Check for updates — Aliyun Drive first (fast for domestic users),
    GitHub Release API as fallback.

    Usage::

        checker = UpdateChecker()
        checker.check_finished.connect(on_result)
        checker.check_error.connect(on_error)
        checker.check_for_updates()
    """

    check_finished = Signal(object)  # dict | None  — update_info or None (no update)
    check_error = Signal(str)        # human-readable error message

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._nam = QNetworkAccessManager(self)
        self._reply: QNetworkReply | None = None
        self._aliyunpan_path: str | None = None
        self._aliyun_process: QProcess | None = None
        self._timeout_timer = QTimer(self)
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.timeout.connect(self._on_timeout)
        self._TIMEOUT_MS = 20_000

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_for_updates(self) -> None:
        """Initiate an async check — Aliyun Drive first, GitHub on failure.

        20-second timeout: if no result arrives, silently treat as no-update.
        """
        self._stop_timeout()
        if self._reply is not None and self._reply.isRunning():
            self._reply.abort()

        # Try Aliyun Drive first (faster for domestic users)
        self._try_aliyun_check()

    def _try_github_check(self) -> None:
        """GitHub API as fallback."""
        self._timeout_timer.start(self._TIMEOUT_MS)

        request = QNetworkRequest(QUrl(_GITHUB_API))
        request.setRawHeader(b"Accept", b"application/vnd.github+json")
        request.setRawHeader(b"User-Agent", b"Tadado-UpdateChecker")

        self._reply = self._nam.get(request)
        self._reply.finished.connect(self._on_reply_finished)

    def _stop_timeout(self) -> None:
        """Cancel the 20-second timeout timer."""
        self._timeout_timer.stop()

    def _on_timeout(self) -> None:
        """20 seconds elapsed — silently treat as no update."""
        if self._reply is not None and self._reply.isRunning():
            self._reply.abort()
        if self._aliyun_process is not None:
            self._aliyun_process.kill()
        self.check_finished.emit(None)

    def cancel(self) -> None:
        """Abort any in-flight request."""
        self._stop_timeout()
        if self._reply is not None and self._reply.isRunning():
            self._reply.abort()
        if self._aliyun_process is not None:
            self._aliyun_process.kill()

    # ------------------------------------------------------------------
    # GitHub API path
    # ------------------------------------------------------------------

    def _on_reply_finished(self) -> None:
        reply = self._reply
        if reply is None:
            return

        self._stop_timeout()
        reply.deleteLater()
        self._reply = None

        err = reply.error()
        if err != QNetworkReply.NetworkError.NoError:
            # GitHub unreachable — Aliyun was already tried first, give up
            self.check_finished.emit(None)
            return

        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        body = bytes(reply.readAll()).decode("utf-8", errors="replace")

        if status == 403 and "rate limit" in body.lower():
            self.check_error.emit("GitHub API 请求频率限制，请稍后再试")
            return
        if status == 404:
            self.check_finished.emit(None)  # no GitHub releases yet — not an error
            return
        if status != 200:
            self.check_error.emit(f"GitHub API 返回异常状态码: {status}")
            return

        try:
            data = json.loads(body)
            info = self._parse_release(data)
            if info is None:
                self.check_finished.emit(None)
            else:
                info["source"] = "github"
                self.check_finished.emit(info)
        except (json.JSONDecodeError, KeyError) as exc:
            self.check_error.emit(f"GitHub API 返回数据解析失败: {exc}")

    # ------------------------------------------------------------------
    # Aliyun Drive primary check (via local aliyunpan CLI)
    # ------------------------------------------------------------------

    def _try_aliyun_check(self) -> None:
        """Locate aliyunpan CLI and query the cloud folder for latest version.
        Falls back to GitHub if the CLI is unavailable or fails."""
        cli_path = self._find_aliyunpan()
        if cli_path is None:
            self._try_github_check()  # fallback
            return

        self._aliyunpan_path = cli_path
        # Build the command: aliyunpan ls /Tadado/ --drive-id <resource>
        self._aliyun_process = QProcess(self)
        self._aliyun_process.setProgram(cli_path)
        self._aliyun_process.setArguments(["ls", _ALIYUN_REMOTE_DIR])
        self._aliyun_process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        self._aliyun_process.finished.connect(self._on_aliyun_finished)
        self._aliyun_process.start()

    def _on_aliyun_finished(self) -> None:
        process = self._aliyun_process
        if process is None:
            return
        self._stop_timeout()
        process.deleteLater()
        self._aliyun_process = None

        if process.exitStatus() != QProcess.ExitStatus.NormalExit or process.exitCode() != 0:
            self._try_github_check()  # fallback
            return

        output = bytes(process.readAllStandardOutput()).decode("utf-8", errors="replace")
        latest_version = self._parse_aliyun_ls(output)
        if latest_version is None:
            self._try_github_check()  # fallback
            return

        current = __version__
        try:
            current_tuple = parse_version(current)
            latest_tuple = parse_version(latest_version)
        except (ValueError, TypeError):
            self.check_error.emit(f"版本号解析失败（当前: {current}，云盘: {latest_version}）")
            return

        if latest_tuple <= current_tuple:
            self.check_finished.emit(None)  # already latest
        else:
            self.check_finished.emit({
                "latest_version": f"v{latest_version}",
                "current_version": f"v{current}",
                "release_url": ALIYUN_DRIVE_URL,
                "release_notes": "",
                "published_at": "",
                "is_newer": True,
                "assets": [],
                "aliyun_drive": ALIYUN_DRIVE_URL,
                "source": "aliyunpan",
                "download_hint": "推荐通过 ☁️ 阿里云盘下载更新",
            })

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _find_aliyunpan(self) -> str | None:
        """Locate aliyunpan.exe — PATH first, then known install directories."""
        # 1) Check PATH
        for d in os.environ.get("PATH", "").split(os.pathsep):
            p = Path(d) / "aliyunpan.exe"
            if p.is_file():
                return str(p)

        # 2) Scan known locations
        candidates = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "aliyunpan" / "aliyunpan.exe",
            Path(os.environ.get("ProgramFiles", "")) / "aliyunpan" / "aliyunpan.exe",
            Path(os.environ.get("ProgramFiles(x86)", "")) / "aliyunpan" / "aliyunpan.exe",
        ]
        # D:\aliyunpan-* (versioned installs)
        for base in (Path("D:/"), Path(os.environ.get("USERPROFILE", ""))):
            try:
                for d in base.glob("aliyunpan-*"):
                    if d.is_dir():
                        candidates.append(d / "aliyunpan.exe")
            except OSError:
                pass

        for p in candidates:
            if p.is_file():
                return str(p)

        return None

    def _parse_aliyun_ls(self, output: str) -> str | None:
        """Extract the latest version from aliyunpan ls output.

        Scans for filenames like ``Tadado_setup_v0.1.1.exe`` and returns
        the greatest version string (e.g. ``"0.1.1"``).
        """
        versions: list[tuple[int, int, int]] = []
        for match in _VERSION_RE.finditer(output):
            try:
                versions.append(parse_version(match.group(0)))
            except ValueError:
                continue
        if not versions:
            return None
        versions.sort(reverse=True)
        return ".".join(str(x) for x in versions[0])

    # ------------------------------------------------------------------
    # GitHub response parsing
    # ------------------------------------------------------------------

    def _parse_release(self, data: dict) -> dict | None:
        """Parse the GitHub API response and return update_info or None."""
        current = __version__
        latest_tag: str = data.get("tag_name", "")
        if not latest_tag:
            return None

        try:
            current_tuple = parse_version(current)
            latest_tuple = parse_version(latest_tag)
        except (ValueError, TypeError):
            return None

        if latest_tuple <= current_tuple:
            return None

        body: str = data.get("body", "") or ""
        if len(body) > 500:
            body = body[:500] + "\n\n…"

        return {
            "latest_version": latest_tag,
            "current_version": f"v{current}",
            "release_url": data.get("html_url", ""),
            "release_notes": body,
            "published_at": data.get("published_at", ""),
            "is_newer": True,
            "assets": [
                {"name": a.get("name", ""), "url": a.get("browser_download_url", "")}
                for a in data.get("assets", [])
            ],
            "aliyun_drive": ALIYUN_DRIVE_URL,
            "source": "github",
            "download_hint": "",
        }
