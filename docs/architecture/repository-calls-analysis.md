# Repository 调用分析

> 统计 Tadado UI 层对 `TaskRepository` 的所有直接调用（76 处），为 TaskService 接口设计提供数据基础。

## 总览

| 指标 | 数值 |
|------|------|
| 调用 repository 的 UI 文件 | **16** 个 |
| 直接 repository 调用点 | **76** 处 |
| WRITE 调用 | 28 处 |
| READ 调用 | 48 处 |
| 实例化 Parser 的文件 | 5 个 |
| 实例化 Formatter 的文件 | 7 个 |

---

## 写操作分类（28 处）

### 任务 CRUD（8 处）

| 文件 | 方法 | 次数 |
|------|------|------|
| `task_edit_panel.py` | `insert`, `update`, `delete` | 8 |
| `task_input.py` | `insert` | 1 |
| `task_dialog.py` | `update`, `insert` | 2 |
| `timeline_detail_dialog.py` | `update` | 1 |
| `multi_task_dialog.py` | `insert` | 1（循环内） |
| `tag_management_panel.py` | `update` | 2 |

### 批量操作（15 处，全部在 main_window.py）

| 方法 | 说明 |
|------|------|
| `batch_update_status` | 更改状态（2 处） |
| `batch_update_urgency` | 更改优先级 |
| `batch_delete` | 删除（3 处：编辑视图×2 + 清除已归档） |
| `batch_suspend` | 中止（2 处） |
| `batch_restart` | 重启（2 处） |
| `batch_postpone` | 延后处理 |
| `batch_move_partition` | 调整分区 |
| `archive_batch` | 手动归档 |
| `ensure_default_partition` | 首次启动建默认分区 |
| `completed_last` (set) | 设置已完成置底 |

### 分区管理（7 处，全部在 settings_dialog.py）

| 方法 | 说明 |
|------|------|
| `upsert_partition` | 新建/编辑分区（2 处） |
| `delete_partition` | 删除分区 |
| `set_partition_password` | 设置密码（3 处：清空/新建/已有） |
| — | `count_tasks_in_partition`（READ，用于删除校验） |

---

## 读操作分类（48 处）

### 高频：search / search_with_total（12 处）

| 文件 | 方法 | 用途 |
|------|------|------|
| `main_window.py` | `search_with_total` | 数据刷新（2 处） |
| `main_window.py` | `search` | 批量视图×4 |
| `task_edit_panel.py` | `search` | 重复检测 |
| `quick_overview_bar.py` | `search` | 速览预设过滤 |
| `progress_dynamics_bar.py` | `search` | 进展动态过滤 |
| `activity_report_panel.py` | `search` | 活动报告 |
| `task_tree_panel.py` | `search` | 任务树 |
| `task_list_panel.py` | `search` | 独立面板 |

### 中频：统计与聚合

| 文件 | 方法 | 用途 |
|------|------|------|
| `status_badge_strip.py` | `get_status_counts` | 状态徽章计数 |
| `status_stats_bar.py` | `count` | 状态统计 |
| `main_window.py` | `get_status_counts` | 状态栏更新 |
| `main_window.py` | `get_all` | 导入/导出 |
| `main_window.py` | `get_by_id` | 恢复状态 |

### 分区查询（8 处）

| 文件 | 方法 | 用途 |
|------|------|------|
| `main_window.py` | `get_all_partitions` | 加载分区列表（3 处） |
| `main_window.py` | `get_partition_name_map` | ID→名称映射（4 处） |
| `main_window.py` | `check_partition_password` | 密码验证（3 处） |
| `settings_dialog.py` | `get_all_partitions` | 分区表格 |
| `settings_dialog.py` | `check_partition_password` | 密码验证 |
| `settings_dialog.py` | `count_tasks_in_partition` | 删除校验 |

### 标签与热力图（8 处）

| 文件 | 方法 | 用途 |
|------|------|------|
| `heatmap_model.py` | `get_heatmap_activity_data` | 热力图数据（3 处） |
| `heatmap_model.py` | `get_all_tags` | 标签列表（2 处） |
| `tag_management_panel.py` | `get_all_tags_with_counts` | 标签+计数 |
| `tag_management_panel.py` | `get_tasks_by_tag` | 按标签查任务 |
| `tag_management_panel.py` | `get_tasks_by_tags` | 按多标签查任务 |

---

## Parser/Formatter 实例化分布

| 文件 | Parser | Formatter |
|------|--------|-----------|
| `task_edit_panel.py` | ✓ | ✓ |
| `task_list_view.py` | — | ✓ |
| `task_input.py` | ✓ | ✓ |
| `task_dialog.py` | ✓ | ✓ |
| `tag_management_panel.py` | — | ✓ |
| `timeline_detail_dialog.py` | — | ✓ |
| `multi_task_dialog.py` | ✓ | ✓ |
| **合计** | **5 文件** | **7 文件** |

所有实例化均在构造函数中 `self._parser = MarkdownTaskParser()` / `self._formatter = MarkdownTaskFormatter()`，无状态，无需外部依赖。

---

## 迁移优先级

按"改动风险低→高"排序：

| 优先级 | 文件 | 写操作 | 读操作 | 风险 |
|--------|------|--------|--------|------|
| 1 | `task_input.py` | 1 | 0 | 极低 |
| 2 | `multi_task_dialog.py` | 1（循环） | 0 | 低 |
| 3 | `timeline_detail_dialog.py` | 1 | 0 | 低 |
| 4 | `task_dialog.py` | 2 | 0 | 低 |
| 5 | `task_edit_panel.py` | 8 | 1 | 中 |
| 6 | `tag_management_panel.py` | 2 | 3 | 中 |
| 7 | `settings_dialog.py` | 7 | 3 | 高 |
| 8 | `main_window.py` | 15 | 20 | **最高** |
| 9 | 其余 8 个只读文件 | 0 | 20 | 低 |
