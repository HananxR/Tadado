# DeskTodoSeq

Windows 桌面任务管理工具，使用 Markdown 语法定义和管理任务（兼容 **Todoseq** 格式），SQLite 本地存储 + FTS5 全文搜索，配备日历热力图可视化。

## 核心功能

- **Markdown 原生任务定义** — 任务以 `"- [ ] TODO [#A] <2026-05-20> 重构模块 #标签"` 格式创建和编辑，`raw_md` 为唯一数据源
- **快速状态流转** — 点击状态标签即可在 TODO → DOING → DONE / URGENT / WAIT / LATER 之间循环切换
- **优先级与截止日** — 支持 `[#A]` `[#B]` `[#C]` 三级优先级，`<日期>` 截止日标记，自动检测逾期
- **标签 + 全文搜索** — 任意 `#标签` 自由分类，SQLite FTS5 引擎对标题、标签、备注全文检索
- **日历热力图** — GitHub 风格的任务活跃度热力图，直观展示每日任务完成情况
- **系统托盘常驻** — 最小化到托盘，全局快捷键唤出/隐藏，定时提醒通知
- **数据可移植** — 所有任务导入/导出为 Markdown 文件，纯文本即可迁移

## 技术栈

| 层 | 技术 |
|---|------|
| 语言 | Python 3.10 |
| GUI 框架 | PySide6 (Qt for Python) |
| 数据库 | SQLite + FTS5 全文搜索 |
| 调度器 | APScheduler（提醒、归档等定时任务） |
| 快捷键 | pynput（全局热键监听） |
| 包管理 | uv + setuptools |
| 测试 | pytest + pytest-qt + pytest-mock |
| 构建打包 | PyInstaller（单文件 exe） |

## 架构概览

```
src/
  models/      领域模型 — Task、TaskStatus、Priority、TaskFilter、TaskRepository
  services/    业务逻辑 — Markdown 解析器/格式化器
  ui/          PySide6 界面 — 主窗口、系统托盘、任务列表、日历热力图、对话框
  utils/       横切工具 — 信号总线(SignalBus)、日期工具、Win32 工具
```

**核心数据流**：Markdown 行 → `MarkdownTaskParser` 解析 → `TaskRepository` 入库（raw_md + 结构化字段 + FTS5 索引）。编辑时修改 raw_md → 重新解析 → 同步更新。`MarkdownTaskFormatter` 保证相同字段始终生成稳定的 Markdown 输出。

## 开发规划

| Sprint | 内容 | 状态 |
|--------|------|------|
| Sprint 1 | 领域模型、Markdown 解析/格式化、Repository、测试套件 | ✅ 完成 |
| Sprint 2 | 应用骨架（app.py、config.py、main_window、system_tray、主题 QSS） | ✅ 完成 |
| Sprint 3 | 任务列表组件（输入框、列表视图、筛选栏、右键菜单） | 🔲 待开发 |
| Sprint 4 | 日历热力图组件（日级活跃度方格、颜色映射、年份切换） | 🔲 待开发 |
| Sprint 5 | 对话框（设置、导入导出、关于）、通知提醒、归档、循环任务 | 🔲 待开发 |

## 当前进度

- **已完成**：models 全部（Task / TaskStatus / Priority / TaskFilter / TaskRepository）、Markdown 解析器/格式化器、SignalBus 信号总线、AppConfig 配置管理、MainWindow 主窗口框架（菜单栏/工具栏/侧边栏/状态栏）、SystemTray 系统托盘管理器、light/dark 主题 QSS、3 个测试文件（parser / formatter / repository）
- **待开发**：task_list 组件、calendar_heatmap 组件、dialogs 对话框、widgets 通用组件、scheduler 定时调度器、notifier 通知器、archiver 归档器、recurrence 循环任务

## 快速开始

```bash
# 环境搭建
uv venv --python 3.10 .venv
uv sync --dev

# 运行
uv run python main.py

# 测试
uv run pytest

# 构建
uv run pyinstaller --name="DeskTodoSeq" --windowed --onefile \
  --icon="resources/icons/app.ico" \
  --add-data="resources;resources" main.py
```

## 参考来源

本项目在设计与实现中参考了以下优秀项目和方案：

- **[Todoseq](https://github.com/nicepkg/todoseq)** — Markdown 任务序列化规范，定义了通过 Markdown 行描述任务状态、优先级、日期、标签的语法，DeskTodoSeq 完全兼容此格式
- **[Org-mode](https://orgmode.org/)** — Emacs 的任务管理与大纲系统，状态流转（TODO → DOING → DONE）的设计理念来源
- **[GitHub Contribution Graph](https://docs.github.com/en/account-and-profile/setting-up-and-managing-your-github-profile/managing-contribution-settings-on-your-profile)** — 日历热力图的可视化灵感来源
- **[Qt Framework](https://www.qt.io/)** — 通过 PySide6 绑定使用的跨平台 GUI 框架
- **[SQLite FTS5](https://www.sqlite.org/fts5.html)** — 内置全文搜索引擎，支撑任务搜索功能

> 本项目仅供个人学习与实践使用。
