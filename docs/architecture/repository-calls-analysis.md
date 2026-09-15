# Repository 调用分析

> 统计 Tadado UI 层对 `TaskRepository` 的直接调用，为 `TaskService` 门面收敛提供数据基础。
>
> **本文档为收敛完成后的快照**（2026-09-14）。历史版本曾记录 16 个文件 / 76 处调用；
> 经阶段 2–3 的单缝收敛与全量迁移，**UI 层直接调用已归零**。

## 总览

| 指标 | 收敛前 | 现状 |
|------|--------|------|
| 直连 repository 的 UI 文件 | 16 | **0** |
| 直接 repository 调用点 | 76 | **0** |
| 持有 repository 的 UI 文件（纯宿主） | — | **1**（`main_window.py`） |

## 现状

`MainWindow` 是**唯一**允许持有 `TaskRepository` 的位置：构造注入、创建 `TaskService`、
在关闭流程中随 repository 一起释放。除此之外，UI 层不出现任何 `repository` 读写。

```
UI (widgets / views / dialogs / controllers)
        │  只依赖 TaskService
        ▼
   TaskService ── 单一写缝（save_task / create_task / update_tasks / create_tasks_bulk…）
        │        单一读口（search / count / get_* / get_partition_* / get_heatmap_*…）
        ▼
  TaskRepository ── SQLite 访问
```

## 迁移明细

### 只读部件 → TaskService

| 文件 | 原调用 | 现状 |
|------|--------|------|
| `calendar_heatmap/heatmap_model.py` | `get_heatmap_activity_data` ×3、`get_all_tags` ×2 | 依赖 `TaskService` |
| `calendar_heatmap/task_tree_panel.py` | `search` | 依赖 `TaskService` |
| `calendar_heatmap/calendar_heatmap_widget.py` | 透传宿主 | 依赖 `TaskService` |
| `widgets/tag_management_panel.py` | `update` ×2 回退、`get_all_tags_with_counts`、`get_tasks_by_tag(s)` | 依赖 `TaskService`（必填） |

### 写路径 → 单缝 `save_task`

| 文件 | 原调用 | 现状 |
|------|--------|------|
| `dialogs/task_dialog.py` | `update` / `insert` 回退 + 手工 `bus.emit()` | `save_task(task, is_new=…, previous_status=…)` |
| `task_list/task_edit_panel.py` | `insert`/`update`/`delete` ×8 回退 | 已随文件删除（见下） |
| `dialogs/settings_dialog.py` | 分区管理 6 处回退 | 全部经 `TaskService` |

### 透传宿主清理

| 文件 | 变更 |
|------|------|
| `controllers/batch_controller.py` | 移除 `repository` 参数与 `self._repo` |
| `task_list/task_list_view.py` | 移除 `repository` 参数 |

### 删除的孤儿

| 文件 | 原因 |
|------|------|
| `task_list/task_edit_panel.py` | 任务页已由维护抽屉承载；全项目（含测试）无实例化点 |
| `widgets/status_stats_bar.py` | 仅 `__init__` re-export，无构造点 |
| `calendar_heatmap/activity_report_panel.py` | 仅 `__init__` re-export，无构造点 |
| `dialogs/timeline_detail_dialog.py` | 无实例化点 |
| `task_list/task_list_panel.py` | 无实例化点（任务页已由时间轴承载） |

## 写路径单缝语义

UI 写操作统一经 `TaskService.save_task(task, *, is_new, previous_status)`，
由服务决定发 `task_created` / `task_updated` / `task_status_changed` 之一 —— 保证**每次保存只发一次信号**。
历史上「直接 `repo.update()` + 手工 `bus.emit()`」的双通道已彻底移除。

## 剩余注意事项

- `src/ui/widgets/timeline_view.py`、`src/ui/splash_screen.py` 的注释中提及
  `task_edit_panel._fmt_ts` / `_welcome_bg_path`（说明实现来源）；该文件已删除，
  注释仅作历史参考，两个函数已各自独立实现，无运行时依赖。
- 新增 UI 部件时请直接依赖 `TaskService`，不要再引入 `TaskRepository`。
