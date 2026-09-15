"""PartitionController — partition lifecycle, password cache, auto-lock timer."""

from __future__ import annotations

import datetime as dt
import logging

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QInputDialog, QLineEdit, QMessageBox

from ...services.task_service import TaskService

_log = logging.getLogger("runlog")


class PartitionController(QObject):
    """Owns partition lifecycle: load, activate, lock, unlock, idle timer.

    分区入口位于**侧栏底部**（原型 ``.part-wrap``），通过注入的 *selector*
    接缝驱动，不再占用底部状态栏。

    Signals:
        partition_activated(pid): emitted after a partition is activated
    """

    partition_activated = Signal(str)  # partition_id (empty if locked)

    def __init__(
        self,
        task_service: TaskService,
        config,  # AppConfig
        splitter_stack,  # QStackedLayout — index 1 = password mask
        selector,  # PartitionSelector — rail-bottom trigger + popup
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._svc = task_service
        self._config = config
        self._splitter_stack = splitter_stack
        self._selector = selector

        # State
        self._active_id: str | None = None
        self._passwords: dict[str, str] = {}  # pid → password (empty = unlocked)
        self._auto_lock: dict[str, int] = {}  # pid → minutes
        self._in_load = False
        self._last_activity: dt.datetime | None = None

        # Idle lock timer
        self._idle_timer = QTimer(self)
        self._idle_timer.setInterval(30_000)
        self._idle_timer.timeout.connect(self._check_idle_lock)
        self._idle_timer.start()

        # Wire rail trigger → popup → activate
        self._selector.partition_chosen.connect(self.activate)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def active_id(self) -> str | None:
        return self._active_id

    @property
    def passwords(self) -> dict[str, str]:
        return self._passwords

    def notify_activity(self) -> None:
        """Reset the idle timer — call from keyboard/mouse event handlers."""
        self._last_activity = dt.datetime.now()

    def load_all(self) -> None:
        """Load partitions from DB, sync passwords, build menu, activate default."""
        self._in_load = True
        # Ensure at least one partition exists (creates "功能演示" if empty)
        self._svc.ensure_default_partition()

        partitions = self._svc.get_all_partitions()
        # Fix config if default_partition is unset or points to a deleted partition
        current_default = self._config.get("general", "default_partition", default="")
        if not current_default or current_default not in {p["id"] for p in partitions}:
            first_pid = partitions[0]["id"] if partitions else ""
            if first_pid:
                self._config.set("general", "default_partition", value=first_pid)
                self._config.save()
        name_map: dict[str, str] = {p["id"]: p["name"] for p in partitions}

        # Sync passwords + auto_lock from DB
        for p in partitions:
            pid = p["id"]
            db_pw = p.get("password", "")
            if db_pw:
                if pid not in self._passwords:
                    self._passwords[pid] = db_pw
                elif self._passwords[pid]:
                    self._passwords[pid] = db_pw
            else:
                self._passwords.pop(pid, None)
            self._auto_lock[pid] = p.get("auto_lock_minutes", 3)

        # Rebuild the rail popup — name + task count, active entry highlighted
        entries: list[dict] = []
        for p in partitions:
            pid = p["id"]
            entries.append(
                {
                    "id": pid,
                    "name": p["name"],
                    "count": self._svc.count_tasks_in_partition(pid),
                    "locked": bool(p.get("password", "")) and bool(self._passwords.get(pid, "")),
                }
            )
        self._selector.set_entries(entries, self._active_id or "")

        # Reset if current partition was deleted
        if self._active_id and self._active_id not in name_map:
            self._active_id = None

        if not self._active_id:
            activated = False
            for key in ("default_partition", "last_partition_id"):
                pid = self._config.get("general", key, default="")
                if pid and pid in name_map:
                    self.activate(pid)
                    activated = True
                    break
            if not activated:
                first = self._find_first_unlocked()
                if first:
                    self.activate(first)

        self._in_load = False

    def activate(self, pid: str) -> None:
        """Activate a partition — lock previous, update UI, emit signal."""
        prev = self._active_id
        if prev and prev != pid:
            has_pw, stored = self._svc.check_partition_password(prev)
            if has_pw:
                self._passwords[prev] = stored

        self._active_id = pid or ""
        self._config.set("general", "last_partition_id", value=self._active_id)
        self._config.save()

        if pid and self._passwords.get(pid, ""):
            self._splitter_stack.setCurrentIndex(1)  # show password mask
        else:
            self._splitter_stack.setCurrentIndex(0)

        self._update_trigger()
        self.load_all()  # refresh popup entries

        # Retroactive archive: if archive_days=0, archive all existing DONE tasks
        self._archive_done_if_needed(pid)

        self.partition_activated.emit(self._active_id)
        _log.info("Partition activated: %s", self._active_id)

    def _archive_done_if_needed(self, pid: str) -> None:
        """Archive all existing DONE tasks if partition has archive_days=0."""
        if not pid:
            return
        partitions = self._svc.get_all_partitions()
        for p in partitions:
            if p["id"] == pid and p.get("archive_days", 0) == 0:
                from ...models.task_filter import TaskFilter
                from ...models.task_status import TaskStatus
                done_tasks = self._svc.search(
                    TaskFilter(partition_id=pid, statuses={TaskStatus.DONE})
                )
                if done_tasks:
                    ids = [t.id for t in done_tasks]
                    self._svc.archive_batch(ids)
                    _log.info(
                        "PartitionController: retroactive archive %s tasks in %s (archive_days=0)",
                        len(ids), pid,
                    )
                break

    def lock(self, target_id: str) -> None:
        """Lock a partition (restore password from DB, show mask)."""
        has_pw, stored = self._svc.check_partition_password(target_id)
        if has_pw:
            self._passwords[target_id] = stored
            self._splitter_stack.setCurrentIndex(1)
            self._update_trigger()

    def unlock(self) -> bool:
        """Prompt for password and unlock active partition. Returns True on success."""
        pid = self._active_id
        if not pid:
            return False
        stored = self._passwords.get(pid, "")
        if not stored:
            return False
        pw, ok = QInputDialog.getText(
            self._selector, "解锁分区", "请输入密码：", QLineEdit.EchoMode.Password,
        )
        if not ok:
            return False
        if pw.strip() == stored:
            self._passwords[pid] = ""
            self._splitter_stack.setCurrentIndex(0)
            self.load_all()
            return True
        else:
            QMessageBox.warning(self._selector, "错误", "密码不正确")
            return False

    def has_password(self, pid: str | None = None) -> bool:
        """Check if a partition has a password set."""
        pid = pid or self._active_id or ""
        return bool(self._passwords.get(pid, ""))

    def is_unlocked(self, pid: str | None = None) -> bool:
        """Check if a password-protected partition is currently unlocked."""
        pid = pid or self._active_id or ""
        return self._passwords.get(pid, "") == ""

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _update_trigger(self, name_map: dict[str, str] | None = None) -> None:
        """Refresh the rail trigger tooltip (partition name + lock marker)."""
        pid = self._active_id or ""
        if name_map is None:
            name_map = self._svc.get_partition_name_map()
        pname = name_map.get(pid, "")
        self._selector.set_active_name(pname, bool(self._passwords.get(pid, "")))

    def _find_first_unlocked(self) -> str | None:
        parts = self._svc.get_all_partitions()
        for p in parts:
            if not self._passwords.get(p["id"], ""):
                return p["id"]
        return None

    def _check_idle_lock(self) -> None:
        mins = self._auto_lock.get(self._active_id or "", 3)
        if not mins or mins <= 0:
            return
        if self._splitter_stack.currentIndex() == 1:
            return  # already locked
        if self._last_activity is None:
            self._last_activity = dt.datetime.now()
            return
        elapsed = (dt.datetime.now() - self._last_activity).total_seconds() / 60.0
        if elapsed >= mins / 2.0:
            pid = self._active_id or ""
            has_pw, stored = self._svc.check_partition_password(pid)
            if has_pw:
                self._passwords[pid] = stored
                self._idle_timer.stop()
                self.lock(pid)
