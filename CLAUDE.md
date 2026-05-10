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
uv run pyinstaller --name="DeskTodoSeq" --windowed --onefile --icon="resources/icons/app.ico" --add-data="resources;resources" main.py
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
URGENT → DOING → DONE → URGENT
WAIT → DOING → DONE → WAIT
LATER → TODO → DOING → DONE
```

点击状态标签即调用 `TaskStatus.next_status` 推进状态，formatter 重新生成含新关键字和复选框的 raw_md。

### SQLite 要点

- 标签以 JSON 数组字符串存储（`'["tag1","tag2"]'`），过滤时用 `LIKE '%"tag"%'` 匹配。
- `notification_log` 用复合主键 `(task_id, interval_minutes)` 去重 — 同一任务+同一时间粒度的通知不会重复发送。
- Repository 用 `check_same_thread=False` 打开连接，因为 Qt 信号可能从任意线程触发回调。

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

- **Sprint 1**：models（Task/TaskStatus/Priority/TaskFilter/TaskRepository）、Markdown 解析器/格式化器、SignalBus、date_utils、测试套件
- **Sprint 2**：app.py、config.py、main_window（框架+侧边栏+状态栏）、system_tray、light/dark 主题 QSS、main.py
- **Sprint 3**：TaskInputWidget、FilterBar、TaskListModel、TaskListDelegate、TaskListView、TaskListPanel、TaskDialog、AboutDialog
- **Sprint 4**：HeatmapModel、CalendarHeatmapWidget（自定义绘制 GitHub 风格热力图，含年份导航和点击筛选）
- **Sprint 5**：SettingsDialog、导入/导出 Markdown、TaskScheduler、TaskNotifier、TaskArchiver、TaskRecurrence

**测试覆盖**：parser（20 用例）、formatter（5 用例）、repository（12 用例）— 共 32 用例全部通过。

**依赖安装**：PySide6 的 wheel 包约 160MB，网络慢时可能超时。失败时用 `UV_HTTP_TIMEOUT=300 uv sync` 重试。
