# PRD: TaskService 门面模块

> 版本: v1.0 · 日期: 2026-06-29 · 状态: 待实施

## 目录

1. [背景与动机](#1-背景与动机)
2. [当前状态分析](#2-当前状态分析)
3. [设计决策](#3-设计决策)
4. [接口设计](#4-接口设计)
5. [实施计划](#5-实施计划)
6. [测试策略](#6-测试策略)
7. [风险与缓解](#7-风险与缓解)
8. [DESIGN.md 约束验证](#8-designmd-约束验证)

---

## 1. 背景与动机

### 1.1 问题

Tadado 当前架构中，UI 层**绕过服务层直接调用数据层**：

- **22 个 UI 文件** 包含 76 处 `self._repository.*` 直接调用
- **7 个 UI 文件** 各自 `new MarkdownTaskParser()` / `new MarkdownTaskFormatter()`
- **零集中约束**——没有统一的地方实施业务规则、发射信号、协调副作用
- **Repository 层次违规**——4 个批量方法内 `lazy-import` 服务层的 `MarkdownTaskFormatter`

### 1.2 目标

在 `src/services/` 下新增 `task_service.py`，作为 **UI 层与数据层之间的唯一接缝**。一个模块承载 CRUD、批量操作、查询、分区管理、格式化——22 个 UI 调用方共享同一条接缝。

### 1.3 价值

| 维度 | 改造前 | 改造后 |
|------|--------|--------|
| UI→数据调用路径 | 22 个文件各自 import repository | 22 个文件 import 同一个 service |
| 直接 repository 调用 | 76 处 | 0 |
| Parser/Formatter 实例 | 7 处各自 new | 1 处（service 内部） |
| 信号发射责任 | 分散在 UI 各组件 | 集中在 service |
| 需 mock 的接缝 | 4（repo+fmt+parse+bus） | 1（service） |
| 层次违规 | 4 处 repo→service | 0 |

---

## 2. 当前状态分析

> 详细数据见 [repository-calls-analysis.md](repository-calls-analysis.md)

### 2.1 调用分布

```
写操作 (28 处):
  main_window.py         15  (批量操作 + 分区)
  task_edit_panel.py      8  (CRUD)
  settings_dialog.py      7  (分区管理)
  tag_management_panel.py 2  (update)
  task_dialog.py          2  (CRUD)
  task_input.py           1  (insert)
  timeline_detail_dialog  1  (update)
  multi_task_dialog.py    1  (insert 循环)

读操作 (48 处):
  main_window.py         20  (search, partitions, status)
  heatmap_model.py        5  (heatmap, tags)
  tag_management_panel    3  (tags)
  其余 8 个文件            20  (search, count, status_counts)
```

### 2.2 架构图（Before）

```
┌─────────────────────────────────────────────┐
│  UI 层 (22 文件)                              │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────────┐   │
│  │MainWin│ │EditPnl│ │Dialog│ │Heatmap...│   │
│  └──┬───┘ └──┬───┘ └──┬───┘ └────┬─────┘   │
│     │        │        │          │          │
│     ↓ 76 处 self._repository.* 直接调用       │
├─────────────────────────────────────────────┤
│  数据层                                       │
│  ┌──────────────────────────┐                │
│  │    TaskRepository         │ ← 4 处 lazy   │
│  │    (SQLite CRUD + FTS5)  │   import      │
│  └──────────────────────────┘   ↓           │
├─────────────────────────────────────────────┤
│  服务层 (仅后台定时)                            │
│  ┌──────────────────────────┐                │
│  │  MarkdownTaskFormatter   │                │
│  └──────────────────────────┘                │
└─────────────────────────────────────────────┘
```

---

## 3. 设计决策

> 详细决策过程见 [decisions-task-service.md](decisions-task-service.md)

| # | 决策 | 结论 |
|---|------|------|
| 1 | 方法面 | 单门面，全纳入（~30 方法） |
| 2 | 单门面 vs 拆分 | 单门面 |
| 3 | Parser/Formatter | 内部持有 |
| 4 | 信号发射 | Service 统一发 |
| 5 | 迁移策略 | 渐进 3 Phase |
| 6 | 测试策略 | 真实 SQLite + pytest-qt |
| 7 | repository lazy-import | 删除，Service 接管 raw_md 回写 |

---

## 4. 接口设计

### 4.1 构造函数

```python
class TaskService:
    def __init__(
        self,
        repository: TaskRepository,
        signal_bus: SignalBus | None = None,
    ):
        self._repo = repository
        self._bus = signal_bus or get_signal_bus()
        self._parser = MarkdownTaskParser()       # 内部持有
        self._formatter = MarkdownTaskFormatter()  # 内部持有
```

**要点**：
- `signal_bus` 默认使用全局单例，测试可注入新实例——顺手解决 #4 候选
- Parser/Formatter 内部持有——它们无状态、无外部依赖

### 4.2 任务 CRUD

```python
def create_task(self, raw_md: str, partition_id: str = "") -> Task:
    """解析 Markdown → 创建 Task → insert → emit task_created → 返回 Task"""

def update_task(self, task: Task) -> Task:
    """更新 Task → 重建 raw_md → update → emit task_updated → 返回更新后 Task"""

def delete_task(self, task_id: str) -> None:
    """删除 Task → emit task_deleted"""

def get_task(self, task_id: str) -> Task | None:
    """按 ID 查询"""
```

### 4.3 批量操作

```python
def batch_update_status(self, task_ids: list[str], status: TaskStatus) -> int:
    """批量更改状态 → 重建 raw_md → emit batch_operation_completed"""

def batch_update_urgency(self, task_ids: list[str], urgency: int) -> int:
    """批量更改优先级 → 重建 raw_md → emit batch_operation_completed"""

def batch_delete(self, task_ids: list[str]) -> int:
    """批量删除 → emit batch_operation_completed"""

def batch_suspend(self, task_ids: list[str]) -> int:
    """批量中止"""

def batch_restart(self, task_ids: list[str]) -> int:
    """批量重启"""

def batch_postpone(self, task_ids: list[str], days: int) -> int:
    """延后处理 → 调整 deadline_date → 刷新逾期状态 → 重建 raw_md"""

def batch_move_partition(self, task_ids: list[str], to_partition_id: str) -> int:
    """迁移分区"""

def archive_batch(self, task_ids: list[str]) -> int:
    """手动归档"""

def ensure_default_partition(self) -> str:
    """确保存在默认分区，返回分区 ID"""
```

### 4.4 任务查询

```python
def search(self, filter_: TaskFilter) -> list[Task]:
    """按条件查询任务列表"""

def search_with_total(self, filter_: TaskFilter) -> tuple[list[Task], int]:
    """查询 + 返回总数（用于分页）"""

def get_all(self) -> list[Task]:
    """获取全部任务"""

def get_status_counts(self, partition_id: str | None = None) -> dict[str, int]:
    """按状态统计数量"""

def count(self, filter_: TaskFilter) -> int:
    """计数"""
```

### 4.5 分区管理

```python
def get_all_partitions(self) -> list[Partition]:
    """获取全部分区"""

def get_partition_name_map(self) -> dict[str, str]:
    """ID → 名称映射"""

def upsert_partition(self, name: str, partition_id: str | None = None) -> str:
    """新建或编辑分区，返回分区 ID"""

def delete_partition(self, partition_id: str) -> None:
    """删除分区（校验：非最后一个、非空）"""

def set_partition_password(self, partition_id: str, password: str) -> None:
    """设置/清除分区密码"""

def check_partition_password(self, partition_id: str) -> bool:
    """验证分区密码"""

def count_tasks_in_partition(self, partition_id: str) -> int:
    """分区内任务数"""
```

### 4.6 标签与热力图

```python
def get_all_tags(self, partition_id: str) -> list[str]:
    """获取分区内全部标签"""

def get_all_tags_with_counts(self, partition_id: str) -> dict[str, int]:
    """标签 + 使用次数"""

def get_tasks_by_tag(self, tag: str, partition_id: str) -> list[Task]:
    """按标签查任务"""

def get_tasks_by_tags(self, tags: list[str], partition_id: str) -> list[Task]:
    """按多标签查任务"""

def get_heatmap_activity_data(
    self, year: int, tags: list[str] | None = None, partition_id: str | None = None
) -> tuple[dict, dict]:
    """热力图活动数据"""
```

### 4.7 格式化

```python
def format_task(self, task: Task) -> str:
    """→ MarkdownTaskFormatter.format()"""

def parse_markdown(self, raw_md: str) -> ParsedTask:
    """→ MarkdownTaskParser.parse()"""
```

### 4.8 架构图（After）

```
┌─────────────────────────────────────────────┐
│  UI 层 (22 文件)                              │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────────┐   │
│  │MainWin│ │EditPnl│ │Dialog│ │Heatmap...│   │
│  └──┬───┘ └──┬───┘ └──┬───┘ └────┬─────┘   │
│     │        │        │          │          │
│     └────────┼────────┼──────────┘          │
│              ↓ 全部走 self._service.*        │
├─────────────────────────────────────────────┤
│  服务层                                       │
│  ┌──────────────────────────────────────┐    │
│  │         TaskService (深模块)          │    │
│  │  ┌──────┐ ┌──────┐ ┌──────────────┐ │    │
│  │  │Parser│ │Format│ │ SignalBus    │ │    │
│  │  └──────┘ └──────┘ └──────────────┘ │    │
│  └──────────────┬───────────────────────┘    │
│                 ↓                            │
├─────────────────────────────────────────────┤
│  数据层                                       │
│  ┌──────────────────────────┐                │
│  │    TaskRepository         │                │
│  │    (纯数据访问, 无 formatter 依赖) │         │
│  └──────────────────────────┘                │
└─────────────────────────────────────────────┘
```

---

## 5. 实施计划

### Phase 1: 引入但不切断（预计 2-3 小时）

**目标**：TaskService 存在、可测、已注入——但不改任何 UI 文件。

**步骤**：

1. **新建 `src/services/task_service.py`**
   - 实现全部 ~30 个方法
   - 构造函数注入 repository + signal_bus（默认值 = 全局单例）
   - 内部持有 parser + formatter

2. **新建 `tests/test_task_service.py`**
   - 复用 `conftest.py` 的 `temp_db` fixture
   - SignalBus 可注入——测试用 `pytest-qt` 的 `qtbot`
   - ~30 个测试用例覆盖所有 CRUD + 批量 + 查询 + 分区

3. **更新 `app.py`**
   - 创建 `TaskService` 实例
   - 传给 `MainWindow` 构造函数（新增 `task_service` 参数）
   - MainWindow 存储但**暂不使用**——现有 repository 路径照旧

4. **验证**
   - 运行全部 70+30=100 测试用例
   - 手动启动应用，功能完全不受影响

**交付物**：`task_service.py` + `test_task_service.py` + `app.py`（注入但不切换）

---

### Phase 2: 逐文件迁移写操作（预计 3-4 小时）

**目标**：所有写操作走 service，repository 直调逐步清零。

**迁移顺序**（风险从低到高）：

| 步 | 文件 | 变更 | 验证方式 |
|----|------|------|---------|
| 2.1 | `task_input.py` | `insert` → `service.create_task` | 手动输入一条任务 |
| 2.2 | `multi_task_dialog.py` | 循环 `insert` → `service.create_task` | 手动多任务创建 |
| 2.3 | `timeline_detail_dialog.py` | `update` → `service.update_task` | 编辑活动日志 |
| 2.4 | `task_dialog.py` | `update`+`insert` → service | 对话框编辑保存 |
| 2.5 | `task_edit_panel.py` | 8 处 CRUD → service | **核心路径**，重点验证 |
| 2.6 | `tag_management_panel.py` | `update`+标签查询 → service | 标签重命名/合并 |
| 2.7 | `settings_dialog.py` | 7 处分区 CRUD → service | 分区增删改密码 |
| 2.8 | `main_window.py` | 15 处批量操作 → service | **核心路径**，重点验证 |

**每步操作**：
1. 修改 UI 文件：`self._repository.xxx()` → `self._service.xxx()`
2. 删除文件中已不再需要的 Parser/Formatter 实例化
3. 跑全部测试
4. 手动验证相关功能
5. Git commit（每步一个 commit）

---

### Phase 3: 切查询 + 清理（预计 1-2 小时）

**步骤**：

1. **查询方法迁移**
   - 8 个只读 UI 文件的 `search/get_status_counts` 等 → `service`
   - 删除最后一个 UI 文件中的 Parser/Formatter 实例化

2. **删除 repository 层次违规**
   - 删除 `repository.py` 中 `batch_update_status` 的 formatter lazy-import（Line 832）
   - 删除 `batch_update_urgency` 的 formatter lazy-import（Line 884）
   - 删除 `batch_postpone` 的 formatter lazy-import（Line 985）
   - 删除 `refresh_overdue_status` 的 formatter lazy-import（Line 1138）
   - 这 4 个方法改为纯数据操作——只做 SQL + activity_log，不碰 formatter

3. **raw_md 回写重新安置**
   - TaskService 的 `batch_*` 方法在 repository 返回后，遍历受影响任务
   - 用 `self._formatter.format(task)` 重建 raw_md
   - 用 `self._repo.update(task)` 写回

4. **验证**
   - 全量测试 `uv run pytest`
   - 手动冒烟：CRUD + 批量 + 标签 + 分区 + 热力图
   - 代码质量：`uv run ruff check src/`

---

## 6. 测试策略

### 6.1 TaskService 单元测试

**文件**：`tests/test_task_service.py`（新增）

**风格**：遵循现有惯例——真实 SQLite（`tempfile.mkstemp()`），无 mock。

**Fixture**：
```python
@pytest.fixture
def service(temp_db, qtbot):
    repo = TaskRepository(temp_db)
    bus = SignalBus()  # 可注入，无需 QApp
    return TaskService(repo, bus)
```

**用例覆盖**（预计 30 个）：

| 类别 | 用例 | 验证点 |
|------|------|--------|
| create_task | 标准格式 / 最小格式 / 含标签 / 含截止时间 / 含优先级 | Task 字段正确 + raw_md 已生成 + 数据库可查 + task_created 信号已发射 |
| update_task | 改标题 / 改状态 / 改截止日 / 改优先级 | raw_md 已重建 + task_updated 信号已发射 |
| delete_task | 删除存在 / 删除不存在 | task_deleted 信号 |
| batch_update_status | 1 个 / 多个 / 空列表 | 返回受影响行数 + raw_md 全部刷新 + signal |
| batch_postpone | +1天 / +7天 / 无截止时间（从今天算） | activity_log 格式 `[批量操作] 延后处理: ...` |
| search | 按状态过滤 / 按分区 / 按标签 / 组合条件 | 结果正确 |
| get_status_counts | 空数据库 / 多任务混合状态 | 计数正确 |
| 分区管理 | 新建 / 编辑 / 删除最后一个 / 默认分区 | 错误处理 |

### 6.2 现有测试不受影响

现有 70 个测试用例直接测试 repository/formatter/parser——**TaskService 的引入不改变这些接口**，全部继续通过。

---

## 7. 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| raw_md 回写逻辑迁移遗漏 | 中 | 高——raw_md 是规范数据源 | Phase 3 前逐方法 diff 对比旧新 raw_md 输出 |
| 信号遗漏导致 UI 不刷新 | 中 | 中 | TaskService 每个写方法末尾统一 emit，测试用例逐方法验证信号 |
| main_window.py 迁移出错 | 高 | 高——核心路径 | 最后迁移（Phase 2.8），此时其他文件已验证 service 正确性 |
| 批量操作中 formatter 行为差异 | 低 | 高 | 保持 formatter 调用方式不变，仅改变调用位置 |
| TaskService 成为新上帝对象 | 低 | 中 | 接口方法虽多但每个背后有实质逻辑——不是透传。后续 MainWindow 拆分（#2）会自然分担 |

---

## 8. DESIGN.md 约束验证

| DESIGN.md 约束 | 验证状态 | 说明 |
|----------------|---------|------|
| §1.3 raw_md 是规范数据源 | ✅ 保持 | Formatter 仍是唯一生成入口，调用位置从 repository 移到 TaskService |
| §1.3 SignalBus 解耦 | ✅ 保持 | 信号契约不变，仅发射源从 UI 组件变为 TaskService |
| §1.4 全局信号清单 | ✅ 保持 | `task_created`/`task_updated` 等信号参数不变，监听方无感知 |
| §2.14 批量操作事务+activity_log | ✅ 保持 | Repository 保留事务和日志逻辑，仅删除 raw_md 回写 |
| §2.14 batch_postpone 日志格式 | ✅ 保持 | `[批量操作] 延后处理: 截止时间 {旧} -> {新}（+{N}天）` |
| §1.5 日志规范 | ✅ 保持 | TaskService 在操作边界 INFO 日志，不在循环内逐条 |
| §3.1 Markdown 创建流 | ✅ 保持 | Parse → Task → insert → emit 流程不变，执行方变更 |
| §3.1 编辑保存流 | ✅ 保持 | Parse → Format → Update → emit 流程不变 |
| §3.1 状态循环流 | ✅ 保持 | Status → next_status → Format → Update → emit 流程不变 |

---

## 附录

### A. 相关文档

- [架构审查报告](architecture-review.md) — 6 个候选全貌
- [Repository 调用分析](repository-calls-analysis.md) — 76 处调用明细
- [设计决策日志](decisions-task-service.md) — 7 轮追问记录
- [DESIGN.md](../../DESIGN.md) — 项目功能设计
- [CLAUDE.md](../../CLAUDE.md) — 运行时 AI 指令

### B. 后续优化

完成 TaskService（#3）后，以下候选自然解锁：

1. **#1 层次倒置** — Phase 3 完成时自动解决
2. **#2 MainWindow 拆分** — TaskService 就位后，批量操作、分区管理等可提取为独立控制器
3. **#4 SignalBus 注入** — Phase 1 已顺手解决
4. **#5 Service 去 Qt 耦合** — `SchedulerAdapter`/`NotifyAdapter` 接缝可逐一引入
5. **#6 `__init__.py` 统一** — 低风险独立优化
