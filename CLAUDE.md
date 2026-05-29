# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在本仓库中工作时提供指导。

## 项目概览

DeskTodoSeq 是一个 Windows 桌面任务管理工具，Python 3.10 + PySide6 构建。任务完全使用 Markdown 语法定义和编辑（兼容 Todoseq 格式），SQLite 存储 + FTS5 全文搜索，配备日历热力图可视化。

## 常用命令

```bash
# 环境搭建
uv venv --python 3.10 .venv
uv sync                         # 仅生产依赖
uv sync --dev                   # 生产 + 开发依赖

# 开发时运行
uv run python main.py

# 测试
uv run pytest                                 # 全部测试
uv run pytest tests/test_md_parser.py         # 单个测试文件
uv run pytest tests/test_md_parser.py::TestParseStandard::test_full_format  # 单个用例
uv run pytest -k "round_trip"                 # 按关键字匹配

# 代码质量
uv run black src/ tests/                      # 格式化
uv run ruff check src/ tests/                 # lint 检查
uv run ruff check --select=F src/             # 仅 pyflakes 规则

# 构建打包
# 免安装便携版：
#   执行 build.bat（调用 Nuitka --standalone），输出到 dist/main.dist/

# 安装版（用户可选路径，需先安装 Inno Setup）：
#   1. 执行 build.bat
#   2. 用 Inno Setup Compiler 打开 installer.iss 编译 → 生成 Setup.exe
```

## 架构

### 包分层

```
src/
  models/    领域模型：Task、TaskStatus、Priority、TaskFilter、TaskRepository（SQLite 访问层）
  services/  业务逻辑：md_parser（Markdown → 结构化字段）、md_formatter（结构化字段 → Markdown）
  ui/        PySide6 界面：main_window、system_tray、task_list/、calendar_heatmap/、dialogs/
  utils/     横切工具：signal_bus（Qt 信号总线）、date_utils、win32_utils
```

### 核心数据流

每个任务以 Markdown 行创建，以两种形式存储在 SQLite 中：

```
"- [ ] TODO [#A] <2026-05-20> 重构认证模块 #backend"  ← 用户输入
        │
        ▼  MarkdownTaskParser.parse() 解析
ParsedTask(status=TODO, priority=A, deadline=date(2026,5,20), title="重构认证模块", tags=["backend"])
        │
        ▼  MarkdownTaskFormatter.format() 规范化
Task(raw_md="- [ ] TODO [#A] <2026-05-20> 重构认证模块 #backend", title="重构认证模块", ...)
        │
        ▼  TaskRepository.insert() 入库
SQLite（raw_md 原文 + 解析后的结构化列 + FTS5 索引）
```

编辑时：用户修改 raw_md → 重新解析 → raw_md 和结构化字段同步更新。

### 核心设计决策

- **`raw_md` 是规范数据源** — 结构化字段（`title`、`status`、`priority`、`dates`、`tags`）从 raw_md 派生，始终可通过 `MarkdownTaskParser` 重新生成。
- **`MarkdownTaskFormatter.format()` 输出稳定** — 相同字段总是生成相同的 raw_md 字符串。`test_md_formatter.py::TestRoundTrip` 中的往返测试验证了这一不变性。
- **FTS5 全文搜索** 作用于 `raw_md, title, notes, tags` 列 — 全文查询走虚拟表而非 `LIKE` 扫描。
- **SignalBus 解耦各模块** — 服务和 UI 组件通过 Qt 信号（`task_created`、`task_updated`、`task_deleted`、`reminder_fired` 等）通信，而非模块间直接调用。
- **后台服务已实现** — `scheduler.py`（APScheduler 定时检查到期任务）、`notifier.py`（托盘提醒，尊重安静时段）、`archiver.py`（每日自动归档已完成任务）、`recurrence.py`（循环任务自动创建下一实例）。

### 任务状态循环

```
TODO → DOING → DONE → TODO
OVERDUE → (修改截止日) → DOING
```

点击状态标签即调用 `TaskStatus.next_status` 推进状态，formatter 重新生成含新关键字和复选框的 raw_md。OVERDUE 状态由系统自动设置（截止日过期），不可手动更改。

### SQLite 要点

- 标签以 JSON 数组字符串存储（`'["tag1","tag2"]'`），过滤时用 `LIKE '%"tag"%'` 匹配。
- `notification_log` 用复合主键 `(task_id, interval_minutes)` 去重 — 同一任务+同一时间粒度的通知不会重复发送。
- Repository 用 `check_same_thread=False` 打开连接，因为 Qt 信号可能从任意线程触发回调。

## UI 组件规范

### QComboBox 下拉列表样式

- **紧凑宽度**：使用 `setFixedWidth()` 或紧凑的 `min-width`，刚好容纳最长选项 + 下拉箭头 + 少量 padding，不留多余空白
  - 中文字号 12px 时每个字约 12px 宽，2 个字 ≈ 24px + 左 padding 8px + 下拉区 18px ≈ 50px，取 48px
- **加粗规则**：位于菜单栏（`QMenuBar`）或工具栏（`QToolBar`）中的 QComboBox，其选中项文本加粗（`font-weight: bold`）；其余位置（对话框、面板等）默认不加粗
- **下拉箭头**：QSS 中 `QComboBox::down-arrow` 使用自定义 SVG 图标（`resources/icons/chevron-down-{light,dark}.svg`），避免 Windows 原生样式在暗色主题下箭头不可见
  - 暗色主题：`chevron-down-light.svg`（`#c9d1d9`）
  - 亮色主题：`chevron-down-dark.svg`（`#555`）
- **图标路径**：QSS 中用 `url(__ICONS__/chevron-down-*.svg)` 占位符，`app.py` 加载时自动替换为实际 icons 目录绝对路径
- **弹出列表**：`QComboBox QAbstractItemView` 必须显式设置 `color` 属性（暗色 `#c9d1d9` / 亮色 `#2c2c2c`），确保选项文字可见

### QPushButton 小导航按钮

- 小导航按钮（`<` `>` `◀` `▶`）使用 `objectName="navBtn"`，QSS 规则：`padding: 2px 4px; font-size: 11px; min-width: 24px; min-height: 24px;`
- 全局 QPushButton 的 `padding` 不宜过大（当前 `5px 10px`），否则 `setFixedWidth(28)` 的小按钮文字会被挤出可视区

### 主题颜色

- 所有组件颜色优先使用 `design_tokens.py` 的 `get_tokens()`，避免硬编码色值
- `QPalette` 必须设置在 `QApplication.instance()` 级别（非 MainWindow），使弹出窗口（QComboBox 下拉列表等）继承正确的调色板

## PEP8 命名规范

| 对象类型 | 规范 | 示例 |
|---------|------|------|
| 模块/文件 | `snake_case` | `task_list_model.py`、`md_parser.py` |
| 包 | `snake_case`，短小 | `ui/`、`models/`、`services/` |
| 类 | `PascalCase` | `TaskRepository`、`MarkdownTaskParser` |
| 函数/方法 | `snake_case` | `parse_line()`、`get_by_id()` |
| 变量 | `snake_case` | `raw_md`、`scheduled_date` |
| 常量 | `UPPER_SNAKE_CASE` | `TASK_LINE_PATTERN` |
| 私有成员 | 前缀 `_` | `_repository`、`_update_fts()` |
| Qt 信号 | 过去式动词 | `task_created`、`status_changed` |

## 当前进度

**已完成（全部 Sprint）**：

- **Sprint 1**：models（Task/TaskStatus/TaskFilter/TaskRepository）、Markdown 解析器/格式化器、SignalBus、date_utils、测试套件
- **Sprint 2**：app.py、config.py、main_window（frameless 自定义标题栏 + Win32 拖拽）、system_tray、light/dark 主题 QSS、main.py
- **Sprint 3**：TaskInputWidget、FilterBar、TaskListModel、TaskListDelegate、TaskListView、TaskListPanel、TaskEditPanel、AboutDialog
- **Sprint 4**：HeatmapModel、CalendarHeatmapWidget（12 月×7 行×5 列矩阵布局、accent 单色渐变）、HeatmapTooltip、HeatmapCollapsePanel、ActivityReportPanel、ReportExporter
- **Sprint 5**：SettingsDialog、导入/导出 Markdown、TaskScheduler、TaskNotifier、TaskArchiver、TaskRecurrence
- **Sprint 6**：活动时间线、StatusBadgeStrip、草稿模式、编辑区折叠、进度追踪（ProgressDynamicsBar）
- **Sprint 7**：分区管理（密码保护+自动锁定）、截止时间日历（CalendarPopup/TimePopup）、时间线重构、统计联动
- **Sprint 8**：速览栏（QuickOverviewBar）、批量操作（BatchToolbar）、编辑器分栏重构、截止区间计算器（DeadlineCalculator）、多任务创建（MultiTaskDialog）、suspended 列、DropdownWidget、widget_utils（combo_width）
- **已移除**：Priority 系统（合并到 status）、CarouselBanner（被 QuickOverviewBar 替代）、TaskDialog（被 TaskEditPanel 替代）、热力图点击/拖选/右键交互（数据源不匹配）

**测试覆盖**：parser（20 用例）、formatter（7 用例）、repository（21 用例）、task（7 用例）— 共 57 用例全部通过。

**依赖安装**：PySide6 的 wheel 包约 160MB，网络慢时可能超时。失败时用 `UV_HTTP_TIMEOUT=300 uv sync` 重试。

## 工作流程规则

### 1. 优化验证与活动记录

所有测试和优化问题均需按功能模块创建 TODO 任务，并在对应任务的**活动时间线**记录优化信息：
- 作用一：验证软件功能，确保优化完成且无回归
- 作用二：检查软件使用缺陷，促进软件迭代更新

### 2. 避免历史问题复现

当前优化不能引起历史已解决问题再次复现。若当前需求与历史需求出现**重大冲突**，需整理以下内容并向用户沟通确认，确认后归档保存（可在"测试分区"以"需求变更"为标签记录）：
- 历史需求
- 当前需求
- 冲突点
- 推荐的解决方案

### 3. 复用成熟技术栈

项目开发中尽可能复用已有成熟的技术栈，避免重复造轮子。优先检索开源、可靠、可复用的项目和组件。

### 4. 新增需求：推荐成熟设计方案

在设计阶段推荐比较成熟的设计方案，避免仅解决当前问题而不兼顾全局，导致整体功能因局部设计不合理而影响后续扩展和优化。

### 5. 待办与任务拆分

当前因需求不明或技术实现复杂的问题，可以以待办（TODO）、任务拆分的方式进行备忘、分步完成，避免阻塞整体进度。

### 6. 主题色适配

系统设计中涉及主题色适配：所有 UI 交互、组件选择、logo 设计、配色等问题，均需严格遵守 `design_tokens.py` 的设计令牌体系。暗色/亮色主题必须同时适配。

### 7. 全局一致性与设置验证

功能开发必须保证全局一致。与设置（Config）有关的配置信息，需验证是否在全局生效。若存在需求不明或不确定的情况，主动向用户确认。

### 8. 开发环境与生产环境隔离

严格区分开发环境和生产环境：
- **生产环境**：仅存在"功能演示分区"，"工作"、"个人"、"学习"为默认分区名称但无对应任务
- **打包时以生产环境的包为主**，避免项目信息泄露
- 开发环境和生产环境使用不同的数据库和配置

### 9. 自行模拟测试

每次优化完成后，**必须自行模拟启动应用并测试对应优化项**，确保功能正常：
1. 通过 `timeout 5 uv run python main.py` 验证应用能正常启动（无异常退出）
2. 根据本次优化内容，检查相关功能是否能正常触发和执行
3. 若发现错误，立即修复并重新测试，直到通过为止
4. 测试通过后，告知用户"自测完成"，由用户进行再次测试和确认

### 10. 优化完成确认与备份

1. 自测完成并告知用户后，等待用户测试确认和反馈
2. 用户确认问题已解决后，**必须先通过 `git commit` 提交当前代码作为备份**，再进行下一个任务的修改

## 当前进度（按功能模块）

### 任务列表（TaskListView / TaskListModel / TaskListDelegate）
- ✅ Markdown 格式任务展示（8 列：复选框、序号、创建时间、内容、截止日、进度、状态、标签）
- ✅ 状态行颜色标识（TODO/DOING/DONE/OVERDUE）
- ✅ 行选择 + 多选 + 批量操作工具栏
- ✅ 分页（20/50/100）+ 排序
- ✅ Suspended 列（视觉 dimming）
- 待办：拖拽排序、列宽记忆

### 编辑任务（TaskEditPanel）
- ✅ Markdown 源码编辑 + 实时预览
- ✅ 草稿模式（蓝色高亮、自动聚焦）
- ✅ 截止日历选择器（CalendarPopup）+ 时间选择器（TimePopup）
- ✅ 活动时间线（activity_log 编辑 + 锁定）
- ✅ 分区选择器
- 待办：标签快捷插入、Markdown 语法提示

### 底部状态栏（StatusBar）
- ✅ 任务总数 + 筛选状态
- ✅ 分页信息
- ✅ 闲置自动锁定计时

### 搜索栏（FilterBar）
- ✅ 全文搜索（FTS5）
- ✅ 状态筛选（Dropdown）
- ✅ 排序切换

### 统计栏
- ✅ StatusBadgeStrip：按状态统计 + 点击筛选
- ✅ ProgressDynamicsBar：昨日/今日/本周/本月进度动态
- ✅ 速览栏（QuickOverviewBar）：预设时间范围 + 循环轮播

### 热度日历（CalendarHeatmapWidget）
- ✅ 12 月 × 7 行 × 5 列矩阵布局
- ✅ Accent 单色渐变（activity_log 数据源）
- ✅ 悬浮 tooltip（HeatmapTooltip）
- ✅ 年份导航 + 标签筛选
- ✅ 速览栏联动高亮
- ✅ 活动报告面板（ActivityReportPanel）+ 导出（Markdown/Excel）
- ✅ 折叠面板（HeatmapCollapsePanel）
- ❌ 已移除：点击筛选、拖选范围、右键菜单（数据源不匹配）

### 分区管理
- ✅ 分区 CRUD（设置对话框）
- ✅ 分区切换（DropdownWidget）
- ✅ 密码保护 + 自动锁定
- ✅ 闲置计时器自动锁定
- ✅ 默认分区设置

### 设置对话框（SettingsDialog）
- ✅ 通用（语言、开机启动、最小化到托盘、闲置锁定时间）
- ✅ 显示（主题、字号、热力图起始年份、配色）
- ✅ 自动化（提醒间隔、安静时段、归档）
- ✅ 分区管理（CRUD + 密码）

### 系统托盘（SystemTray）
- ✅ 托盘图标 + 右键菜单（显示/隐藏、新建任务、退出）
- ✅ 双击托盘显示/隐藏
- ✅ 提醒通知弹窗

### 后台服务
- ✅ TaskScheduler：APScheduler 定时检查到期任务
- ✅ TaskNotifier：托盘提醒（尊重安静时段）
- ✅ TaskArchiver：每日自动归档已完成任务
- ✅ TaskRecurrence：循环任务自动创建下一实例

### 导入/导出
- ✅ 导入 Markdown 文件
- ✅ 导出 Markdown 文件
- ✅ 活动报告导出（Markdown / Excel）

### 窗口管理
- ✅ Frameless 自定义标题栏（VS Code 风格）
- ✅ Win32 原生拖拽 + 边框调整大小
- ✅ 最大化/还原/最小化按钮
- ✅ 初始尺寸屏幕 65%
- 待办：最大化/还原按钮在某些场景下响应异常

### 主题系统
- ✅ Light / Dark 双主题 QSS
- ✅ design_tokens.py 设计令牌体系
- ✅ QPalette 全局设置
- ✅ 主题热切换

### 测试
- ✅ parser（20 用例）、formatter（7 用例）、repository（21 用例）、task（7 用例）— 共 57 用例全部通过
- 待办：UI 自动化测试（pytest-qt）

### 已移除的功能
- ❌ Priority 系统（合并到 TaskStatus）
- ❌ CarouselBanner（被 QuickOverviewBar 替代）
- ❌ TaskDialog（被 TaskEditPanel 替代）
- ❌ 热力图点击/拖选/右键交互（数据源不匹配）
