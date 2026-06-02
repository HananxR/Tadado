"""Tag chip cloud — checkable capsule buttons in flow layout for activity analysis."""

from __future__ import annotations

import json
from datetime import date, datetime

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLayout,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ...models.repository import TaskRepository
from ...models.task import Task
from ...utils.design_tokens import get_tokens


class _FlowLayout(QLayout):
    """Horizontal flow layout that wraps items to the next row."""

    def __init__(self, parent: QWidget | None = None, margin: int = 0, spacing: int = 4):
        super().__init__(parent)
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)
        self._items: list = []

    def addItem(self, item) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self) -> Qt.Orientation:
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        size += QSize(m.left() + m.right(), m.top() + m.bottom())
        return size

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        m = self.contentsMargins()
        x = rect.x() + m.left()
        y = rect.y() + m.top()
        line_height = 0
        spacing = self.spacing()
        usable = rect.width() - m.left() - m.right()

        for item in self._items:
            hint = item.sizeHint()
            w, h = hint.width(), hint.height()
            if x + w > rect.x() + m.left() + usable and line_height > 0:
                x = rect.x() + m.left()
                y += line_height + spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(x, y, w, h))
            x += w + spacing
            line_height = max(line_height, h)
        return y + line_height + m.bottom() - rect.y()


class TaskTreePanel(QWidget):
    """Tag chip cloud with checkable capsule buttons. Emits tag_selected(tag_name)."""

    tag_selected = Signal(str)
    checked_tags_changed = Signal()

    def __init__(self, repository: TaskRepository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._repository = repository
        self._tag_task_map: dict[str, list[Task]] = {}
        self._checked_tags: set[str] = set()
        self._active_tag: str | None = None
        self._all_checked = True
        self._tag_buttons: dict[str, QPushButton] = {}
        self._chip_order: list[str] = []
        self._tag_filter_text: str = ""
        self._build_ui()

    def _build_ui(self) -> None:
        t = get_tokens()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Top row: search filter + select-all toggle ──
        top_row = QWidget()
        top_row.setFixedHeight(28)
        top_layout = QHBoxLayout(top_row)
        top_layout.setContentsMargins(2, 3, 2, 3)
        top_layout.setSpacing(3)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("筛选标签…")
        self._search_input.setFixedHeight(22)
        self._search_input.setStyleSheet(
            f"QLineEdit {{ font-size: 10px; padding: 1px 4px; "
            f"border: 1px solid {t.border_primary}; border-radius: 3px; "
            f"background: transparent; color: {t.text_primary}; }}"
        )
        self._search_input.textChanged.connect(self._apply_tag_filter)
        top_layout.addWidget(self._search_input, 1)

        self._toggle_btn = QPushButton("全")
        self._toggle_btn.setFixedSize(28, 22)
        self._toggle_btn.setStyleSheet("QPushButton { font-size: 10px; padding: 0px; }")
        self._toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_btn.clicked.connect(self.toggle_all_checked)
        top_layout.addWidget(self._toggle_btn)

        layout.addWidget(top_row)

        # ── Separator ──
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("activityHline")
        layout.addWidget(sep)

        # ── Scrollable chip container ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self._chip_container = QWidget()
        self._chip_container.setStyleSheet("background: transparent;")
        self._chip_layout = _FlowLayout(self._chip_container, margin=2, spacing=4)
        scroll.setWidget(self._chip_container)

        layout.addWidget(scroll, 1)

    def _chip_style(self, checked: bool) -> str:
        t = get_tokens()
        if checked:
            return (
                f"QPushButton {{ font-size: 11px; padding: 4px 10px; "
                f"border: 1.5px solid {t.accent}; border-radius: 14px; "
                f"background: {t.accent}; color: {t.text_on_accent}; "
                f"font-weight: bold; }}"
                f"QPushButton:hover {{ background: {t.accent}dd; }}"
            )
        return (
            f"QPushButton {{ font-size: 11px; padding: 4px 10px; "
            f"border: 1.5px solid {t.border_primary}; border-radius: 14px; "
            f"background: transparent; color: {t.text_secondary}; }}"
            f"QPushButton:hover {{ border-color: {t.accent}80; color: {t.text_primary}; }}"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refresh(self, date_from: date | None, date_to: date | None,
                partition_id: str | None, tag_filter: str | None = None) -> None:
        from ...models.task_filter import TaskFilter

        self._last_date_range = (date_from, date_to)
        self._last_partition_id = partition_id

        f = TaskFilter(partition_id=partition_id)
        tasks = self._repository.search(f)

        tag_data: dict[str, tuple[int, list[Task]]] = {}
        for task in tasks:
            entries = self._filter_entries(task, date_from, date_to)
            tag = (task.tags or ["__untagged__"])[0]
            if tag_filter and tag != tag_filter:
                continue
            if tag not in tag_data:
                tag_data[tag] = (0, [])
            count, task_list = tag_data[tag]
            tag_data[tag] = (count + len(entries), task_list + [task])

        sorted_tags = sorted(tag_data.items(), key=lambda x: x[1][0], reverse=True)

        # Clear old chips
        for btn in self._tag_buttons.values():
            self._chip_layout.removeWidget(btn)
            btn.deleteLater()
        self._tag_buttons.clear()
        self._tag_task_map.clear()
        self._checked_tags.clear()
        self._chip_order.clear()
        self._active_tag = None

        ftext = self._tag_filter_text.lower()
        for tag, (count, task_list) in sorted_tags:
            display = tag if tag != "__untagged__" else "未分类"
            if ftext and ftext not in display.lower():
                continue
            if len(display) > 8:
                display = display[:8] + "…"
            label = f"#{display}({count})"
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(self._chip_style(checked=True))
            btn.clicked.connect(lambda checked, t=tag, b=btn: self._on_chip_clicked(t, checked, b))
            btn.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            self._tag_buttons[tag] = btn
            self._tag_task_map[tag] = task_list
            self._checked_tags.add(tag)
            self._chip_order.append(tag)
            self._chip_layout.addWidget(btn)

        self._all_checked = True
        self._toggle_btn.setText("全")

        if self._chip_order:
            first_tag = self._chip_order[0]
            self._active_tag = first_tag
            self.tag_selected.emit(first_tag)
        else:
            self._active_tag = None
            self.tag_selected.emit("")

    def get_tasks_for_tag(self, tag: str) -> list[Task]:
        return self._tag_task_map.get(tag, [])

    def get_checked_tags(self) -> list[str]:
        return [t for t in self._chip_order if t in self._checked_tags]

    def get_next_checked_tag(self, current_tag: str) -> str | None:
        checked = self.get_checked_tags()
        try:
            idx = checked.index(current_tag)
            if idx + 1 < len(checked):
                return checked[idx + 1]
        except ValueError:
            pass
        return None

    def select_tag(self, tag: str) -> None:
        if tag not in self._tag_buttons:
            return
        if tag != self._active_tag:
            self._active_tag = tag
            self.tag_selected.emit(tag)
        btn = self._tag_buttons[tag]
        btn.setFocus()

    def toggle_all_checked(self) -> None:
        self._all_checked = not self._all_checked
        new_checked = self._all_checked
        self._checked_tags.clear()
        for tag, btn in self._tag_buttons.items():
            btn.blockSignals(True)
            btn.setChecked(new_checked)
            btn.setStyleSheet(self._chip_style(checked=new_checked))
            btn.blockSignals(False)
            if new_checked:
                self._checked_tags.add(tag)
        self._toggle_btn.setText("全" if self._all_checked else "⊘")
        self.checked_tags_changed.emit()

    def get_active_tag(self) -> str | None:
        return self._active_tag

    def select_prev(self) -> None:
        """Cycle to the previous checked tag (wrap around)."""
        checked = self.get_checked_tags()
        if not checked:
            return
        try:
            idx = checked.index(self._active_tag) if self._active_tag in checked else -1
        except ValueError:
            idx = -1
        prev_tag = checked[idx - 1] if idx > 0 else checked[-1]
        self.select_tag(prev_tag)

    def select_next(self) -> None:
        """Cycle to the next checked tag (wrap around)."""
        checked = self.get_checked_tags()
        if not checked:
            return
        try:
            idx = checked.index(self._active_tag) if self._active_tag in checked else -1
        except ValueError:
            idx = -1
        next_tag = checked[idx + 1] if idx + 1 < len(checked) else checked[0]
        self.select_tag(next_tag)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_chip_clicked(self, tag: str, checked: bool, btn: QPushButton) -> None:
        btn.setStyleSheet(self._chip_style(checked=checked))
        if checked:
            self._checked_tags.add(tag)
        else:
            self._checked_tags.discard(tag)
        self._all_checked = all(
            self._tag_buttons[t].isChecked() for t in self._chip_order
        )
        self._toggle_btn.setText("全" if self._all_checked else "⊘")
        self.checked_tags_changed.emit()

        if tag != self._active_tag:
            self._active_tag = tag
            self.tag_selected.emit(tag)

    def _apply_tag_filter(self, text: str) -> None:
        self._tag_filter_text = text
        d_from, d_to = getattr(self, '_last_date_range', (None, None))
        pid = getattr(self, '_last_partition_id', None)
        self.refresh(d_from, d_to, pid)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _filter_entries(self, task: Task, date_from: date | None, date_to: date | None) -> list[dict]:
        if date_from is None or date_to is None:
            return self._parse_log(task)
        entries = self._parse_log(task)
        return [e for e in entries if date_from <= self._entry_date(e) <= date_to]

    def _parse_log(self, task: Task) -> list[dict]:
        try:
            raw = task.activity_log
            if not raw or raw == "[]":
                return []
            return json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            return []

    def _entry_date(self, entry: dict) -> date:
        try:
            ts = entry.get("ts", entry.get("time", ""))
            if "T" in ts:
                return datetime.fromisoformat(ts).date()
            return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").date()
        except (ValueError, TypeError):
            return date.today()
