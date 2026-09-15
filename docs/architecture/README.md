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
  ├─ DashboardController (~270 行) — 仪表盘+分析（⚠ 孤儿，2.0 阶段 4 删除）
  ├─ BatchController (~420 行) — 批量操作+管理控制台
  └─ FilterCoordinator (~250 行) — 数据刷新核心
  MainWindow: 2,486 → 2,035 行（-451 行）

## 2.0 界面重构路线图（7 阶段 · 分轮执行）

UI 原型：`resources/ui-mockup/tadado-2.0.html`（已确认）。架构决策：四层骨架复用；
NavShell+视图注册表、SelectionContext、WindowShell、TaskGraphService；仅 Windows。

```
阶段 1: NavShell + 视图注册表 + 死代码清理                        ✅ 完成（2026-09-12）
  └─ SelectionContext / src/ui/views 注册表（5 页 + 旧名别名）
  └─ NavShell 侧栏（工作/洞察/管理分组 + 设置齿轮 + Ctrl+1..5）
  └─ 死代码清理：-724 行（2,075 → 1,351），午夜崩溃修复
  └─ 测试基建：qapp 上移 conftest（offscreen），169 用例全绿
  └─ 收尾：DB 保全不变量测试 + 无头 MainWindow 冒烟 + 文档同步

阶段 2: TaskService 单缝整合（双路径/双查询消除 + TaskDialog 崩溃）  ✅ 完成（2026-09-12）
  └─ service 新增 save_task / create_tasks_bulk / update_tasks / recalc_activity_counts
  └─ 6 个 UI 文件写路径收敛，`service._repo` / `service._bus` 私有通道清零
  └─ TaskDialog 幻影 _signal_bus 崩溃修复 + 回归测试
  └─ MainWindow 旧刷新管线删除（~20 方法），SignalBus 刷新由 FilterCoordinator 独家订阅
  └─ 分页状态移交 FilterCoordinator（page_changed 信号）
  └─ 189 用例全绿

阶段 3: 时间轴视图替换任务页（TimelineModel + Gantt 委托 + TimelineController）  ✅ 完成（2026-09-14）
  └─ ✅ src/ui/timeline/timeline_model.py（7 粒度 / 裁剪 / 排序 / 状态·搜索·优先级过滤，29 用例，无 Qt）
  └─ ✅ TimelineTableView + Gantt 委托 + TimelineController（总线订阅 + 50ms 去抖 + SelectionContext）
  └─ ✅ 工具行：粒度 / 搜索 / 状态 chips / 优先级 / 排序 / 图例
  └─ ✅ 退役旧列表 + 分页 + FilterCoordinator + FilterBar/StatusBadge/QuickOverview/ProgressDynamicsBar
  └─ ✅ 孤儿清理：MultiTaskDialog / TimelineDetailDialog / task_list_panel

阶段 4: 维护抽屉 + 总览页（焦点时间轴 6 预设）+ AnalysisController        ✅ 完成（2026-09-14）
  └─ ✅ TaskService append_activity / get_recent_activity / get_urgency_distribution / get_due_stats
  └─ ✅ TaskDrawer + 总览页（问候/快建/4 瓦片/焦点时间轴/近期活动/紧迫度）+ 删除 DashboardController
  └─ ✅ 分析页槽迁入 AnalysisController（12 方法 + 导出链路，attach() 注入部件）

阶段 5: WindowShell（RegisterHotKey 全局热键/置顶/托盘收敛）              ✅ 完成（2026-09-14）
  └─ ✅ src/utils/win32_hotkey.py（parse_accel + 注册/注销，51 用例）+ config hotkey/pin_on_top
  └─ ✅ nativeEventFilter 消费 HOTKEY_MESSAGE + 唤醒收敛 + 托盘收 shell + 设置项

阶段 6: 图谱（[[wiki链接]] + TaskGraphService）+ 设置页签化               ✅ 完成（2026-09-14）
  └─ ✅ ParsedTask.links + formatter 往返锁定 + TaskGraphService.build_graph（16 用例）
  └─ ✅ 图谱页改用自绘（非 QGraphicsScene）+ SettingsDialog 页签化

阶段 7: 性能（set-based SQL/刷新去抖/热力图缓存）+ 主题注册表              ✅ 完成（2026-09-14）
  └─ ✅ 批操作 set-based SQL（单事务 executemany）+ 总线刷新 50ms 去抖
  └─ ✅ 热力图 (year,tags,partition) 查询缓存 + 不可见延迟刷新 + 时间轴 dirty 延迟刷新
  └─ ✅ theme_registry 弱引用注册表（替代 MainWindow 逐个列举的 refresh_theme 链）
  └─ ✅ 裸 hex 核查：其余属品牌色 / 启动画面配色 / HTML 文档 CSS，不适用 design_tokens
```

数据保全：全部阶段零 DB 变更（user_version 恒为 8）；测试用临时库。

剩余工作（1.0 遗留）:
  └─ ✅ UI 层 repository 直连归零（76 → 0 处，MainWindow 为唯一宿主）
  └─ ✅ #5 Service 去 Qt 耦合（4 个后台服务全部支持构造注入，21 用例覆盖）
  └─ ⬜ 真机（有显示器）GUI 冒烟验证
```
