# DeskTodoSeq

Windows 桌面任务管理工具，Markdown 语法定义和管理任务（兼容 **Todoseq** 格式），SQLite 本地存储 + FTS5 全文搜索，配备日历热力图可视化、活动时间线、草稿编辑。

## 核心功能

- **Markdown 原生任务** — 以 `"- [ ] TODO [#A] <2026-05-20> 重构模块 #标签"` 格式创建和编辑，`raw_md` 为唯一数据源
- **状态快速流转** — 点击状态标签在 TODO → DOING → DONE / URGENT / WAIT / LATER 循环切换，支持下拉 + 快捷按钮
- **优先级与截止日** — `[#A]` `[#B]` `[#C]` 三级优先级，`<日期>` 截止日，自动检测逾期
- **标签 + 全文搜索** — `#标签` 自由分类，SQLite FTS5 全文搜索引擎
- **日历热力图** — GitHub 风格任务活跃度，年份切换，点击日期筛选
- **活动时间线** — 每个任务独立时间线：创建/状态变更/进展追加/完成，卡片式展示，支持编辑、删除、多选、复制 Markdown
- **速览栏** — 合并轮播+预设按钮（全部/今天/本周/逾期），基于截止日计算紧迫度，3个一组轮播
- **进度动态栏** — 5种周期切换（昨天/今天/本周/本月/年度），按活动条数+进度排序，可配置启用/禁用
- **批量操作** — 多选任务 → 批量状态变更/删除/中止/重启，底部状态栏显示摘要统计
- **编辑器分栏** — Markdown 编辑器 + 预览左右布局，预览可切换显示/隐藏
- **截止区间计算器** — 临时/周/月三种任务类型智能设期，自动更新日期时间选择器
- **多任务创建** — 新建按钮下拉菜单（单任务/多任务），批量输入+共享截止时间
- **标签必填** — 保存时强制验证标签，无标签不可保存
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

**设计决策**：
- 速览栏合并轮播+预设按钮，紧迫度基于截止日与"最后时间"之差计算（今天 23:59:59 / 本周日 23:59:59）
- 进度动态栏按"活动条数+进度"排序追踪任务进展，替代原 StatusStatsBar 的周期切换
- 状态徽章条（StatusBadgeStrip）独立保留，展示各状态计数+点击筛选
- 任务状态限定为 4 种（OVERDUE/TODO/DOING/DONE）；OVERDUE 由系统自动设置
- 分区为全局作用域（工具栏选择器），所有视图按分区隔离；支持密码保护 + 自动锁定
- 编辑区默认折叠，Markdown 编辑器+预览左右分栏（预览可切换显示/隐藏）
- 所有筛选变更统一经 `_refresh_all_views()` 调度，保证任务列表、速览栏、进度栏、状态栏数据一致
- `suspended` 列独立于状态枚举，中止的任务不参与统计；批量操作通过 SignalBus 广播

## Sprint 8 核心功能

### 速览栏 (QuickOverviewBar)
- **合并轮播+预设**：全部/今天/本周/逾期 预设按钮 + 任务轮播 3 个一组
- **紧迫度算法**：今天基于 `(今日23:59:59 - 截止日)` 秒差、本周基于 `(周日23:59:59 - 截止日)` 秒差
- **自动滚动**：每 5 秒切换一组，越靠前越紧急
- **联动**：点击预设 → 任务表按进度排序刷新 → 右侧自动打开第一个任务

### 进度动态栏 (ProgressDynamicsBar)
- **5 周期切换**：昨天/今天/本周/本月/年度
- **可配置启用/禁用**：`config.json` 中 `progress_bar.enabled_periods`
- **排序**：按 `activity_log 条目数 DESC, progress DESC` 排序
- **最活跃提示**：显示当前周期活动最多的任务名+条数

### 批量操作
- **多选支持**：TaskListView 改为 `ExtendedSelection` 模式
- **BatchToolbar**：状态变更/删除/中止/重启 按钮，自动显示选中数量
- **活动日志**：每条批量操作自动记录 activity_log 条目
- **底部摘要**：格式 "本次更新了N个任务, 其中紧急a个，进行中b个，已完成c个，逾期d个"

### 编辑器重构
- **默认格式变更**：`- [ ]  <YYYY-MM-DD HH:MM> 新任务 #标签`（当前时间、标签必填）
- **分栏布局**：左侧 Markdown 编辑器 + 右侧预览（可切换显示/隐藏）
- **标签必填验证**：保存时检查 `parsed.tags` 非空，否则弹出警告
- **日期/时间组件统一**：创建时间和截止时间均使用 `QDateEdit` + `QTimeEdit`

### 截止区间计算器 (DeadlineIntervalCalculator)
- **临时任务**：当前+1天 / 今天 23:59:59（默认）
- **周任务**：本周X / 下周X，X 可选（默认周五）
- **月任务**：本月末 / 自然月（默认本月末）
- **自动同步**：选择后点击"应用建议" → 更新截止日期+时间选择器

### 多任务创建 (MultiTaskDialog)
- **下拉菜单**：新建按钮改为 `MenuButtonPopup` → 新增单任务/新增多任务
- **多行输入**：文本区域一次输入多行 Markdown 任务
- **共享时间**：所有任务使用相同的创建时间和截止时间
- **批量导入**：保存时按换行符拆分，逐行解析并插入

### 其他
- **suspended 列**：tasks 表新增 `suspended INTEGER` 列，独立于状态枚举
- **StatusBadgeStrip**：保留 4 状态计数徽章（逾期/待办/进行中/已完成），支持点击筛选
- **SignalBus 扩展**：`batch_operation_completed`、`tasks_bulk_created` 信号
- **交叉刷新**：任务状态变更 → 速览栏+进度栏+任务表+状态栏联动刷新

## 开发进度

| Sprint | 内容 | 状态 |
|--------|------|------|
| Sprint 1 | 领域模型、Markdown 解析/格式化、Repository、测试套件 | ✅ |
| Sprint 2 | 应用骨架（app.py、config.py、main_window、system_tray、QSS） | ✅ |
| Sprint 3 | 任务列表组件（输入、列表、筛选、右键菜单、编辑面板） | ✅ |
| Sprint 4 | 日历热力图（日级活跃度、颜色映射、年份切换、点击筛选） | ✅ |
| Sprint 5 | 对话框、导入导出、通知、归档、循环任务 | ✅ |
| Sprint 6 | 活动时间线、状态统计栏、轮播横幅、草稿模式、UI 统一优化 | ✅ |
| Sprint 7 | 分区管理、截止时间日历、编辑器折叠、时间线重构、统计联动、密码保护、自动锁定 | ✅ |
| Sprint 8 | 速览栏、进度动态栏、批量操作、编辑器分栏、截止区间计算器、多任务创建、状态徽章条 | ✅ |

**测试覆盖**：57 用例（parser 20 + formatter 7 + repository 21 + task 7），全部通过。

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
uv run pyinstaller --name="DeskTodoSeq" --windowed --onefile --icon="resources/icons/app.ico" --add-data="resources;resources" main.py
```

## 参考

- [Todoseq](https://github.com/nicepkg/todoseq) — Markdown 任务格式规范
- [Org-mode](https://orgmode.org/) — 状态流转设计理念
- [GitHub Contribution Graph](https://docs.github.com/en/account-and-profile) — 热力图可视化灵感
- [Qt Framework](https://www.qt.io/) — PySide6 跨平台 GUI
- [SQLite FTS5](https://www.sqlite.org/fts5.html) — 内置全文搜索

> 本项目仅供个人学习与实践使用。
