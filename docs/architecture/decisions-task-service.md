# TaskService 设计决策日志

> 2026-06-29 · 基于 `/grilling` 技能 7 轮追问的设计决策记录。

---

## 决策 1：方法面 — 全纳入

**问题**：TaskService 应暴露哪些方法？

**结论**：单门面，全纳入——任务 CRUD、批量操作、任务查询、分区管理、标签/热力图查询、格式化，约 30 个方法。

**理由**：
- 即使接口方法多，每个方法背后有实质逻辑（信号发射、raw_md 回写、校验、事务协调）——**深度不来自方法数量**
- 如果拆分（如 TaskService + PartitionService），UI 层又要同时持有两个依赖——回到老问题
- 查询方法也不是纯透传——`search_with_total` 可同时填充缓存，`get_status_counts` 可附加实时计算

**替代方案**：拆分为 TaskService + PartitionService（已否决）

---

## 决策 2：单门面 vs 拆分 — 单门面

**问题**：30 个方法会不会让 TaskService 变成浅模块？

**结论**：选方案 A — 单门面。

**理由**：
- 深度不来自方法数量，来自每个方法背后的行为
- 拆分会导致 UI 同时持有两个依赖
- 分区管理是任务入口，和任务 CRUD 紧密关联

---

## 决策 3：Parser/Formatter — 内部持有

**问题**：Parser/Formatter 是 TaskService 内部持有还是可注入？

**结论**：内部持有。

**理由**：
- Parser 和 Formatter 是无状态纯函数集合，无外部依赖
- `/codebase-design` 原则："一个适配器意味着假设性接缝。两个适配器才意味着真实接缝"
- 目前没有第二个 Parser/Formatter 实现的需求
- 注入只增加签名噪音，无实际收益

**形式**：
```python
class TaskService:
    def __init__(self, repository: TaskRepository, signal_bus: SignalBus):
        self._repo = repository
        self._bus = signal_bus
        self._parser = MarkdownTaskParser()
        self._formatter = MarkdownTaskFormatter()
```

---

## 决策 4：信号发射 — Service 统一发

**问题**：信号发射由 TaskService 负责还是调用方负责？

**结论**：TaskService 统一发射。

**理由**：
- 调用方从"做两件事"变成"做一件事"——接口缩小
- 不会再有"忘了发信号"的 bug——局部性
- 批量操作受益最大：一次操作后发射一个信号，而非 N 个
- DESIGN.md §1.4 定义的信号契约中，监听方（MainWindow, HeatmapWidget 等）无感知，只改变发射源

**当前信号发射方 → 变更后**：
| 信号 | 当前发射方 | 变更后 |
|------|-----------|--------|
| `task_created` | TaskEditPanel, TaskInputWidget, Recurrence | **TaskService** |
| `task_updated` | TaskEditPanel | **TaskService** |
| `task_deleted` | TaskListView, BatchToolbar | **TaskService** |
| `task_status_changed` | TaskEditPanel, BatchToolbar, Recurrence | **TaskService** |
| `batch_operation_completed` | TaskRepository | **TaskService** |
| `tasks_bulk_created` | MultiTaskDialog, TaskEditPanel | **TaskService** |

---

## 决策 5：迁移策略 — 渐进 3 Phase

**问题**：一次性全改还是逐文件迁移？

**结论**：渐进迁移，3 个 Phase，每步可提交可验证。

- **Phase 1** — 引入但不切断：新建 TaskService + 全套测试，注入 app.py，不改 UI 文件
- **Phase 2** — 逐文件切写操作：按风险从低到高，task_input → multi_task_dialog → timeline_detail → task_dialog → task_edit_panel → tag_management → settings → main_window
- **Phase 3** — 切查询 + 收尾：查询方法迁移 + 移除 UI 层 Parser/Formatter 实例化 + 删除 repository 4 处 lazy-import

---

## 决策 6：测试策略 — 真实 SQLite + 顺手解决 SignalBus 注入

**问题**：TaskService 测试用什么策略？

**结论**：复用现有风格——真实 SQLite（tempfile）+ 真实 repository。同时在此次实现中顺手解决 SignalBus 构造函数注入（#4 候选部分内容），测试用 `pytest-qt` 的 `qtbot` 提供 QApplication。

**理由**：
- 与现有 70 个测试用例保持一致（无 mock，真实 SQLite）
- SignalBus 不注入就无法脱离 QApp 创建——这是 TaskService 可测试的前提
- 一举两得

---

## 决策 7：repository lazy-import — 方案 A 删除

**问题**：迁移后 repository.py 的 4 处 formatter lazy-import 如何处理？

**结论**：方案 A — 直接删除。

**与 DESIGN.md 约束验证**：
- ✅ raw_md 仍是规范数据源——formatter 仍是唯一生成入口，只是调用位置从数据层移到服务层
- ✅ SignalBus 解耦——信号契约不变，仅发射源变更
- ✅ 批量操作事务 + activity_log——repository 保留事务和日志逻辑，仅删除 raw_md 回写
- ✅ 日志规范——TaskService 在操作边界记录 INFO 汇总

**替代方案**：B（保留过渡）、C（重构 batch 方法）——已否决
