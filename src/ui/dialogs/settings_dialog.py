"""Application settings dialog with tabbed interface."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from ...config import AppConfig
from ...models.repository import TaskRepository
from ...utils.signal_bus import get_signal_bus


class SettingsDialog(QDialog):
    """Settings dialog with tabs for General, Display, Reminders, Archive, and Partitions."""

    def __init__(
        self, config: AppConfig, repository: TaskRepository, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._repository = repository
        self._original_theme = config.theme

        self.setWindowTitle("设置")
        self.setObjectName("settingsDialog")
        self.resize(580, 520)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        tabs = QTabWidget()
        tabs.addTab(self._build_general_tab(), "通用")
        tabs.addTab(self._build_display_tab(), "显示")
        tabs.addTab(self._build_reminders_tab(), "提醒")
        tabs.addTab(self._build_archive_tab(), "归档")
        tabs.addTab(self._build_partitions_tab(), "分区管理")
        tabs.addTab(self._build_motd_tab(), "激励语")
        tabs.addTab(self._build_help_tab(), "帮助")
        layout.addWidget(tabs)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------
    # General tab
    # ------------------------------------------------------------------

    def _build_general_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(10)

        self._minimize_cb = QCheckBox()
        self._minimize_cb.setChecked(self._config.minimize_to_tray)
        form.addRow("最小化到托盘", self._minimize_cb)

        self._auto_lock_spin = QSpinBox()
        self._auto_lock_spin.setRange(1, 120)
        self._auto_lock_spin.setSuffix(" 分钟")
        self._auto_lock_spin.setValue(
            self._config.get("general", "auto_lock_minutes", default=10)
        )
        form.addRow("分区自动锁定", self._auto_lock_spin)

        self._page_size_spin = QSpinBox()
        self._page_size_spin.setRange(10, 100)
        self._page_size_spin.setSingleStep(10)
        self._page_size_spin.setSuffix(" 条/页")
        self._page_size_spin.setValue(
            self._config.get("general", "page_size", default=20)
        )
        form.addRow("默认每页条数", self._page_size_spin)

        self._default_sort_combo = QComboBox()
        SORT_LABELS = {"status": "状态", "deadline": "截止日", "created": "创建时间", "title": "标题"}
        for key, label in SORT_LABELS.items():
            self._default_sort_combo.addItem(label, key)
        current_sort = self._config.get("general", "default_sort", default="status")
        idx = self._default_sort_combo.findData(current_sort)
        if idx >= 0:
            self._default_sort_combo.setCurrentIndex(idx)
        form.addRow("默认排序", self._default_sort_combo)

        return w

    # ------------------------------------------------------------------
    # Display tab
    # ------------------------------------------------------------------

    def _build_display_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(10)

        self._theme_combo = QComboBox()
        self._theme_combo.addItem("跟随系统", "system")
        self._theme_combo.addItem("浅色", "light")
        self._theme_combo.addItem("深色", "dark")
        for i in range(self._theme_combo.count()):
            if self._theme_combo.itemData(i) == self._config.theme:
                self._theme_combo.setCurrentIndex(i)
                break
        form.addRow("主题", self._theme_combo)

        start_year = self._config.get("display", "heatmap_start_year", default=2026)
        self._heatmap_start_year = QSpinBox()
        self._heatmap_start_year.setRange(2000, 2100)
        self._heatmap_start_year.setValue(start_year)
        form.addRow("热力图起始年份", self._heatmap_start_year)

        return w

    # ------------------------------------------------------------------
    # Reminders tab
    # ------------------------------------------------------------------

    def _build_reminders_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(10)

        self._reminders_cb = QCheckBox()
        self._reminders_cb.setChecked(self._config.reminders_enabled)
        form.addRow("启用提醒", self._reminders_cb)

        self._quiet_start = QTimeEdit()
        parts = self._config.get("reminders", "quiet_hours_start", default="22:00").split(":")
        from PySide6.QtCore import QTime
        self._quiet_start.setTime(QTime(int(parts[0]), int(parts[1])))
        form.addRow("安静时段开始", self._quiet_start)

        self._quiet_end = QTimeEdit()
        parts = self._config.get("reminders", "quiet_hours_end", default="08:00").split(":")
        self._quiet_end.setTime(QTime(int(parts[0]), int(parts[1])))
        form.addRow("安静时段结束", self._quiet_end)

        return w

    # ------------------------------------------------------------------
    # Archive tab
    # ------------------------------------------------------------------

    def _build_archive_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(10)

        self._archive_cb = QCheckBox()
        self._archive_cb.setChecked(self._config.archive_enabled)
        form.addRow("启用自动归档", self._archive_cb)

        self._archive_days = QSpinBox()
        self._archive_days.setRange(1, 365)
        self._archive_days.setValue(self._config.archive_after_days)
        form.addRow("完成后天数", self._archive_days)

        return w

    # ------------------------------------------------------------------
    # Partitions tab
    # ------------------------------------------------------------------

    def _build_partitions_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(8)

        hint = QLabel("勾选的分区将显示在筛选栏中，取消勾选可隐藏分区。")
        hint.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(hint)

        # Partition table: 可见 | 名称 | 密码 | 删除
        self._partition_table = QTableWidget(0, 4)
        self._partition_table.setHorizontalHeaderLabels(["可见", "名称", "密码", ""])
        self._partition_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self._partition_table.horizontalHeader().resizeSection(0, 40)
        self._partition_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._partition_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self._partition_table.horizontalHeader().resizeSection(2, 60)
        self._partition_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self._partition_table.horizontalHeader().resizeSection(3, 60)
        self._partition_table.verticalHeader().hide()
        self._partition_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self._partition_table)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("添加")
        add_btn.clicked.connect(self._on_add_partition)
        rename_btn = QPushButton("重命名")
        rename_btn.clicked.connect(self._on_rename_partition)
        delete_btn = QPushButton("删除")
        delete_btn.clicked.connect(self._on_delete_partition)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(rename_btn)
        btn_row.addWidget(delete_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        default_label = QLabel("默认分区：")
        self._default_partition_combo = QComboBox()
        layout.addWidget(default_label)
        layout.addWidget(self._default_partition_combo)

        self._populate_partition_table()
        return w

    def _populate_partition_table(self) -> None:
        self._partitions_data = self._repository.get_all_partitions()
        hidden = set(self._config.get("general", "hidden_partitions", default=[]))
        default_id = self._config.get("general", "default_partition", default="")

        self._partition_table.setRowCount(0)
        self._default_partition_combo.blockSignals(True)
        self._default_partition_combo.clear()
        self._default_partition_combo.addItem("(无)", "")

        for i, p in enumerate(self._partitions_data):
            row = self._partition_table.rowCount()
            self._partition_table.insertRow(row)

            # Visible checkbox
            cb = QCheckBox()
            cb.setChecked(p["id"] not in hidden)
            self._partition_table.setCellWidget(row, 0, cb)

            # Name
            name_item = QTableWidgetItem(p["name"])
            self._partition_table.setItem(row, 1, name_item)

            # Password button
            has_pwd = bool(p.get("password", ""))
            pwd_btn = QPushButton("🔒" if has_pwd else "🔓")
            pwd_btn.setStyleSheet(
                "QPushButton { font-size: 12px; padding: 2px 6px; border: none; background: transparent; }"
            )
            pwd_btn.clicked.connect(lambda checked=False, pid=p["id"]: self._on_set_partition_password(pid))
            self._partition_table.setCellWidget(row, 2, pwd_btn)

            # Delete button per row
            del_btn = QPushButton("删除")
            del_btn.setStyleSheet("QPushButton { color: #c0392b; font-size: 10px; padding: 2px 6px; }")
            del_btn.clicked.connect(lambda checked=False, pid=p["id"]: self._on_delete_single_partition(pid))
            self._partition_table.setCellWidget(row, 3, del_btn)

            # Default combo
            self._default_partition_combo.addItem(p["name"], p["id"])
            if p["id"] == default_id:
                self._default_partition_combo.setCurrentIndex(i + 1)

        self._default_partition_combo.blockSignals(False)

    def _on_add_partition(self) -> None:
        name, ok = QInputDialog.getText(self, "添加分区", "分区名称：")
        if ok and name.strip():
            self._repository.upsert_partition(name.strip())
            self._populate_partition_table()
            get_signal_bus().partitions_changed.emit()

    def _on_rename_partition(self) -> None:
        row = self._partition_table.currentRow()
        if row < 0 or row >= len(self._partitions_data):
            return
        p = self._partitions_data[row]
        name, ok = QInputDialog.getText(self, "重命名分区", "新名称：", text=p["name"])
        if ok and name.strip():
            self._repository.upsert_partition(name.strip(), partition_id=p["id"])
            self._populate_partition_table()
            get_signal_bus().partitions_changed.emit()

    def _on_delete_partition(self) -> None:
        row = self._partition_table.currentRow()
        if row < 0 or row >= len(self._partitions_data):
            return
        p = self._partitions_data[row]
        self._confirm_delete_partition(p)

    def _on_delete_single_partition(self, pid: str) -> None:
        for p in self._partitions_data:
            if p["id"] == pid:
                self._confirm_delete_partition(p)
                return

    def _on_set_partition_password(self, pid: str) -> None:
        has_pwd, cur = self._repository.check_partition_password(pid)
        if has_pwd:
            old, ok = QInputDialog.getText(
                self, "修改密码", "输入旧密码（留空清除，忘记请点OK后重置）：",
                QLineEdit.EchoMode.Password,
            )
            if not ok:
                return
            if not old:
                # Empty = clear password
                self._repository.set_partition_password(pid, "")
            elif old != cur:
                # Wrong password — offer reset
                result = QMessageBox.question(
                    self, "密码错误",
                    "旧密码不正确。是否直接设置新密码？（无需旧密码）",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if result != QMessageBox.StandardButton.Yes:
                    return
                new, ok2 = QInputDialog.getText(
                    self, "重置密码", "输入新密码（留空则清除）：",
                    QLineEdit.EchoMode.Password,
                )
                if ok2:
                    self._repository.set_partition_password(pid, new)
            else:
                # Correct password — change it
                new, ok2 = QInputDialog.getText(
                    self, "设置新密码", "输入新密码（留空则清除）：",
                    QLineEdit.EchoMode.Password,
                )
                if ok2:
                    self._repository.set_partition_password(pid, new)
        else:
            pwd, ok = QInputDialog.getText(
                self, "设置密码", "输入密码（留空则取消）：",
                QLineEdit.EchoMode.Password,
            )
            if ok and pwd:
                self._repository.set_partition_password(pid, pwd)
        self._populate_partition_table()
        get_signal_bus().partitions_changed.emit()

    def _confirm_delete_partition(self, p: dict) -> None:
        result = QMessageBox.question(
            self, "确认删除",
            f'确定要删除分区 "{p["name"]}" 吗？\n该分区下的任务将变为"未分类"。',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if result == QMessageBox.StandardButton.Yes:
            self._repository.delete_partition(p["id"])
            self._populate_partition_table()
            get_signal_bus().partitions_changed.emit()

    # ------------------------------------------------------------------
    # MOTD tab (encouragement messages)
    # ------------------------------------------------------------------

    def _build_motd_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(10)

        motd = self._config.get("motd", default={})
        labels = [
            ("today", "今日无事时："),
            ("week", "本周无事时："),
            ("overdue", "无逾期时："),
            ("all", "全部为空时："),
        ]
        self._motd_edits: dict[str, QLineEdit] = {}
        for key, label_text in labels:
            edit = QLineEdit()
            edit.setText(motd.get(key, ""))
            edit.setPlaceholderText("输入激励语…")
            self._motd_edits[key] = edit
            form.addRow(label_text, edit)

        return w

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Help tab
    # ------------------------------------------------------------------

    def _build_help_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)

        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setStyleSheet("QTextBrowser { font-size: 13px; line-height: 1.6; }")

        help_html = """
<h1 style="color:#2c3e50;border-bottom:2px solid #3498db;padding-bottom:8px;">DeskTodoSeq 帮助文档</h1>

<h2 style="color:#2980b9;">一、核心设计理念</h2>

<h3>1.1 Markdown 即数据</h3>
<p>DeskTodoSeq 以 <b>Markdown 文本行为任务的最小单元</b>。每一条任务都是一行标准的 Markdown：</p>
<pre style="background:#f5f6fa;padding:8px;border-radius:4px;">- [ ] TODO &lt;2026-05-20&gt; 重构认证模块 #backend</pre>
<p>这条文本 <b>既是用户看到的，也是数据库存储的规范格式</b>。结构化字段（状态、日期、标签）从 Markdown 派生，始终可通过解析器重新生成——<b>raw_md 是唯一真相源（Single Source of Truth）</b>。</p>

<h3>1.2 本地优先 · 隐私至上</h3>
<p>所有数据存储在本地 SQLite 数据库中，无需网络连接、无需注册账号。支持分区密码保护，敏感任务可加密隔离。</p>

<h3>1.3 键盘驱动 · 鼠标辅助</h3>
<p>核心操作（新建、编辑、状态切换）都支持快捷键。Markdown 文本编辑是主要的交互方式，可视化控件（日期选择器、状态下拉）作为辅助。</p>

<h3>1.4 时间可视化</h3>
<p>通过 GitHub 风格日历热力图、活动时间线、统计栏等可视化手段，让时间管理和任务进度一目了然。</p>

<hr>

<h2 style="color:#2980b9;">二、系统架构</h2>

<h3>2.1 分层设计</h3>
<pre style="background:#f5f6fa;padding:8px;border-radius:4px;">
┌─────────────────────────────────────────────┐
│  UI 层 (src/ui/)                            │
│  main_window · system_tray · task_list/     │
│  calendar_heatmap/ · dialogs/ · widgets/    │
├─────────────────────────────────────────────┤
│  服务层 (src/services/)                     │
│  md_parser · md_formatter · scheduler       │
│  notifier · archiver · recurrence           │
├─────────────────────────────────────────────┤
│  领域模型层 (src/models/)                   │
│  Task · TaskStatus · Partition               │
│  TaskFilter · TaskRepository (SQLite)       │
├─────────────────────────────────────────────┤
│  工具层 (src/utils/)                        │
│  signal_bus · date_utils · win32_utils      │
│  icon_loader                                 │
└─────────────────────────────────────────────┘</pre>

<h3>2.2 核心数据流</h3>
<pre style="background:#f5f6fa;padding:8px;border-radius:4px;">
用户输入 Markdown
    │
    ▼ MarkdownTaskParser.parse()
ParsedTask(status, deadline, title, tags...)
    │
    ▼ MarkdownTaskFormatter.format()
Task(raw_md, title, status, ...)  ← 规范化后的领域对象
    │
    ▼ TaskRepository.insert/update
SQLite (raw_md + 结构化列 + FTS5 全文索引)
</pre>

<h3>2.3 信号总线（SignalBus）</h3>
<p>各模块通过 Qt 信号解耦通信，不直接相互调用：</p>
<table style="width:100%;border-collapse:collapse;font-size:12px;" border="1" cellpadding="4" cellspacing="0">
<tr style="background:#3498db;color:white;"><th>信号</th><th>触发场景</th><th>响应组件</th></tr>
<tr><td><code>task_created</code></td><td>新建任务保存</td><td>MainWindow 刷新列表、统计栏、轮播</td></tr>
<tr><td><code>task_updated</code></td><td>任务字段修改</td><td>同上</td></tr>
<tr><td><code>task_deleted</code></td><td>删除任务</td><td>同上 + 清理引用</td></tr>
<tr><td><code>task_status_changed</code></td><td>状态变更</td><td>同上 + 活动时间线刷新</td></tr>
<tr><td><code>partitions_changed</code></td><td>分区增删改</td><td>工具栏菜单、筛选栏刷新</td></tr>
<tr><td><code>config_changed</code></td><td>设置保存</td><td>主题切换、字体更新</td></tr>
</table>

<hr>

<h2 style="color:#2980b9;">三、功能详解</h2>
<p><i>以下功能说明结合「功能演示」分区中的样例任务进行演示。</i></p>

<h3>3.1 任务创建与 Markdown 编辑</h3>
<p>点击工具栏 <b>+ 新建</b> 按钮（或 <kbd>Ctrl+N</kbd>），编辑面板自动生成今日日期的 TODO 模板：</p>
<pre style="background:#f5f6fa;padding:8px;border-radius:4px;">- [ ] TODO &lt;2026-05-15&gt; 新任务</pre>
<p><b>Markdown 语法规则：</b></p>
<ul>
<li><b>状态关键字</b>：<code>TODO</code> / <code>DOING</code> / <code>DONE</code> / <code>URGENT</code>——位于 <code>- [ ]</code> 之后</li>
<li><b>截止日期</b>：<code>&lt;YYYY-MM-DD&gt;</code> 或 <code>&lt;YYYY-MM-DD HH:MM&gt;</code></li>
<li><b>标签</b>：<code>#标签名</code>——可多个，置于行末</li>
</ul>

<h3>3.2 任务状态与生命周期</h3>
<p>任务状态按以下循环流转：</p>
<pre style="background:#f5f6fa;padding:8px;border-radius:4px;">
URGENT ──→ DOING ──→ DONE ──→ TODO
  ↑                            │
  └──────── TODO ←─────────────┘
</pre>
<p><b>操作方式：</b></p>
<ul>
<li><b>右键菜单</b>：任务列表右键 → 更改状态 → 选择目标状态</li>
<li><b>编辑面板</b>：底部状态下拉 + 「追加进展」按钮，一步完成状态切换 + 进展记录</li>
<li><b>Markdown 编辑</b>：直接修改状态关键字后保存</li>
</ul>
<p><b>示例：</b>查看「功能演示」分区中 <i>"准备季度汇报 PPT"</i> 的活动时间线，可看到 待办→进行中→已完成 的完整流转过程。</p>

<h3>3.3 活动时间线</h3>
<p>每条任务下方展示 <b>活动时间线</b>，按时间倒序显示：</p>
<ul>
<li>每次「追加进展」生成一条带时间戳的记录</li>
<li>状态变更自动记录</li>
<li>每条记录标记当前状态标签（带颜色）</li>
<li>「创建任务」作为时间线起点始终显示</li>
</ul>
<p><b>示例：</b>查看「功能演示」分区中 <i>"学习 Rust 所有权机制"</i> 的时间线，展示了多次追加进展的学习过程。</p>

<h3>3.4 分区管理（OneNote 笔记本模式）</h3>
<p>分区用于隔离不同场景的任务，类似 OneNote 的笔记本：</p>
<ul>
<li><b>创建分区</b>：设置 → 分区管理 → 添加（可设置密码保护）</li>
<li><b>切换分区</b>：工具栏 📖 按钮 → 选择分区</li>
<li><b>密码保护</b>：锁定后需输入密码才能查看分区内容</li>
<li><b>自动锁定</b>：设置 → 通用 → 分区自动锁定（N 分钟无操作后锁定）</li>
<li><b>隐藏分区</b>：分区管理中取消勾选，分区从工具栏菜单隐藏</li>
</ul>

<h3>3.5 筛选与排序</h3>
<p>筛选栏提供多维过滤：</p>
<ul>
<li><b>搜索框</b>：全文搜索（基于 FTS5），支持中文分词</li>
<li><b>状态筛选</b>：按 URGENT / TODO / DOING / DONE 过滤</li>
<li><b>优先级筛选</b>：按 A / B / C 过滤</li>
<li><b>排序</b>：支持按状态、截止日、优先级、创建时间、标题排序</li>
</ul>
<p>顶部快捷按钮：<b>全部 | 今日 | 本周 | 逾期</b>，一键切换视角。</p>

<h3>3.6 日历热力图</h3>
<p>工具栏热力图按钮 切换显示 GitHub 风格的贡献热力图：</p>
<ul>
<li>每个格子代表一天，颜色深浅反映当天任务量</li>
<li>点击某天自动筛选该日期的任务</li>
<li>支持年份切换</li>
<li>颜色可在设置 → 显示中自定义</li>
</ul>
<p><b>示例：</b>切换到「功能演示」分区查看热力图，可看到 5 月中旬任务密集区。</p>

<h3>3.7 提醒与归档</h3>
<ul>
<li><b>提醒</b>：设置 → 提醒 → 启用后按间隔检查到期任务，托盘弹窗通知</li>
<li><b>安静时段</b>：可设置免打扰时间段</li>
<li><b>自动归档</b>：设置 → 归档 → 启用后自动归档 N 天前已完成的任务</li>
</ul>

<h3>3.8 任务详情对话框</h3>
<p>右键任务 → 详情，弹出详情对话框，可查看：</p>
<ul>
<li>完整活动时间线（只读）</li>
<li>标签编辑：以 <code>#tag1 #tag2</code> 格式直接修改</li>
<li>复制 MD：一键复制 Markdown 原文</li>
</ul>

<h3>3.9 统计栏</h3>
<p>筛选栏下方状态统计栏显示各状态任务数量、逾期数，点击可快速筛选。</p>

<h3>3.10 轮播横幅</h3>
<p>顶部轮播区自动滚动显示近期优先任务，点击可跳转。</p>

<h3>3.11 系统托盘</h3>
<p>关闭窗口默认最小化到系统托盘（可在设置中修改），托盘图标右键菜单支持快速操作。</p>

<h3>3.12 快捷键</h3>
<table style="width:100%;border-collapse:collapse;font-size:12px;" border="1" cellpadding="4" cellspacing="0">
<tr style="background:#3498db;color:white;"><th>快捷键</th><th>功能</th></tr>
<tr><td><kbd>Ctrl+N</kbd></td><td>新建任务</td></tr>
<tr><td><kbd>Ctrl+Alt+T</kbd></td><td>显示/隐藏主窗口</td></tr>
</table>

<hr>

<h2 style="color:#2980b9;">四、「功能演示」分区样例说明</h2>
<p>切换到「功能演示」分区可查看以下演示场景：</p>

<table style="width:100%;border-collapse:collapse;font-size:12px;" border="1" cellpadding="4" cellspacing="0">
<tr style="background:#3498db;color:white;"><th>任务</th><th>演示要点</th></tr>
<tr><td>📊 准备季度汇报 PPT</td><td>完整状态流转（TODO→DOING→DONE）+ 活动时间线</td></tr>
<tr><td>🏃 每周三次有氧运动</td><td>循环任务 + 标签 #健康</td></tr>
<tr><td>📖 阅读《系统设计面试》</td><td>DOING 状态 + 多次追加进展</td></tr>
<tr><td>🦀 学习 Rust 所有权机制</td><td>URGENT 高优先级 + 详细学习笔记时间线</td></tr>
<tr><td>💰 整理本月开支账单</td><td>逾期任务展示 + deadline 紧迫感</td></tr>
<tr><td>✈️ 规划端午出行行程</td><td>远期截止日 + WAIT 等待中状态</td></tr>
<tr><td>📝 写技术博客：Python 协程</td><td>低保真优先级 + 富文本活动记录</td></tr>
<tr><td>📚 整理书单并写读书笔记</td><td>LATER 稍后状态 + 多标签</td></tr>
</table>

<p>建议逐一查看每条任务，体验 <b>状态切换、追加进展、活动时间线、右键详情</b> 等核心功能。</p>

<hr>

<h2 style="color:#2980b9;">五、数据存储</h2>
<ul>
<li><b>数据库</b>：SQLite，位于 <code>resources/tasks.db</code></li>
<li><b>配置文件</b>：JSON，位于 <code>resources/config.json</code></li>
<li><b>FTS5 索引</b>：全文搜索虚拟表 <code>tasks_fts</code></li>
<li><b>标签存储</b>：JSON 数组字符串 <code>["tag1","tag2"]</code></li>
<li><b>活动日志</b>：JSON 数组字符串 <code>[{"ts":"...","content":"...","status":"..."}]</code></li>
</ul>

<hr>

<h2 style="color:#2980b9;">六、常见问题</h2>

<p><b>Q: 任务是否可以跨分区移动？</b><br>
A: 目前需在编辑面板中切换分区下拉来迁移任务。</p>

<p><b>Q: 忘记分区密码怎么办？</b><br>
A: 设置 → 分区管理 → 选中分区 → 设置密码 → 输入错误密码后可选择直接设置新密码（原数据不解密）。</p>

<p><b>Q: 如何备份数据？</b><br>
A: 直接复制 <code>resources/</code> 目录下的 <code>tasks.db</code> 和 <code>config.json</code> 即可。</p>

<p><b>Q: Markdown 格式写错了会怎样？</b><br>
A: 保存时解析器会尝试容错解析，如果完全无法解析会提示"解析失败"。</p>

<p style="margin-top:30px;color:#95a5a6;font-size:11px;">
DeskTodoSeq — 用 Markdown 管理时间，用数据可视化进度。
</p>
"""
        browser.setHtml(help_html)
        layout.addWidget(browser)
        return w

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def _on_accept(self) -> None:
        self._config.set("general", "minimize_to_tray", value=self._minimize_cb.isChecked())
        self._config.set("general", "auto_lock_minutes", value=self._auto_lock_spin.value())
        self._config.set("general", "page_size", value=self._page_size_spin.value())
        self._config.set("general", "default_sort", value=self._default_sort_combo.currentData())
        self._config.set("display", "theme", value=self._theme_combo.currentData())
        self._config.set("display", "heatmap_start_year", value=self._heatmap_start_year.value())
        self._config.set("reminders", "enabled", value=self._reminders_cb.isChecked())
        self._config.set(
            "reminders", "quiet_hours_start",
            value=self._quiet_start.time().toString("HH:mm"),
        )
        self._config.set(
            "reminders", "quiet_hours_end",
            value=self._quiet_end.time().toString("HH:mm"),
        )
        self._config.set("archive", "enabled", value=self._archive_cb.isChecked())
        self._config.set("archive", "completed_after_days", value=self._archive_days.value())
        self._config.set(
            "general", "default_partition",
            value=self._default_partition_combo.currentData(),
        )
        # Save hidden partitions
        hidden = []
        for r in range(self._partition_table.rowCount()):
            cb = self._partition_table.cellWidget(r, 0)
            if cb and not cb.isChecked():
                pid = self._partitions_data[r]["id"]
                hidden.append(pid)
        self._config.set("general", "hidden_partitions", value=hidden)

        motd_cfg = {}
        for key, edit in self._motd_edits.items():
            if edit.text().strip():
                motd_cfg[key] = edit.text().strip()
        self._config.set("motd", value=motd_cfg)

        self._config.save()
        self.accept()

    def theme_changed(self) -> bool:
        """Return True if the theme was changed."""
        return self._theme_combo.currentData() != "system"
