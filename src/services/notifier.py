"""Tray notification handler — daily digest summary via tray message."""

from __future__ import annotations

from datetime import datetime

from ..config import AppConfig
from ..models.repository import TaskRepository
from ..utils.signal_bus import get_signal_bus


class TaskNotifier:
    """Listens to daily_digest and shows a single merged tray notification
    summarizing today's due tasks, respecting quiet hours."""

    def __init__(self, tray_manager, config: AppConfig, repository: TaskRepository) -> None:
        self._tray = tray_manager
        self._config = config
        self._repository = repository
        self._signal_bus = get_signal_bus()
        self._signal_bus.daily_digest.connect(self._on_daily_digest)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_daily_digest(self) -> None:
        """Called once per day at the configured digest time."""
        if not self._config.reminders_enabled:
            return
        if self._in_quiet_hours():
            return

        pid = self._config.get("general", "last_partition_id", default="") or None
        due_today = self._repository.get_due_today(partition_id=pid)
        overdue = self._repository.get_overdue(partition_id=pid)

        total = len(due_today) + len(overdue)
        if total == 0:
            return

        parts: list[str] = []
        if overdue:
            parts.append(f"逾期 {len(overdue)} 项")
        if due_today:
            parts.append(f"今日到期 {len(due_today)} 项")

        title = "Tadado 每日摘要"
        msg = "，".join(parts)

        # Show up to 3 task titles
        sample = [t.title for t in (overdue + due_today)[:3]]
        if sample:
            msg += "\n" + "、".join(sample)
        if total > 3:
            msg += f"\n…等 {total} 项"

        self._tray.show_message(title, msg)

    # ------------------------------------------------------------------
    # Quiet hours
    # ------------------------------------------------------------------

    def _in_quiet_hours(self) -> bool:
        try:
            start_str = self._config.get("reminders", "quiet_hours_start") or "22:00"
            end_str = self._config.get("reminders", "quiet_hours_end") or "08:00"
            start_h, start_m = map(int, start_str.split(":"))
            end_h, end_m = map(int, end_str.split(":"))
        except (ValueError, AttributeError):
            return False

        now = datetime.now().time()
        start = datetime.strptime(f"{start_h:02d}:{start_m:02d}", "%H:%M").time()
        end = datetime.strptime(f"{end_h:02d}:{end_m:02d}", "%H:%M").time()

        if start <= end:
            return start <= now <= end
        else:
            # Overnight range (e.g., 22:00–08:00)
            return now >= start or now <= end
