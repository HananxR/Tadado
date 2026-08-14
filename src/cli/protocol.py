"""Shared pipe protocol between tadado-cli and the running Tadado GUI.

Frame format: ``PROTO_HEADER`` (magic line) followed by exactly one JSON
object.  The GUI distinguishes legacy "wake" bytes from CLI requests by the
header, so pre-CLI versions simply consume the frame and answer nothing —
the client reports a "version too old" error in that case.
"""

from __future__ import annotations

import json
import time

from PySide6.QtNetwork import QLocalSocket

PROTO_HEADER = b"TADADO_CLI/1\n"
SERVER_NAME = "Tadado_Instance"
LEGACY_EXIT_CODE = 10  # a GUI is running but predates the CLI protocol


def write_message(sock, payload: dict) -> None:
    """Send header + JSON payload over a QLocalSocket connection."""
    sock.write(PROTO_HEADER + json.dumps(payload, ensure_ascii=False).encode("utf-8"))


def _try_parse(buf: bytearray) -> dict | None:
    """Parse the accumulated buffer as one JSON object."""
    try:
        obj = json.loads(buf.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    return obj if isinstance(obj, dict) else None


def read_message(sock, timeout_ms: int = 3000) -> dict | None:
    """Read one JSON message; returns None on timeout or empty stream."""
    buf = bytearray()
    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() < deadline:
        if sock.waitForReadyRead(200):
            chunk = bytes(sock.readAll())
            if chunk:
                buf += chunk
                parsed = _try_parse(buf)
                if parsed is not None:
                    return parsed
        elif sock.state() != QLocalSocket.LocalSocketState.ConnectedState:
            # Peer closed — drain whatever it left in the pipe before giving up.
            buf += bytes(sock.readAll())
            return _try_parse(buf)
    return None


def read_raw(sock, timeout_ms: int = 3000) -> bytes:
    """Read one peer frame (header + one JSON object) and return promptly.

    Returns as soon as the first chunk arrives plus one short grace poll —
    do not spin until the deadline: the peer may wait for our reply while
    the connection stays open.
    """
    buf = bytearray()
    deadline = time.monotonic() + timeout_ms / 1000.0
    while not buf and time.monotonic() < deadline:
        if sock.waitForReadyRead(200):
            buf += bytes(sock.readAll())
        elif sock.state() != QLocalSocket.LocalSocketState.ConnectedState:
            break
    # One short grace poll in case the frame arrived in two pipe chunks.
    if buf and sock.state() == QLocalSocket.LocalSocketState.ConnectedState:
        if sock.waitForReadyRead(100):
            buf += bytes(sock.readAll())
    return bytes(buf)
