"""Tray notification handler — listens to reminders_fired and shows a merged tray message."""

from __future__ import annotations

from datetime import datetime

from ..config import AppConfig
from ..utils.signal_bus import get_signal_bus


class TaskNotifier:
    """Listens to reminders_fired signals and shows a single merged tray notification,
    respecting quiet hours defined in config."""

    def __init__(self, tray_manager, config: AppConfig) -> None:
        self._tray = tray_manager
        self._config = config
        self._signal_bus = get_signal_bus()
        self._signal_bus.reminders_fired.connect(self._on_reminders_fired)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_reminders_fired(self, reminders: list) -> None:
        if self._in_quiet_hours() or not reminders:
            return
        # 合并所有任务标题为一条消息（最多显示 5 个）
        names = [t.title for t, _ in reminders[:5]]
        suffix = f" 等 {len(reminders)} 项" if len(reminders) > 5 else ""
        msg = "、".join(names) + suffix
        self._tray.show_message("任务提醒", msg)

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
