# 架构审查报告

> 2026-06-29 · 基于 `/improve-codebase-architecture` 技能扫描 Tadado 代码库（45 源模块、~18k 行、PySide6 + SQLite）得出。

## 术语

| 术语 | 定义 |
|------|------|
| **模块** | 任何有接口和实现的东西——函数、类、包 |
| **接口** | 调用方使用模块需知的一切：类型签名、不变量、约束、错误模式 |
| **深度** | 接口后的行为量 / 接口复杂度。深模块 = 小接口 + 大实现 |
| **接缝** | 模块接口所在的位置——可以不动该处代码而改变行为的地方 |
| **适配器** | 在接缝处满足接口的具体事物 |
| **杠杆** | 调用方从深度中获得的收益：更多能力，更少学习 |
| **局部性** | 维护者从深度中获得的收益：修改、bug、知识集中一处 |

## 候选总览

| # | 候选 | 强度 | 核心摩擦 |
|---|------|------|---------|
| 1 | Repository 反向导入 Service | 强烈建议 | 数据层 4 处 lazy-import 服务层——层次倒置 |
| 2 | MainWindow 上帝模块 | 强烈建议 | 2,466 行、100+ 方法、8+ 不相关职责 |
| 3 | 缺少 Service 门面 | **强烈建议 ★** | 22 UI 文件 76 处直调 repository，7 文件各自 new Parser/Formatter |
| 4 | SignalBus 单例不可注入 | 值得探索 | 模块级全局单例，测试间信号泄漏 |
| 5 | Service 与 Qt 硬耦合 | 值得探索 | 5/6 Service 在构造函数创建 Qt 依赖——零测试 |
| 6 | `__init__.py` 重导出不一致 | 探索性 | 5 个包部分重导出，`widgets/` 最严重（2/12） |

## 候选详情

### #1 Repository 反向导入 Service（层次倒置）

**文件**：`src/models/repository.py`、`src/services/md_formatter.py`

**问题**：`repository.py` 在 4 个批量方法内延迟导入 `MarkdownTaskFormatter`——数据层向上触及服务层。

```python
# batch_update_status, batch_update_urgency, batch_postpone, refresh_overdue_status 中:
from ..services.md_formatter import MarkdownTaskFormatter
formatter = MarkdownTaskFormatter()
```

**方案**：引入 TaskService（#3）后，批量操作协调逻辑上移，repository 不再需要 formatter。

**收益**：
- 局部性：批量+格式逻辑集中一处
- 可测性：注入 formatter，独立测试
- 接口缩小：repository 减去 4 个感知格式化的方法

---

### #2 MainWindow 上帝模块

**文件**：`src/ui/main_window.py`（2,466 行）

**问题**：承载 8 种不相关职责：窗口生命周期、批量操作、分区管理、筛选排序、热力图协调、空闲锁、信号连线、快捷键。

**方案**：提取 `BatchController`、`PartitionController`、`DashboardController`、`FilterCoordinator`——每个以干净小接口暴露在接缝处。

**收益**：
- 局部性：改批量不担心破坏热力图
- 可测性：控制器脱离窗口测试
- 杠杆：每个控制器暴露约 3 个方法

---

### #3 缺少 Service 门面（★ 拱心石）

**文件**：`src/ui/`（22 文件）、`src/models/repository.py`、`src/services/md_parser.py`、`src/services/md_formatter.py`

**问题**：
- 76 处 `self._repository.*` 直调散布在 22 个 UI 文件
- 7 个 UI 文件各自 `new MarkdownTaskParser()` / `new MarkdownTaskFormatter()`
- 无统一入口实施约束、发射信号、协调副作用

**方案**：引入 `TaskService` 作为 UI 与数据层之间的唯一接缝。持有 repository、formatter、parser、signal bus——所有 UI 通过同一接口。

**收益**：
- 杠杆：22 调用方 → 1 接口
- 局部性：副作用集中在 Service
- 可测性：mock 一个接缝，测所有 UI 逻辑
- 深度：小接口，大量协调逻辑

---

### #4 SignalBus 单例不可注入

**文件**：`src/utils/signal_bus.py`（63 行）

**问题**：`get_signal_bus()` 返回模块级单例，12+ 模块直接调用。测试间信号连接持久存在，无法隔离。

**方案**：保留 `get_signal_bus()` 作为便利默认，所有地方增加构造函数注入 `SignalBus` 参数。

**收益**：
- 可测性：每用例独立 bus
- 接缝：生产 bus ＋ 测试 bus

---

### #5 Service 与 Qt 硬耦合

**文件**：`src/services/scheduler.py`、`archiver.py`、`notifier.py`、`recurrence.py`、`update_checker.py`

**问题**：构造函数内创建 `QtScheduler`、连接 `SignalBus` 单例、接收 Qt 控件。无 QApplication 无法实例化——5/6 Service 零测试。

**方案**：引入适配器接缝：`SchedulerAdapter`、`NotifyAdapter`。构造函数注入。测试用桩适配器。

**收益**：
- 可测性：5 个 Service 首次可测
- 适配器：生产用 Qt，测试用桩

---

### #6 `__init__.py` 重导出不一致

**文件**：5 个包的 `__init__.py`

| 包 | 已导出 | 总计 | 缺失 |
|------|--------|------|------|
| services/ | 6 | 7 | UpdateChecker |
| dialogs/ | 3 | 5 | MultiTask, TimelineDetail |
| task_list/ | 4 | 6 | BatchToolbar, Delegate |
| widgets/ | 2 | 12 | 10 个公开组件 |
| calendar_heatmap/ | 6 | 10 | 4 个模块 |

**方案**：全导出或全不导出，统一规则。

**收益**：导入路径可预测文件位置，零歧义。

---

## 量化指标

| 指标 | 当前值 | 目标 |
|------|--------|------|
| 层次违规数 | 4（repo→service） | 0 |
| UI→数据直调路径 | 22 文件 | 0（全走 service） |
| repository 直调点 | 76 处 | 0 |
| 最大模块行数 | 2,466 | <500 |
| 单例全局引用 | 12 处 | 0（全注入） |
| 可测 Service | 1/6 (17%) | 6/6 (100%) |
| 需 mock 接缝数 | 4 | 1 |
| `__init__.py` 不一致包 | 5 | 0 |
