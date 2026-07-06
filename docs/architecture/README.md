# 架构优化文档

> Tadado 项目架构优化记录，包含审查报告、分析数据、决策日志和实施计划。

## 文档索引

| 文件 | 说明 |
|------|------|
| [architecture-review.md](architecture-review.md) | 架构审查报告 — 6 个深化候选及其价值分析 |
| [repository-calls-analysis.md](repository-calls-analysis.md) | Repository 调用分析 — 76 处 UI→数据层直调映射 |
| [decisions-task-service.md](decisions-task-service.md) | TaskService 设计决策日志 — 7 轮追问结论 |
| [prd-task-service.md](prd-task-service.md) | TaskService PRD — 背景、方案、实施计划、测试策略 |

## 相关文档

- [DESIGN.md](../../DESIGN.md) — 项目功能设计说明
- [CLAUDE.md](../../CLAUDE.md) — 运行时 AI 指令
- [CHANGELOG.md](../../CHANGELOG.md) — 版本更新日志

## 优化路线图

```
Phase 1: TaskService 引入（拱心石）                           ✅ 完成
  └─ 新建 TaskService，不切断旧路径
  └─ 全套单元测试（41 用例）

Phase 2: 逐文件迁移写操作                                      ✅ 完成
  └─ 9 个文件：task_input → multi_task_dialog → ... → main_window
  └─ 所有写操作 + 信号发射走 TaskService

Phase 3: 查询迁移 + 清理                                       ✅ 完成
  └─ main_window 20 处读取全部切到 service
  └─ 6 个 UI 文件 Parser/Formatter 改用 service._parser/_formatter
  └─ repository.py 4 处 formatter lazy-import 改为可选注入参数
  └─ scheduler/app startup 走 service.refresh_overdue_status

#6 __init__.py 统一                                            ✅ 完成
  └─ 5 个包全部重导出所有公开符号

#2 MainWindow 拆分                                             ✅ 完成
  ├─ PartitionController (~200 行) — 分区生命周期
  ├─ DashboardController (~270 行) — 仪表盘+分析
  ├─ BatchController (~420 行) — 批量操作+管理控制台
  └─ FilterCoordinator (~250 行) — 数据刷新核心
  MainWindow: 2,486 → 2,035 行（-451 行）

剩余工作:
  └─ MainWindow 死代码清理（~500 行旧方法）
  └─ 7 个只读 widget 文件仍用 repository（低优先级）
  └─ #5 Service 去 Qt 耦合
```
