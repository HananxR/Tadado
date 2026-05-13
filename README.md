# DeskTodoSeq

Windows 桌面任务管理工具，Markdown 语法定义和管理任务（兼容 **Todoseq** 格式），SQLite 本地存储 + FTS5 全文搜索，配备日历热力图可视化、活动时间线、草稿编辑。

## 核心功能

- **Markdown 原生任务** — 以 `"- [ ] TODO [#A] <2026-05-20> 重构模块 #标签"` 格式创建和编辑，`raw_md` 为唯一数据源
- **状态快速流转** — 点击状态标签在 TODO → DOING → DONE / URGENT / WAIT / LATER 循环切换，支持下拉 + 快捷按钮
- **优先级与截止日** — `[#A]` `[#B]` `[#C]` 三级优先级，`<日期>` 截止日，自动检测逾期
- **标签 + 全文搜索** — `#标签` 自由分类，SQLite FTS5 全文搜索引擎
- **日历热力图** — GitHub 风格任务活跃度，年份切换，点击日期筛选
- **活动时间线** — 每个任务独立时间线：创建/状态变更/进展追加/完成，卡片式展示，支持编辑、删除、多选、复制 Markdown
- **轮播 + 快速筛选** — 顶部轮播今日 A/B 活跃任务，一键切换"全部/今日/本周/逾期"视图，轮播联动
- **草稿模式** — 工具栏"新建"在今日视角下创建内存草稿，保存后入库，未保存离开时提醒
- **自动选中** — 筛选后自动选中列表第一条（紧急 > 优先级 > 截止日排序）
- **系统托盘** — 最小化到托盘，定时提醒通知
- **Markdown 导入/导出** — 纯文本即可迁移

## 技术栈

| 层 | 技术 |
|---|------|
| 语言 | Python 3.10 |
| GUI | PySide6 (Qt for Python) |
| 数据库 | SQLite + FTS5 |
| 调度 | APScheduler |
| 包管理 | uv + setuptools |
| 测试 | pytest + pytest-qt |
| 构建 | PyInstaller（单文件 exe） |

## 架构

```
src/
  models/    领域模型 — Task, TaskStatus, Priority, TaskFilter, TaskRepository
  services/  业务逻辑 — MarkdownParser, MarkdownFormatter (往返稳定)
  ui/        PySide6 — main_window, system_tray, task_list/, calendar_heatmap/, dialogs/, widgets/
  utils/     信号总线(SignalBus), 日期工具, Win32 工具, 图标加载
```

**核心数据流**：Markdown 行 → `MarkdownTaskParser` → 结构化字段 → `TaskRepository` 入库（raw_md + FTS5）。编辑时修改 raw_md → 重新解析 → 同步更新。`MarkdownTaskFormatter` 保证往返稳定（round-trip invariant）。

## 开发进度

| Sprint | 内容 | 状态 |
|--------|------|------|
| Sprint 1 | 领域模型、Markdown 解析/格式化、Repository、测试套件 | ✅ |
| Sprint 2 | 应用骨架（app.py、config.py、main_window、system_tray、QSS） | ✅ |
| Sprint 3 | 任务列表组件（输入、列表、筛选、右键菜单、编辑面板） | ✅ |
| Sprint 4 | 日历热力图（日级活跃度、颜色映射、年份切换、点击筛选） | ✅ |
| Sprint 5 | 对话框、导入导出、通知、归档、循环任务 | ✅ |
| Sprint 6 | 活动时间线、状态统计栏、轮播横幅、草稿模式、UI 统一优化 | ✅ |

**测试覆盖**：35 用例（parser 20 + formatter 5 + repository 12 + empty-state 3），全部通过。

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

## 参考

- [Todoseq](https://github.com/nicepkg/todoseq) — Markdown 任务格式规范
- [Org-mode](https://orgmode.org/) — 状态流转设计理念
- [GitHub Contribution Graph](https://docs.github.com/en/account-and-profile) — 热力图可视化灵感
- [Qt Framework](https://www.qt.io/) — PySide6 跨平台 GUI
- [SQLite FTS5](https://www.sqlite.org/fts5.html) — 内置全文搜索

> 本项目仅供个人学习与实践使用。
