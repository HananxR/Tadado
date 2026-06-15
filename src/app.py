"""QApplication subclass — startup orchestration."""

from __future__ import annotations

import sys
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtNetwork import QLocalServer
from PySide6.QtWidgets import QApplication

from .config import AppConfig
from .models.repository import TaskRepository
from .models.task import Task
from .services.archiver import TaskArchiver
from .services.notifier import TaskNotifier
from .services.recurrence import TaskRecurrence
from .services.scheduler import TaskScheduler
from .ui.main_window import MainWindow
from .ui.system_tray import SystemTrayManager
from .utils.design_tokens import init_tokens, refresh_tokens
from .utils.icon_loader import get_icon_loader
from .utils.signal_bus import get_signal_bus


def _ensure_test_partition(repo: TaskRepository) -> None:
    """Create the 「测试分区」with optimization-tracking tasks in dev mode only.

    Uses per-task title dedup so new tracking tasks are added on each launch.
    """
    if getattr(sys, "frozen", False) or "__compiled__" in dir(sys):
        return

    partitions = repo.get_all_partitions()
    if any(p["name"] == "测试分区" for p in partitions):
        # Partition exists — only add missing tasks (incremental)
        existing = repo.get_all_partitions()
        test_p = next((p for p in existing if p["name"] == "测试分区"), None)
        if test_p is None:
            return
        pid = test_p["id"]
        _seed_optimization_tasks(repo, pid)
        return


    test = repo.upsert_partition("测试分区", sort_order=200)
    pid = test["id"]
    _seed_optimization_tasks(repo, pid)


def _seed_optimization_tasks(repo: TaskRepository, pid: str) -> None:
    """Incrementally seed Sprint 8 tracking tasks into a partition."""
    from .services.md_parser import MarkdownTaskParser

    parser = MarkdownTaskParser()
    today = date.today()
    now = datetime.now()

    def _ts(d: int = 0, h: int = 0) -> str:
        return (now - timedelta(days=d, hours=h)).isoformat()

    # Get existing task titles for dedup
    existing_titles: set[str] = set()
    from .models.task_filter import TaskFilter
    existing = repo.search(TaskFilter(partition_id=pid))
    for t in existing:
        existing_titles.add(t.title)

    # Comprehensive test cases — incremental: only insert if title not already present
    optimizations = [
        # === TEST CASES for comprehensive feature verification ===
        (f"- [ ] TODO<{today}> T1: 速览栏预设切换验证 #测试 #速览栏", "T1: 速览栏预设切换验证", [
            {"ts": _ts(0), "content": "【步骤1】点击'今天'按钮 → 验证任务列表刷新为今日任务", "status": "TODO", "progress": 0},
            {"ts": _ts(0), "content": "【步骤2】点击'本周'按钮 → 验证统计栏计数变化", "status": "TODO", "progress": 0},
            {"ts": _ts(0), "content": "【步骤3】点击'本月'按钮 → 验证轮播栏更新", "status": "TODO", "progress": 0},
        ], None),
        (f"- [ ] TODO<{today}> T2: 速览栏默认选中+高亮 #测试 #速览栏", "T2: 速览栏默认选中+高亮", [
            {"ts": _ts(0), "content": "【步骤1】重启应用 → 验证速览栏默认选中'今天'", "status": "TODO", "progress": 0},
            {"ts": _ts(0), "content": "【步骤2】验证选中按钮蓝色背景高亮", "status": "TODO", "progress": 0},
            {"ts": _ts(0), "content": "【步骤3】切换分区 → 验证默认回到'今天'", "status": "TODO", "progress": 0},
        ], None),
        (f"- [ ] TODO<{today}> T3: 进度栏联动 #测试 #进度栏", "T3: 进度栏联动", [
            {"ts": _ts(0), "content": "【步骤1】速览点击'今天' → 验证进度栏仅'今天'可点击", "status": "TODO", "progress": 0},
            {"ts": _ts(0), "content": "【步骤2】点击进度栏'今天' → 验证任务列表排序变化但总数不变", "status": "TODO", "progress": 0},
            {"ts": _ts(0), "content": "【步骤3】新建任务 → 验证进度栏恢复未点击状态", "status": "TODO", "progress": 0},
        ], None),
        (f"- [ ] TODO<{today}> T4: 统计栏计数正确性 #测试 #统计栏", "T4: 统计栏计数正确性", [
            {"ts": _ts(0), "content": "【步骤1】验证FilterBar右侧显示各状态计数", "status": "TODO", "progress": 0},
            {"ts": _ts(0), "content": "【步骤2】切换速览预设 → 验证计数随日期范围更新", "status": "TODO", "progress": 0},
            {"ts": _ts(0), "content": "【步骤3】底部状态栏数据与统计栏一致", "status": "TODO", "progress": 0},
        ], None),
        (f"- [ ] TODO<{today}> T5: 批量操作复选框 #测试 #批量操作", "T5: 批量操作复选框", [
            {"ts": _ts(0), "content": "【步骤1】点击复选框 → 验证绿色对勾显示+批量工具栏更新计数", "status": "TODO", "progress": 0},
            {"ts": _ts(0), "content": "【步骤2】点击全选/取消 → 验证所有复选框联动", "status": "TODO", "progress": 0},
            {"ts": _ts(0), "content": "【步骤3】选3任务 → 状态变更→进行中 → 验证activity_log记录", "status": "TODO", "progress": 0},
            {"ts": _ts(0), "content": "【步骤4】选2任务 → 中止 → 验证变灰+重启后恢复", "status": "TODO", "progress": 0},
        ], None),
        (f"- [ ] TODO<{today}> T6: 编辑器单任务 #测试 #编辑器 #单任务", "T6: 编辑器单任务", [
            {"ts": _ts(0), "content": "【步骤1】新建 → 验证编辑器打开+默认时间+标签模板", "status": "TODO", "progress": 0},
            {"ts": _ts(0), "content": "【步骤2】输入无标签内容 → 保存 → 验证'标签缺失'提示", "status": "TODO", "progress": 0},
            {"ts": _ts(0), "content": "【步骤3】输入正确格式 → 保存 → 验证列表新增+右侧加载新任务", "status": "TODO", "progress": 0},
        ], None),
        (f"- [ ] TODO<{today}> T7: 编辑器多任务拆分 #测试 #编辑器 #多任务", "T7: 编辑器多任务拆分", [
            {"ts": _ts(0), "content": "【步骤1】新建多任务 → 验证3行模板显示", "status": "TODO", "progress": 0},
            {"ts": _ts(0), "content": "【步骤2】保存 → 验证一次保存创建3条独立任务", "status": "TODO", "progress": 0},
            {"ts": _ts(0), "content": "【步骤3】验证每条可独立选中/编辑/删除", "status": "TODO", "progress": 0},
        ], None),
        (f"- [ ] TODO<{today}> T8: 截止计算器(快速计算) #测试 #快速计算", "T8: 截止计算器(快速计算)", [
            {"ts": _ts(0), "content": "【步骤1】点击快速计算 → 验证弹窗显示", "status": "TODO", "progress": 0},
            {"ts": _ts(0), "content": "【步骤2】切换天/周/月 → 验证选项正确切换", "status": "TODO", "progress": 0},
            {"ts": _ts(0), "content": "【步骤3】验证不触发全局刷新(BUG修复验证)", "status": "TODO", "progress": 0},
        ], None),
        (f"- [ ] TODO<{today}> T9: 活动时间线+智能进度 #测试 #时间线", "T9: 活动时间线+智能进度", [
            {"ts": _ts(0), "content": "【步骤1】选中任务 → 追加进展 → 状态选已完成 → 验证进度自动100%", "status": "TODO", "progress": 0},
            {"ts": _ts(0), "content": "【步骤2】输入空内容点追加 → 验证'内容为空'提醒", "status": "TODO", "progress": 0},
            {"ts": _ts(0), "content": "【步骤3】验证时间线新增记录+列表状态更新", "status": "TODO", "progress": 0},
        ], None),
        (f"- [ ] TODO<{today}> T10: 分区切换 #测试 #分区", "T10: 分区切换", [
            {"ts": _ts(0), "content": "【步骤1】切换分区 → 验证按钮文字更新+任务列表刷新", "status": "TODO", "progress": 0},
            {"ts": _ts(0), "content": "【步骤2】验证无重名分区", "status": "TODO", "progress": 0},
        ], None),
        (f"- [ ] TODO<{today}> T11: 主题切换 #测试 #主题", "T11: 主题切换", [
            {"ts": _ts(0), "content": "【步骤1】设置→显示→深色 → 验证菜单/按钮/文字可见", "status": "TODO", "progress": 0},
            {"ts": _ts(0), "content": "【步骤2】验证紧急程度行背景在深色下可见", "status": "TODO", "progress": 0},
            {"ts": _ts(0), "content": "【步骤3】切回浅色 → 验证正常", "status": "TODO", "progress": 0},
        ], None),
        (f"- [ ] TODO<{today}> T12: 翻页+序号 #测试 #翻页", "T12: 翻页+序号", [
            {"ts": _ts(0), "content": "【步骤1】创建12+任务 → 验证翻页按钮可用", "status": "TODO", "progress": 0},
            {"ts": _ts(0), "content": "【步骤2】切换每页数量 → 验证重排", "status": "TODO", "progress": 0},
        ], None),
        (f"- [ ] TODO<{today}> T13: 设置-分区管理+加密 #测试 #设置", "T13: 设置-分区管理+加密", [
            {"ts": _ts(0), "content": "【步骤1】新建分区→设置密码 → 切换需密码验证", "status": "TODO", "progress": 0},
            {"ts": _ts(0), "content": "【步骤2】错误密码 → 验证蒙版提示+锁定", "status": "TODO", "progress": 0},
            {"ts": _ts(0), "content": "【步骤3】解锁 → 验证恢复正常", "status": "TODO", "progress": 0},
        ], None),
        (f"- [ ] TODO<{today}> T14: 联动测试L1-L9 #测试 #联动", "T14: 联动测试L1-L9", [
            {"ts": _ts(0), "content": "【L1】速览→任务列表+统计栏+状态栏三处数据一致", "status": "TODO", "progress": 0},
            {"ts": _ts(0), "content": "【L2】速览→进度栏对应按钮可点击", "status": "TODO", "progress": 0},
            {"ts": _ts(0), "content": "【L3】进度栏→任务列表仅排序不变筛选", "status": "TODO", "progress": 0},
            {"ts": _ts(0), "content": "【L4】编辑器→列表刷新+自动选中", "status": "TODO", "progress": 0},
            {"ts": _ts(0), "content": "【L5】批量操作→列表+状态栏摘要", "status": "TODO", "progress": 0},
            {"ts": _ts(0), "content": "【L6】分区切换→全部联动重置", "status": "TODO", "progress": 0},
            {"ts": _ts(0), "content": "【L7】时间线→编辑器+列表同步", "status": "TODO", "progress": 0},
            {"ts": _ts(0), "content": "【L8】快速计算→不触发全局刷新", "status": "TODO", "progress": 0},
            {"ts": _ts(0), "content": "【L9】深浅主题→所有组件可读", "status": "TODO", "progress": 0},
        ], None),
    ]

    inserted = 0
    for raw_md, title, log, completed in optimizations:
        if title in existing_titles:
            continue
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
        inserted += 1


def _ensure_demo_partition(repo: TaskRepository) -> None:
    """Seed the 「功能演示」partition with demo tasks if empty or missing."""
    from .models.task_filter import TaskFilter
    from .services.md_parser import MarkdownTaskParser

    partitions = repo.get_all_partitions()
    demo_p = next((p for p in partitions if p["name"] == "功能演示"), None)
    if demo_p is not None:
        existing = repo.search(TaskFilter(partition_id=demo_p["id"], limit=1))
        if existing:
            return  # already seeded
        pid = demo_p["id"]
    else:
        demo = repo.upsert_partition("功能演示", sort_order=100)
        pid = demo["id"]

    parser = MarkdownTaskParser()
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


class TadadoApp(QApplication):
    """Main application — owns config, repository, services, and top-level UI."""

    def __init__(self, argv: list[str], local_server: QLocalServer) -> None:
        super().__init__(argv)
        self._local_server = local_server
        self._local_server.setParent(self)
        self._local_server.newConnection.connect(self._on_wake_request)

        self.setApplicationName("Tadado")
        self.setApplicationVersion("0.1.0")
        self.setOrganizationName("Tadado")
        self.setQuitOnLastWindowClosed(False)

        # ── Load bundled CJK font on Linux (Microsoft YaHei not available) ──
        self._load_bundled_fonts()

        # ── Config + theme must load before the shield so QSS is stable ──
        self._config = AppConfig()
        init_tokens(self._config)
        self._load_theme()  # set global QSS & QPalette BEFORE any widget is shown

        # Show startup shield — sized to exactly cover the main window area
        from .ui.splash_screen import StartupShield
        from .utils.win32_theme import set_window_nc_rendering_disabled

        self._shield: StartupShield | None = StartupShield(
            is_dark=(self._config.theme == "dark")
        )
        self._shield.match_main_window_geometry()  # match main window size & pos
        set_window_nc_rendering_disabled(self._shield)  # no ghost buttons on shield itself
        self.setOverrideCursor(Qt.CursorShape.ArrowCursor)  # suppress busy cursor
        self._shield.show()
        self.processEvents()  # force immediate paint so user sees it now
        # ────────────────────────────────────────────────────────────────────

        # Core services
        self._repository = TaskRepository(self._config.db_path())
        self._repository.open()

        # Ensure demo partition exists on first launch (skipped in frozen mode
        # — the package DB already contains pre-seeded data in 演示空间)
        if not getattr(sys, "frozen", False) and "__compiled__" not in dir(sys):
            _ensure_demo_partition(self._repository)
        # Ensure test partition exists in dev mode (already internally guarded)
        _ensure_test_partition(self._repository)

        # Load icons (icons depend on tokens, already initialized)
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
        self._notifier = TaskNotifier(self._tray, self._config, self._repository)
        self._archiver = TaskArchiver(self._repository, self._config)
        self._recurrence = TaskRecurrence(self._repository)

        self._scheduler.start()
        self._archiver.start()

        # Sync auto-start registry with config on launch
        from .utils.win32_autostart import set_autostart

        set_autostart(self._config.auto_start)

        self._main_window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, False)
        self._main_window.apply_screen_size()
        self._main_window.show()  # Qt renders; DWM stays hidden (CLOAKED)
        QTimer.singleShot(0, self._finish_startup)

    def _refresh_overdue_on_startup(self) -> None:
        """Scan all tasks and auto-set/revert OVERDUE status after startup."""
        changed = self._repository.refresh_overdue_status()
        for task, old_status in changed:
            self._signal_bus.task_status_changed.emit(task, old_status)

    def _finish_startup(self) -> None:
        """Uncloak main window so DWM composites it for the first time.

        By now Qt has already painted the complete custom title bar.
        DWM's first composition sees a fully-rendered frameless window
        — no native button ghost frames possible.
        """
        from .utils.win32_theme import set_window_cloaked

        set_window_cloaked(self._main_window, False)  # reveal to DWM
        # Wait 50ms (~3 VSync cycles at 60 Hz) so DWM's composition is
        # stable before we remove the shield that covers it.
        QTimer.singleShot(50, self._dismiss_shield)

    def _dismiss_shield(self) -> None:
        """Close the startup shield and complete remaining startup tasks."""
        if self._shield is not None:
            self._shield.dismiss()
            self._shield = None
        self.restoreOverrideCursor()  # restore cursor after init
        self._tray.show()
        QTimer.singleShot(200, self._refresh_overdue_on_startup)

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
    # Fonts
    # ------------------------------------------------------------------

    def _load_bundled_fonts(self) -> None:
        """Load bundled CJK + Emoji fonts on Linux (Windows has these system-wide)."""
        if sys.platform == "win32":
            return
        # CJK fallback: WenQuanYi Micro Hei (OFL)
        cjk = self._resource_path("fonts", "WenQuanYiMicroHei.ttc")
        if cjk and cjk.exists():
            QFontDatabase.addApplicationFont(str(cjk))
        # Emoji fallback: Noto Color Emoji (OFL)
        emoji = self._resource_path("fonts", "NotoColorEmoji.ttf")
        if emoji and emoji.exists():
            QFontDatabase.addApplicationFont(str(emoji))
        # Do NOT call setFont() — let Qt match fonts per-character via fallback chain.

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def _load_theme(self) -> None:
        from .utils.design_tokens import build_palette, expand_qss, refresh_tokens

        refresh_tokens()

        # Apply QPalette — handles text and standard widget colours globally
        QApplication.instance().setPalette(build_palette())

        # Load unified base.qss and expand token placeholders for current theme
        base_path = self._resource_path("themes", "base.qss")
        if base_path and base_path.exists():
            with open(base_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(expand_qss(f.read()))
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
