"""QApplication subclass — startup orchestration."""

from __future__ import annotations

import sys
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtNetwork import QLocalServer
from PySide6.QtWidgets import QApplication

from .config import AppConfig
from .models.repository import TaskRepository
from .models.task import Task
from .services.archiver import TaskArchiver
from .services.notifier import TaskNotifier
from .utils.design_tokens import init_tokens, refresh_tokens
from .services.recurrence import TaskRecurrence
from .services.scheduler import TaskScheduler
from .ui.main_window import MainWindow
from .ui.system_tray import SystemTrayManager
from .utils.icon_loader import get_icon_loader
from .utils.signal_bus import get_signal_bus


def _ensure_test_partition(repo: TaskRepository) -> None:
    """Create the 「测试分区」with optimization-tracking tasks in dev mode only."""
    if getattr(sys, "frozen", False):
        return

    partitions = repo.get_all_partitions()
    if any(p["name"] == "测试分区" for p in partitions):
        return

    from .services.md_parser import MarkdownTaskParser

    parser = MarkdownTaskParser()
    test = repo.upsert_partition("测试分区", sort_order=200)
    pid = test["id"]
    today = date.today()
    now = datetime.now()

    def _ts(d: int = 0, h: int = 0) -> str:
        return (now - timedelta(days=d, hours=h)).isoformat()

    # Optimization tracking tasks organized by module
    optimizations = [
        (
            f"- [ ] DONE<{today}> 优化：新建任务活动时间线缺少初始状态和进度 #任务创建",
            "优化：新建任务活动时间线缺少初始状态和进度",
            [
                {"ts": _ts(1), "content": "【问题】新建任务时 activity_log 为空，活动时间线中通过 created_at 派生的「创建任务」行不显示状态和进度信息", "status": "TODO", "progress": 0},
                {"ts": _ts(0, 2), "content": "【方案】在四个创建入口（task_input/task_dialog/task_edit_panel/main_window_import）添加初始 activity_log 条目，记录 status+progress，移除展示层的派生回退逻辑", "status": "DOING", "progress": 50},
                {"ts": _ts(0), "content": "【完成】所有新建任务自动记录「创建任务」条目（含状态和进度），38 个测试通过", "status": "DONE", "progress": 100},
            ],
            now,
        ),
        (
            f"- [ ] DONE<{today}> 优化：进度输入控件过于复杂 #编辑面板",
            "优化：进度输入控件 QSpinBox 替换为简单 QLineEdit",
            [
                {"ts": _ts(1), "content": "【问题】活动时间线中的进度输入使用 QSpinBox（带上下箭头），交互复杂，用户只需输入 0~100 数字即可", "status": "TODO", "progress": 0},
                {"ts": _ts(0, 1), "content": "【方案】用 QLineEdit + QIntValidator(0,100) 替换 QSpinBox，添加 % 后缀标签，简化交互", "status": "DOING", "progress": 50},
                {"ts": _ts(0), "content": "【完成】进度输入简化为纯数字输入框，0~100 范围验证，38 个测试通过", "status": "DONE", "progress": 100},
            ],
            now,
        ),
        (
            f"- [ ] TODO<{today + timedelta(days=7)}> 优化：左侧任务列表默认排序规则 #任务列表",
            "优化：左侧任务列表默认排序规则（暂缓）",
            [
                {"ts": _ts(0), "content": "【问题】当前默认按 status 排序，用户期望按 status+deadline 联合排序，但 FilterBar 仅支持单字段排序", "status": "TODO", "progress": 0},
                {"ts": _ts(0), "content": "【分析】TaskFilter.sort_by 已支持 list[SortCriterion]，需改造 FilterBar.set_sort/build_filter 支持逗号分隔的多字段排序，settings_dialog 增加联合排序选项", "status": "TODO", "progress": 10},
            ],
            None,
        ),
        (
            f"- [ ] TODO<{today + timedelta(days=14)}> 优化待办 #任务列表",
            "（示例）在此分区记录新的优化问题",
            [
                {"ts": _ts(0), "content": "【问题】描述发现的问题或需要优化的点", "status": "TODO", "progress": 0},
                {"ts": _ts(0), "content": "【方案】描述解决思路和改动点", "status": "TODO", "progress": 0},
            ],
            None,
        ),
    ]

    for raw_md, title, log, completed in optimizations:
        parsed = parser.parse(raw_md)
        task = Task(
            id=str(uuid.uuid4()),
            raw_md=raw_md,
            title=title,
            status=parsed.status,
            tags=parsed.tags,
            deadline_date=parsed.deadline_date,
            deadline_time=parsed.deadline_time,
            scheduled_date=parsed.scheduled_date,
            partition_id=pid,
            activity_log=log,
            completed_at=completed,
        )
        repo.insert(task)


def _ensure_demo_partition(repo: TaskRepository) -> None:
    """Create the 「功能演示」partition with demo tasks if it doesn't exist."""
    partitions = repo.get_all_partitions()
    if any(p["name"] == "功能演示" for p in partitions):
        return  # already exists

    from .services.md_parser import MarkdownTaskParser

    parser = MarkdownTaskParser()
    demo = repo.upsert_partition("功能演示", sort_order=100)
    pid = demo["id"]
    today = date.today()

    def _ago(d: int) -> str:
        return (datetime.now() - timedelta(days=d)).isoformat()

    def _ago_h(d: int, h: int) -> str:
        return (datetime.now() - timedelta(days=d, hours=h)).isoformat()

    demos = [
        (
            f"- [x] DONE<{today - timedelta(days=2)}> 准备季度汇报 PPT #工作",
            "准备季度汇报 PPT — 完整状态流转演示",
            [
                {"ts": _ago(4), "content": "收集各团队 Q3 数据报表", "status": "TODO"},
                {"ts": _ago_h(4, -3), "content": "确定汇报框架：营收、成本、增长", "status": "DOING"},
                {"ts": _ago(3), "content": "完成初稿 15 页，交付组长审阅", "status": "DOING"},
                {"ts": _ago(2), "content": "终稿审核通过 ✓", "status": "DONE"},
            ],
            datetime.now() - timedelta(days=2),
        ),
        (
            f"- [ ] TODO<{today + timedelta(days=2)}> 每周三次有氧运动 #健康",
            "每周三次有氧运动 — 循环任务 + 标签",
            [{"ts": datetime.now().isoformat(), "content": "本周完成 1/3 次：跑步 5km", "status": "TODO"}],
            None,
        ),
        (
            f"- [ ] DOING<{today + timedelta(days=10)}> 阅读《系统设计面试》第 5-8 章 #学习",
            "阅读《系统设计面试》— DOING + 多次进展",
            [
                {"ts": _ago(6), "content": "开始第 5 章：设计限流器（令牌桶 vs 漏桶）", "status": "DOING"},
                {"ts": _ago(4), "content": "完成第 5 章，整理笔记 3 页", "status": "DOING"},
                {"ts": _ago(2), "content": "第 6 章：设计键值存储，已读一半", "status": "DOING"},
            ],
            None,
        ),
        (
            f"- [ ] DOING<{today + timedelta(days=1)}> 学习 Rust 所有权和借用机制 #学习 #Rust",
            "学习 Rust 所有权机制 — DOING + 详细笔记",
            [
                {"ts": _ago(2), "content": "阅读 Rust Book 第 4 章：所有权", "status": "DOING"},
                {"ts": _ago(1), "content": "理解三规则：每个值只有一个所有者；值离开作用域被丢弃；引用不获取所有权", "status": "DOING"},
                {"ts": datetime.now().isoformat(), "content": "完成练习题 1-10，正确率 8/10", "status": "DOING"},
            ],
            None,
        ),
        (
            f"- [ ] TODO<{today - timedelta(days=1)}> 整理本月开支账单 #生活",
            "整理本月开支账单 — 逾期演示",
            [
                {"ts": _ago(3), "content": "导出支付宝账单 CSV", "status": "TODO"},
                {"ts": _ago(2), "content": "导出微信账单 CSV", "status": "TODO"},
            ],
            None,
        ),
        (
            f"- [ ] TODO<{today + timedelta(days=30)}> 规划端午出行行程 #生活 #旅行",
            "规划端午出行行程 — TODO 远期计划",
            [
                {"ts": _ago(7), "content": "初步确定目的地：成都（3 天 2 晚）", "status": "TODO"},
                {"ts": _ago(5), "content": "查看攻略，等待朋友确认出发时间", "status": "TODO"},
            ],
            None,
        ),
        (
            f"- [ ] TODO<{today + timedelta(days=7)}> 写技术博客：深入理解 Python asyncio 协程 #学习 #写作",
            "写技术博客：Python 协程 — C 优先级",
            [{"ts": datetime.now().isoformat(), "content": "确定选题和大纲：事件循环、Task、await 原理", "status": "TODO"}],
            None,
        ),
        (
            f"- [ ] TODO<{today + timedelta(days=60)}> 整理书单并写读书笔记 #阅读 #生活",
            "整理书单并写读书笔记 — TODO 稍后处理",
            [],
            None,
        ),
    ]

    for raw_md, title, log, completed in demos:
        parsed = parser.parse(raw_md)
        task = Task(
            id=str(uuid.uuid4()),
            raw_md=raw_md,
            title=title,
            status=parsed.status,
            tags=parsed.tags,
            deadline_date=parsed.deadline_date,
            deadline_time=parsed.deadline_time,
            scheduled_date=parsed.scheduled_date,
            partition_id=pid,
            activity_log=log,
            completed_at=completed,
        )
        repo.insert(task)


class DeskTodoSeqApp(QApplication):
    """Main application — owns config, repository, services, and top-level UI."""

    def __init__(self, argv: list[str], local_server: QLocalServer) -> None:
        super().__init__(argv)
        self._local_server = local_server
        self._local_server.setParent(self)
        self._local_server.newConnection.connect(self._on_wake_request)

        self.setApplicationName("DeskTodoSeq")
        self.setApplicationVersion("0.1.0")
        self.setOrganizationName("DeskTodoSeq")
        self.setQuitOnLastWindowClosed(False)

        # Core services
        self._config = AppConfig()
        init_tokens(self._config)
        self._repository = TaskRepository(self._config.db_path())
        self._repository.open()

        # Ensure demo partition exists on first launch
        _ensure_demo_partition(self._repository)
        # Ensure test partition exists in dev mode
        _ensure_test_partition(self._repository)

        # Load theme and icons early
        self._load_theme()
        self._load_icons()

        # Signal bus
        self._signal_bus = get_signal_bus()
        self._signal_bus.application_quit.connect(self._on_quit)
        self._signal_bus.config_changed.connect(self._on_config_changed)

        # UI
        self._main_window = MainWindow(self._config, self._repository)
        self._tray = SystemTrayManager(self._main_window, self._config)

        # Background services
        self._scheduler = TaskScheduler(self._repository, self._config)
        self._notifier = TaskNotifier(self._tray, self._config)
        self._archiver = TaskArchiver(self._repository, self._config)
        self._recurrence = TaskRecurrence(self._repository)

        self._scheduler.start()
        self._archiver.start()

        self._main_window.show()
        QTimer.singleShot(100, self._main_window.apply_screen_size)
        QTimer.singleShot(200, self._refresh_overdue_on_startup)

    def _refresh_overdue_on_startup(self) -> None:
        """Scan all tasks and auto-set/revert OVERDUE status after startup."""
        changed = self._repository.refresh_overdue_status()
        for task, old_status in changed:
            self._signal_bus.task_status_changed.emit(task, old_status)

    def _on_wake_request(self) -> None:
        """Another instance tried to start — bring existing window to front."""
        while self._local_server.hasPendingConnections():
            conn = self._local_server.nextPendingConnection()
            if conn and conn.waitForReadyRead(500):
                conn.readAll()
            conn.close()
        w = self._main_window
        w.show()
        w.setWindowState(w.windowState() & ~Qt.WindowState.WindowMinimized)
        w.raise_()
        w.activateWindow()

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def _load_theme(self) -> None:
        from .utils.design_tokens import build_palette, refresh_tokens

        theme_name = self._config.theme
        if theme_name == "system":
            theme_name = self._detect_system_theme()
        refresh_tokens()

        # Apply QPalette — handles text and standard widget colours globally
        self.setPalette(build_palette())

        # Apply QSS for shapes (borders, padding, fonts; colours are kept
        # for structural elements like toolbar/card backgrounds and borders)
        qss_path = self._resource_path("themes", f"{theme_name}.qss")
        if qss_path and qss_path.exists():
            with open(qss_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())
        else:
            self.setStyleSheet("")

    @staticmethod
    def _detect_system_theme() -> str:
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            )
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return "light" if value == 1 else "dark"
        except Exception:
            return "light"

    # ------------------------------------------------------------------
    # Resources
    # ------------------------------------------------------------------

    def _resource_path(self, *parts: str) -> Path | None:
        base = getattr(sys, "_MEIPASS", None)
        if base:
            path = Path(base) / "resources" / Path(*parts)
            if path.exists():
                return path
        path = Path(__file__).resolve().parents[1] / "resources" / Path(*parts)
        return path if path.exists() else None

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    @property
    def config(self) -> AppConfig:
        return self._config

    @property
    def repository(self) -> TaskRepository:
        return self._repository

    @property
    def main_window(self) -> MainWindow:
        return self._main_window

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def _on_quit(self) -> None:
        self._scheduler.stop()
        self._archiver.stop()
        self._repository.close()
        self.quit()

    def _load_icons(self) -> None:
        loader = get_icon_loader()
        self.setWindowIcon(loader.app_icon())

    def _on_config_changed(self) -> None:
        self._load_theme()
        refresh_tokens()
        get_icon_loader().clear_cache()
        self._load_icons()
        self._main_window.refresh_theme()
