"""Tag management panel — rename and merge tags across all tasks."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QColor, QCursor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...models.repository import TaskRepository
from ...services.md_formatter import MarkdownTaskFormatter
from ...utils.design_tokens import get_tokens


class TagManagementPanel(QWidget):
    """Right-side panel for viewing, renaming, and merging tags.

    Signals:
        tag_changed: emitted after any rename or merge operation completes.
    """

    tag_changed = Signal()

    def __init__(self, repository: TaskRepository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._repository = repository
        self._partition_id: str | None = None
        self._formatter = MarkdownTaskFormatter()
        self._all_tags: list[tuple[str, int]] = []  # full list before search filter
        self._tag_page = 0
        self._tag_page_size = 20
        self._tag_total = 0
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self._apply_search)
        self._setup_ui()
        self._connect_signals()

    # ------------------------------------------------------------------
    # UI Setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- Container with bg and border ---
        container = QWidget()
        container.setObjectName("tagPanelContainer")
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(8, 6, 8, 6)
        container_layout.setSpacing(6)

        # --- Header ---
        container_layout.addWidget(QLabel("🏷 标签管理"))

        # --- Search ---
        from PySide6.QtWidgets import QLineEdit as _QLE

        self._search_input = _QLE()
        self._search_input.setObjectName("tagSearchInput")
        self._search_input.setPlaceholderText("搜索标签...")
        self._search_input.setClearButtonEnabled(True)
        self._search_input.textChanged.connect(self._on_search_text_changed)
        container_layout.addWidget(self._search_input)

        # --- Tag list ---
        self._tag_list = QListWidget()
        self._tag_list.setObjectName("tagList")
        self._tag_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._tag_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tag_list.customContextMenuRequested.connect(self._on_context_menu)
        container_layout.addWidget(self._tag_list, 1)

        # --- Pagination bar ---
        pg_bar = QHBoxLayout()
        pg_bar.setSpacing(4)
        pg_bar.setContentsMargins(0, 2, 0, 0)

        self._tag_prev_btn = QPushButton("◀")
        self._tag_prev_btn.setObjectName("tagActionBtn")
        self._tag_prev_btn.setFixedWidth(32)
        self._tag_prev_btn.clicked.connect(self._on_tag_prev)
        pg_bar.addWidget(self._tag_prev_btn)

        self._tag_next_btn = QPushButton("▶")
        self._tag_next_btn.setObjectName("tagActionBtn")
        self._tag_next_btn.setFixedWidth(32)
        self._tag_next_btn.clicked.connect(self._on_tag_next)
        pg_bar.addWidget(self._tag_next_btn)

        self._tag_page_label = QLabel("0 / 0")
        self._tag_page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._tag_page_label.setStyleSheet("font-size: 10px;")
        pg_bar.addWidget(self._tag_page_label)

        pg_bar.addStretch()
        container_layout.addLayout(pg_bar)

        # --- Button row ---
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)

        self._rename_btn = QPushButton("✏ 重命名")
        self._rename_btn.setObjectName("tagActionBtn")
        self._rename_btn.setEnabled(False)
        self._rename_btn.clicked.connect(self._on_rename)
        btn_row.addWidget(self._rename_btn)

        self._merge_btn = QPushButton("🔗 合并")
        self._merge_btn.setObjectName("tagActionBtn")
        self._merge_btn.setEnabled(False)
        self._merge_btn.clicked.connect(self._on_merge)
        btn_row.addWidget(self._merge_btn)

        self._refresh_btn = QPushButton("🔄 刷新")
        self._refresh_btn.setObjectName("tagActionBtn")
        self._refresh_btn.clicked.connect(self.refresh)
        btn_row.addWidget(self._refresh_btn)

        container_layout.addLayout(btn_row)

        layout.addWidget(container)

    def _connect_signals(self) -> None:
        self._tag_list.itemSelectionChanged.connect(self._update_button_states)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Reload tag list from repository (respects current partition)."""
        self._tag_page = 0
        self._all_tags = self._repository.get_all_tags_with_counts(self._partition_id)
        self._apply_search()

    def refresh_theme(self) -> None:
        """Re-apply current theme colours to tag list items."""
        self._apply_search()

    def set_partition_id(self, pid: str) -> None:
        """Set the active partition and refresh the tag list."""
        self._partition_id = pid or None
        self.refresh()

    # ------------------------------------------------------------------
    # Internal: tag list display
    # ------------------------------------------------------------------

    def _apply_search(self) -> None:
        """Filter the tag list by the current search text, paginate, and rebuild display."""
        search = self._search_input.text().strip().lower()
        filtered = self._all_tags
        if search:
            filtered = [(tag, cnt) for tag, cnt in self._all_tags if search in tag.lower()]

        self._tag_total = len(filtered)
        total_pages = max(1, (self._tag_total + self._tag_page_size - 1) // self._tag_page_size)
        if self._tag_page >= total_pages:
            self._tag_page = 0

        start = self._tag_page * self._tag_page_size
        page_tags = filtered[start:start + self._tag_page_size]

        self._tag_list.clear()
        t = get_tokens()
        for tag, count in page_tags:
            item = QListWidgetItem()
            item.setText(f"#{tag}({count})")
            item.setData(Qt.ItemDataRole.UserRole, tag)
            item.setForeground(QColor(t.text_primary))
            self._tag_list.addItem(item)

        self._tag_page_label.setText(f"第 {self._tag_page + 1}/{total_pages} 页")
        self._tag_prev_btn.setEnabled(self._tag_page > 0)
        self._tag_next_btn.setEnabled(self._tag_page < total_pages - 1)
        self._update_button_states()

    def _selected_tags(self) -> list[str]:
        """Return tag names of all selected items."""
        result: list[str] = []
        for item in self._tag_list.selectedItems():
            tag = item.data(Qt.ItemDataRole.UserRole)
            if tag:
                result.append(tag)
        return result

    def _update_button_states(self) -> None:
        selected = self._selected_tags()
        self._rename_btn.setEnabled(len(selected) == 1)
        self._merge_btn.setEnabled(len(selected) >= 2)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def _on_search_text_changed(self, _text: str) -> None:
        self._tag_page = 0
        self._search_timer.start()

    def _on_tag_prev(self) -> None:
        if self._tag_page > 0:
            self._tag_page -= 1
            self._apply_search()

    def _on_tag_next(self) -> None:
        total_pages = max(1, (self._tag_total + self._tag_page_size - 1) // self._tag_page_size)
        if self._tag_page < total_pages - 1:
            self._tag_page += 1
            self._apply_search()

    # ------------------------------------------------------------------
    # Rename
    # ------------------------------------------------------------------

    def _on_rename(self) -> None:
        selected = self._selected_tags()
        if len(selected) != 1:
            return
        old_tag = selected[0]
        new_tag, ok = QInputDialog.getText(
            self, "重命名标签",
            f"将标签 \"{old_tag}\" 重命名为：",
            text=old_tag,
        )
        if not ok or not new_tag.strip():
            return
        new_tag = new_tag.strip()

        # Validation
        if new_tag == old_tag:
            return
        if "#" in new_tag:
            QMessageBox.warning(self, "无效名称", "标签名称不能包含 # 字符。")
            return

        # Check for conflict (case-insensitive)
        existing = {t.lower(): t for t, _ in self._all_tags}
        if new_tag.lower() in existing and existing[new_tag.lower()] != old_tag:
            reply = QMessageBox.question(
                self, "标签已存在",
                f"标签 \"{existing[new_tag.lower()]}\" 已存在。\n"
                f"是否将 \"{old_tag}\" 合并到 \"{existing[new_tag.lower()]}\"？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._execute_merge({old_tag}, existing[new_tag.lower()])
            return

        self._execute_rename(old_tag, new_tag)

    def _execute_rename(self, old_tag: str, new_tag: str) -> None:
        """Replace old_tag with new_tag in all tasks that contain it."""
        tasks = self._repository.get_tasks_by_tag(old_tag, self._partition_id)
        if not tasks:
            QMessageBox.information(self, "提示", f"没有任务使用标签 \"{old_tag}\"。")
            return

        count = 0
        for task in tasks:
            if old_tag in task.tags:
                task.tags = [
                    new_tag if t == old_tag else t
                    for t in task.tags
                ]
                # Deduplicate (case-insensitive)
                task.tags = self._dedup_tags(task.tags)
                task.raw_md = self._formatter.format(task)
                self._repository.update(task)
                count += 1

        self.tag_changed.emit()
        self.refresh()
        QMessageBox.information(
            self, "重命名完成",
            f"已将标签 \"{old_tag}\" 重命名为 \"{new_tag}\"，更新了 {count} 个任务。",
        )

    # ------------------------------------------------------------------
    # Merge
    # ------------------------------------------------------------------

    def _on_merge(self) -> None:
        selected = self._selected_tags()
        if len(selected) < 2:
            return
        self._show_merge_dialog(selected)

    def _show_merge_dialog(self, source_tags: list[str]) -> None:
        """Show a dialog to choose the merge target."""
        from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QVBoxLayout as _VL

        dlg = QDialog(self)
        dlg.setWindowTitle("合并标签")
        dlg.setMinimumWidth(320)
        dlg_layout = _VL(dlg)
        dlg_layout.setSpacing(10)

        info = QLabel(
            f"将 {len(source_tags)} 个标签合并为一个。\n"
            f"所有源标签将被替换为目标标签，源标签将被删除。\n"
            f"此操作不可撤销，请确认。"
        )
        info.setStyleSheet("QLabel { font-size: 11px; }")
        info.setWordWrap(True)
        dlg_layout.addWidget(info)

        target_label = QLabel("合并到（选择保留的标签）：")
        target_label.setStyleSheet("QLabel { font-size: 10px; font-weight: bold; }")
        dlg_layout.addWidget(target_label)

        combo = QComboBox()
        combo.setStyleSheet("QComboBox { font-size: 10px; padding: 3px; }")
        for t in source_tags:
            combo.addItem(f"#{t}", t)
        dlg_layout.addWidget(combo)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        dlg_layout.addWidget(buttons)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        target_tag = combo.currentData()
        if not target_tag:
            return
        sources = set(source_tags) - {target_tag}
        if not sources:
            QMessageBox.information(self, "提示", "没有需要合并的标签。")
            return

        self._execute_merge(sources, target_tag)

    def _execute_merge(self, source_tags: set[str], target_tag: str) -> None:
        """Replace all source_tags with target_tag in all affected tasks."""
        tasks = self._repository.get_tasks_by_tags(source_tags, self._partition_id)
        if not tasks:
            QMessageBox.information(self, "提示", "没有任务使用选中的标签。")
            return

        count = 0
        for task in tasks:
            original = list(task.tags)
            new_tags: list[str] = []
            for t in original:
                if t in source_tags:
                    new_tags.append(target_tag)
                else:
                    new_tags.append(t)
            # Deduplicate (case-insensitive)
            task.tags = self._dedup_tags(new_tags)
            if task.tags != original:
                task.raw_md = self._formatter.format(task)
                self._repository.update(task)
                count += 1

        self.tag_changed.emit()
        self.refresh()
        QMessageBox.information(
            self, "合并完成",
            f"已将 {len(source_tags)} 个标签合并到 \"{target_tag}\"，更新了 {count} 个任务。",
        )

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------

    def _on_context_menu(self, pos) -> None:
        item = self._tag_list.itemAt(pos)
        if not item:
            return
        tag = item.data(Qt.ItemDataRole.UserRole)
        if not tag:
            return
        selected = self._selected_tags()

        menu = QMenu(self)

        rename_action = menu.addAction("✏ 重命名")
        rename_action.triggered.connect(self._on_rename)

        if len(selected) >= 2 and tag in selected:
            merge_action = menu.addAction(f"🔗 合并选中标签到 \"{tag}\"")
            merge_action.triggered.connect(
                lambda: self._execute_merge(set(selected) - {tag}, tag)
            )

        menu.addSeparator()
        refresh_action = menu.addAction("🔄 刷新")
        refresh_action.triggered.connect(self.refresh)

        menu.exec(QCursor.pos())

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _dedup_tags(tags: list[str]) -> list[str]:
        """Deduplicate tags case-insensitively, preserving first occurrence's casing."""
        seen: set[str] = set()
        result: list[str] = []
        for t in tags:
            if t.lower() not in seen:
                seen.add(t.lower())
                result.append(t)
        return result
