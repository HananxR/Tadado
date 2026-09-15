# Tadado 待办任务

> 最后更新：2026-09-15 · 2.0 界面重构（7 阶段 · 分轮执行）
> UI 原型：[resources/ui-mockup/tadado-2.0.html](resources/ui-mockup/tadado-2.0.html)
> 数据保全：全部阶段零 DB 变更（`PRAGMA user_version` 恒为 8）
>
> **2026-09-15 分支分家**：上面「2.0 界面重构」那几条线（阶段 1~7、`docs/architecture/`、
> Python 侧 428 个用例）都随代码归档到了 **`archive/pyversion`** 分支 —— 本分支
> 已无 `src/` `tests/` `docs/`，那几节的链接只对归档分支有效。
> 主线继续追的是文末「🖥 桌面版（`desktop/` · Tauri）工作线」一节。

## ✅ 已完成 — 阶段 1（2026-09-12）

- [x] SelectionContext（分区/选中任务/时段共享上下文）
- [x] 视图注册表（5 页 + 旧视图名别名 edit→tasks 等）
- [x] NavShell 侧栏（工作/洞察/管理分组 + 设置齿轮 + Ctrl+1..5）
- [x] 页面构建逻辑迁出 MainWindow 至 `src/ui/views/`
- [x] 标题栏极简化 + 置顶按钮（本地实现，TODO phase5 迁 WindowShell）
- [x] 午夜崩溃修复（`_refresh_report` 幽灵调用）
- [x] 死代码清理：main_window 2,075 → 1,351 行（-724）
- [x] 测试基建：qapp 上移 conftest（offscreen），修复 QCoreApplication 崩溃；当时 169 用例全绿（现 322）

## ✅ 阶段 1 收尾（2026-09-12）

- [x] **DB 保全抽查**：新增 `tests/test_db_invariants.py` — `user_version` 恒为 8、任务表列不变量、3 条任务 raw_md 往返稳定
- [x] **GUI 冒烟**（无头替代）：新增 `tests/test_main_window_smoke.py` — offscreen 真实构建 MainWindow，覆盖侧栏切页、分页、数据刷新链路；真机（有显示器）验证待补
- [x] **文档同步**：DESIGN.md（新增 1.3.1 导航骨架 + 窗口/快捷键更新）、resources/help/manual.html（侧栏 5 页导航）
- [x] **无头测试基建修复**：`tests/conftest.py` 新增全局 fixture，短路 `QMessageBox` / `QFileDialog` 模态入口（offscreen 无人可点 → `exec()` 永久阻塞，曾致全量 `pytest` 挂死超时）；修正 `test_task_drawer` 任务字符串的日期/标签顺序；387 用例 43s 全绿

## ✅ 阶段 2 — TaskService 单缝整合（2026-09-12）

- [x] TaskService 增 `save_task` / `create_tasks_bulk` / `update_tasks` / `recalc_activity_counts`（均为「信号只发一次」）
- [x] 写路径全收敛：TaskEditPanel / TaskDialog / SettingsDialog / TagPanel / MultiTaskDialog / TimelineDetailDialog 不再触碰 `service._repo` / `service._bus`（无 service 时保留只读回退路径）
- [x] **修复 TaskDialog 幻影 `_signal_bus` 必崩**（task_dialog.py；回归测试 `tests/test_task_dialog.py` 锁定）
- [x] 删除 MainWindow 旧刷新管线（`_refresh_all_views` / `_build_filter_with_sort` / `_on_data_changed` / `_select_and_load_task` / `_on_task_selected` / `_on_filter_changed` / `_on_quick_preset` / `_on_progress_filter` / `_on_carousel_clicked` / `_update_status_bar` / `_on_status_clicked` / `_on_escape` / `_on_task_selection_changed` / `_on_model_data_changed` 等 20 个方法）及重复的控件/总线信号连接；SignalBus 刷新改由 FilterCoordinator 独家订阅（绑定方法，销毁自动断开）
- [x] 分页 UI 移交 FilterCoordinator（新增 `page_changed` 信号 + `go_prev_page` / `go_next_page` / `total_pages`；初始页尺寸读配置）
- [x] 消除批量操作双重查询（批处理槽内 `_on_data_changed()` 显式调用 + `BatchController.data_changed` 均与总线信号重复，已删除）

## ✅ 阶段 3 — 时间轴视图替换任务页（2026-09-14）

- [x] `src/ui/timeline/timeline_model.py`：`TimelineModel` / `TimelineData` / `TimelineRow` / `resolve_range`
  - 7 种粒度（today/yesterday/week/last_week/month/last_month/30d）、命中裁剪、跨度与裁剪计算、排序（截止/优先级/计划起点）、状态/搜索/归档过滤
  - 纯 Python 无 Qt 依赖，29 用例覆盖（`tests/test_timeline_model.py`）
- [x] `TimelineTableView` + Gantt 委托（色条=起止区间、填充=进度、端点=截止、今天竖线、悬停详情）
- [x] `TimelineController` 接入任务页（总线订阅 + 50ms 去抖 + 粒度/排序/过滤 API + `SelectionContext` 写入）
- [x] 单击选中写入 `SelectionContext`；双击 → 维护抽屉（阶段 4），过渡期同步载入 TaskEditPanel
- [x] **旧列表退役**：任务页移除 `TaskListView` / `TaskListModel` / `BatchToolbar` / 分页控件及 7 个批量槽；`FilterCoordinator` 不再依赖列表（改为「过滤控件 → 辅助部件刷新」），冒烟测试改断言时间轴
- [x] 删除孤儿 MultiTaskDialog / TimelineDetailDialog / task_list_panel（+ `__init__` re-export，grep 证据：全项目 0 引用）
- [x] 时间轴工具行：粒度 + 搜索 + 状态 chips + 优先级 + 排序 + 图例（承接旧 FilterBar 全部过滤能力）
- [x] 删除 FilterCoordinator 及旧过滤部件（FilterBar / StatusBadge / QuickOverview / ProgressBar）；总线刷新与选中由 `TimelineController` 独占
- [x] 时间轴默认**包含已完成任务**（`TimelineController._include_archived = True`）—— 分区 `archive_days=0` 时「完成即归档」，默认排除会让任务一勾选完成就从视野消失；状态 chips 计数改为同口径（含归档），避免「已完成 0」与绿色色条并存的矛盾
- [x] 基建修复：`TaskService.dispose()` 显式解绑 `SignalBus` —— 它是普通 Python 对象而非 `QObject`，Qt 不会自动断连，残留实例会在 repository 关闭后继续回调（`app.py` 退出流程与测试 fixture 均已调用）

## ✅ 阶段 4 — 维护抽屉 + 总览页（2026-09-14）

- [x] 总览页收尾修复：① 总线订阅从 `refresh_theme()` 移入 `__init__`（此前主题未切换过时总览页完全不响应数据变化，且每次切主题重复连接 → 一次事件触发 N 次刷新）；② 焦点时间轴改用与任务页一致的口径（包含已完成 / 已归档任务）；③ 合并问候语与时间轴的重复全量查询；④ `create_task` 补写 `completed_at`（此前 md 导入 / 快速新建的 DONE 任务该字段为 `None`，「本周完成」恒为 0）

- [x] TaskService 增 `append_activity` / `get_recent_activity` / `get_urgency_distribution` / `get_due_stats`
  - `append_activity` 只发一次信号（状态变更优先 `task_status_changed`）；12 用例覆盖
- [x] TaskDrawer：滑入动画（`QPropertyAnimation`）/ Esc 关闭 / 保存自动收起 / 活动时间线 + 撰写器
  - 双击时间轴或图谱节点打开；`tests/test_task_drawer.py` 10 用例
- [x] 总览页：问候 + 快速新建 + 4 统计瓦片（点击跳转带过滤）+ 焦点时间轴（6 预设）+ 近期活动 + 紧迫度分布
- [x] 删除孤儿 DashboardController
- [x] 分析页槽迁入 `AnalysisController`（12 个方法 + 导出链路；页面构建后 `attach()` 注入部件，控制器对未注入部件空值短路以支持懒构建）

## ✅ 阶段 5 — WindowShell（仅 Windows）（2026-09-14）

- [x] `src/utils/win32_hotkey.py`：`parse_accel` 纯函数（修饰键位或 + VK 映射）+ `register_hotkey`/`unregister_hotkey`/`is_supported`/`current_accel`；51 用例覆盖
- [x] `config` 增 `general.hotkey` / `general.pin_on_top`（`_deep_merge` 自动补齐，无迁移）
- [x] WindowShell：`_HotkeyEventFilter(QAbstractNativeEventFilter)` 消费 `HOTKEY_MESSAGE` 触发回调
- [x] WindowShell 收编 show/raise/activate（`wake()` / `toggle_visibility()`）；`grep` 确认 MainWindow 内已无裸 `show()/raise_()`
- [x] SystemTrayManager 改收 shell（构造参数 `shell=` → `shell.toggle_visibility()`）
- [x] 设置对话框增热键 / 置顶项；标题栏置顶按钮改接 `WindowShell.set_pinned()`

## ✅ 阶段 6 — 任务图谱 + 设置页签（2026-09-14）

- [x] md_parser 增 `ParsedTask.links`（`[[任务名]]` 提取、标题保留字面量、边界用例）
- [x] formatter 往返稳定锁定（含链接字面量的 `format(parse(raw)) == raw`）
- [x] `src/services/task_graph.py`：`TaskGraphService.build_graph` + `GraphNode`/`GraphEdge`
  - task/tag/partition 节点、tag case-insensitive 归并、`[[链接]]` 边、`hide_done`、`only_related`、确定性排序；16 用例覆盖
- [x] 图谱渲染：**改用自绘**（`src/ui/graph/graph_view.py`，非 `QGraphicsScene`）— 力导向（seed 可复现）/ hover 高亮 / 双击直达任务 / 过滤 chips
  - 变更理由：节点/箭线在数百量级时自绘比场景图更可控
- [x] SettingsDialog 页签化：常规（含热键 / 置顶）/ 分区 / 关于

## ✅ 阶段 7 — 性能 + 主题注册表（2026-09-14）

- [x] repository 批操作 set-based SQL（`batch_*`/`refresh_overdue_status`/`recalc_all_activity_counts` → 单事务 `executemany` + id 分块 IN，`user_version` 恒为 8）
- [x] 总线刷新 50ms 去抖（`TimelineController.schedule_refresh` / `flush_pending_refresh`）
- [x] 时间线/隐藏页 dirty 延迟刷新（`TimelineController.set_visible` + `HeatmapModel`/`CalendarHeatmapWidget` 的 pending 回放）
- [x] 热力图模型缓存（`HeatmapModel` 按 (year, tags, partition) 缓存 + `invalidate()` 失效；4 用例覆盖）
- [x] theme_registry（`src/utils/theme_registry.py` 弱引用注册表）；部件构造时 `register_theme_aware(self)` 自助登记，`MainWindow.refresh_theme` 由逐个 `hasattr` 列举改为 `refresh_theme_all()` 统一广播；5 用例覆盖
- [x] 裸 hex 收敛核查：31 处中仅 `main_window.py` 标题栏提示色属真·UI 语义色（已收敛）；其余为品牌色（`icon_draw`/`splash` 品牌渐变，注释标明主题无关）、启动画面独立配色、HTML 文档 CSS，均不适用 design_tokens

> 「功能对照遗留」清单已于 2026-09-15 撤销：它比的是**已归档的 PySide6 原型**，
> 11 项里 7 项桌面版已经做掉了（md 实时预览、草稿模式、批量新建、二次确认、
> 标签改名合并、活动搜索、md 导入），剩下的不再当作独立待办，逐条并入下面
> 桌面版的「剩余缺口」去取舍 —— 一份对着不存在的应用列的欠账，只会让人反复
> 去核一些已经落地的功能。

## 🧩 其他

- 真机（有显示器）GUI 冒烟 —— 从清单里撤了：它需要一台带显示器的人和几分钟手点，放在自动化够不着的清单里只会一直挂着。发布前自行过一遍：侧栏 5 页切换、置顶按钮、设置齿轮、托盘、主题
- [x] **UI 层 repository 直连归零**：只读部件（HeatmapModel / TaskTreePanel / CalendarHeatmapWidget / TagManagementPanel）与写路径（TaskDialog / SettingsDialog）全部改依赖 `TaskService`；透传宿主（BatchController / TaskListView）移除 `repository` 参数；删除孤儿 TaskEditPanel / StatusStatsBar / ActivityReportPanel；`MainWindow` 成为唯一持有 repository 的位置（**76 处 → 0 处**，`docs/architecture/repository-calls-analysis.md` 已重写）
- [x] **`#5 Service 去 Qt 耦合`**：4 个后台服务（`TaskScheduler` / `TaskArchiver` / `TaskRecurrence` / `TaskNotifier`）此前构造时硬编码 `QtScheduler()`、直连 `SignalBus` 单例 → 零测试。现全部支持构造注入（`TaskNotifier` 补 `signal_bus` 参数），新增 `tests/test_background_services.py` **21 用例**覆盖调度注册 / 归档阈值（0 与 9999 边界）/ 循环克隆（`+1d/+3d/+1w`）/ 摘要通知（启用开关、静默时段、逾期合并）
- [x] **dev 依赖补全**：`black` / `ruff` 加入 `[dependency-groups].dev`（此前只在 `[project.optional-dependencies].dev`，`uv sync --dev` 拿不到）；`uv sync --dev` 已验证可用。顺带用 `ruff` 清理全项目 lint：**52 → 0**（41 处自动修复 + 手工修复），其中揪出 4 个真实缺陷：
  - `task_list_view.py` 缺失 `TaskService` 导入（`from __future__ import annotations` 掩盖了运行时错误）
  - `task_dialog.py` / `batch_controller.py` 重复导入 `TaskService`
  - `design_tokens.py` **`"surface_raised"` 字典键重复** —— 后一处硬编码静默覆盖了前一处 token 引用，导致 `t.surface_raised` 永不生效
  - `about_dialog.py` 缺失 `QShowEvent` 导入；`app.py` 未使用局部变量
- [x] **CI（`.github/workflows/test.yml`）实际现在就是红的**（此前记「52 → 0」时那批 2.0 代码还没跑过 lint）：`ruff check src/ tests/` 报 4 处（2 × `F541` 多余 f 前缀 + 2 × `F401` 未用导入），已修到 exit 0。同时把第三方教程副本 `docs/fastapi-alembic-demo` 加进 `[tool.ruff] extend-exclude`（用 `extend-` 而不是 `exclude`，后者会覆写默认排除表把 `.venv` 拖进来），`scripts/create_package_db.py` 的 `sys.path.insert` 按文件豁免 `E402` —— 这样本地 `ruff check .` 和 CI 看到的是同一份东西
- [x] **修掉一条日期定时炸弹**：`TestCreateTask::test_create_done_sets_completed_at` 用的 md 是 `DONE <2026-09-14>`，而 `<date>` 紧跟状态关键字时解析成**计划日**不是截止日（见 `md_parser` 的单日期规则），于是 `completed_at` 落到「当前时刻」——撰写当天两者恰好同日，必然通过，次日起必然失败。补上时间让这条 md 真的带上截止日，`completed_at` 的「截止优先」口径才被覆盖到

## 🖥 桌面版（`desktop/` · Tauri）工作线

> 这一节是主线在追的：`desktop/` 是 2.0 界面的 Tauri + TypeScript 重写。
> 2026-09-15 起 PySide6 版整体归档到 `archive/pyversion`，与它**零数据共享**。
> 现状详见 `desktop/README.md`。

已完成：

- 窗口外壳（无边框标题栏 / 置顶 / 托盘 / 全局热键 `Ctrl+Shift+Space` / `Ctrl+1..5`）、主题、五个页面的交互逻辑（甘特时间轴、图谱、热力图、批量表格、标签改名合并）
- **修掉「双击、右键都没反应」**：`dropdown` 的 `setValue` 会回调 `onPick`，于是 `paint → setValue → onPick → paint` 无限递归 —— 抽屉节点建出来了却永远加不上 `.open`，表现就是点了没反应
- **右键菜单**（打开维护抽屉 / 标记完成 / 删除）：删除走 `shared.removeTask`，和抽屉共用同一条确认路径与同一套措辞
- **时间轴按数据自适应**：窗口 = 粒度下限 ∪ 数据跨度 ∪ 今天，列宽按可用宽度平分后夹在 15–34px。以前「本周」只画 7 列，跨月的任务整条消失，右边还空着一大片
- **真实时钟**：`TODAY` 不再读 `DEMO_TODAY`（写死 09-12，害得时间轴上的「今天」指着 12 号星期六）。`DEMO_TODAY` 现在只负责排布演示数据本身
- **快速新建搬到任务页**，替代页头「＋ 新建任务」：必须写任务名，不许造无名任务；总览页那个输入框已删
- 删除类操作的二次确认（`shell/confirm.ts`：抽屉单条 / 管理页批量 / 标签移除，默认焦点给「取消」，Esc 与点遮罩都算取消）
- 图谱：舞台按可用空间铺开（不再写死 900×520）、连线改弧线、节点按离中心的距离错峰入场、右上角加分区标注
- 设置面板 **AI 助手页签已移除**：7 行没有一行接了后端，其中「专用工作区」还指向已删除的目录

已完成（本轮）：

- **持久化**：启动时读库、改完落盘（`data/db.ts`）。Tauri 下走 `tauri-plugin-sql` 直连 SQLite（和原版同一个存储），纯浏览器预览降级到 localStorage —— 刷新不再丢数据
- **分区真正生效**：`partition` 进数据模型，`activeTasks()` 按当前分区过滤。以前 rail 底部的切换器只是弹个 toast
- **Markdown 导入 / 导出**（管理页）：方言实现在 `data/markdown.ts`，抽屉里的 md 源和导出共用同一份序列化
- **热力图对齐真实日历**（`pages/activity.ts` + `styles/pages.css`）：`.hm` 没给 `grid-auto-columns`，隐式列被 `justify-content: stretch` 拉到平分容器 —— 实测列距从 17px 变成 45px，而月份标签按 17px 算绝对位置，整条月份刻度都压在左边一小段；此外标签只按每列周日的月份判定，每月 1 号不在周日时就晚一格（08-01 在 07-26~08-01 那列，标却打到 08-02 那列）。另：「近一月」档位实际是 12 周 = 三个月，标签按周数说话改成了 5 周。冒烟新增断言把「标签列 vs 日历」钉住
- **图谱不再被切一半**（`pages/graph.ts`）：`.gpage` 那条规则从来没命中过任何节点（页面根节点是 `.page`），`.gwrap` 只能退回 min-height 320，而画布高度却按 `innerHeight - 268` 估算成 632 —— `overflow:hidden` 之下底下半张图没了。现在高度由 `#page-graph` 逐层传下来，画布按**量出来的**容器尺寸排布（工具行要先落地再量，否则又会差它那 36px），铺成一圈**椭圆**而不是按短边取半径的正圆 —— 节点占宽从 32% 提到 66%

剩余缺口：**已清空（2026-09-15）**。

最后这几条经确认不再追，一并撤了，留个下落免得有人按老清单又核一遍：

- **Rust 侧业务命令**：不接原版 CLI / 命名管道，前端直连 SQLite 就够（`lib.rs` 继续只有 `app_exit`）
- **演示口径**：总览「较昨日 +2」和活动页「导出」这两处仍是写死的，分别要历史快照表和真导出才谈得上改 —— 位置在 `overview.ts` / `activity.ts` 的注释里，不再单列
- **lint / format script**：CI 已覆盖类型检查、构建与冒烟，格式化暂不引工具
- **每日摘要气泡 / 归档天数 / 管理页多条件筛选侧栏**：原型对照欠的那三项，不搬
- [x] **批量新建**（任务页「批量」按钮）：一次粘贴多行，走同一套 md 方言，实时预览「将创建 N 条」，Ctrl+Enter 提交；Enter 留给换行
- [x] **活动报告搜索框**：只重画列表不 remount —— 整页重建会把输入框连焦点一起重建，「每敲一个字光标跳一下」的搜索框等于不能用
- [x] **抽屉可编辑**：标题、标签、截止（日期框 + 今天 / 明天 / 下周 / 清除）。此前三者全是只读节点 —— 建任务时手滑打错一个字，那条任务就永远错着
- [x] **逾期自动标记**（`store.refreshOverdue`）：`TODAY` 读真实时钟之后，状态还写死在数据里，过了截止日没做完的任务会一直显示「待办」。只从 `todo` 标 `overdue`，**不动 `doing`** —— 手动设的「进行中」下一秒被系统改掉，那个下拉框就像坏了
- [x] **分区口令 + 空闲锁定**（`shell/lock.ts`）：口令按分区设置，切过去挡一层锁屏；空闲若干分钟无输入自动重新上锁。定位是**隐私屏风不是加密** —— 忘了对不起，没法找回（设置时就把这句话写在浮层里）
- [x] **Markdown 源实时预览**（抽屉）：这个框以前能打字却没接任何处理，敲半天没反应，看着像坏的。现在边敲边把那行 md 摊开渲染，写回要显式点「按 md 更新任务」；状态不进 md，所以 `[x]` 不改状态，start 不在方言里所以也不动起点
- [x] **草稿模式**（`shell/draft.ts`）：快速新建与批量框里没提交的字跟着 kv 走（重启还在），页面上一条草稿条说明「字还在那儿」，提交成功立刻清掉 —— 不知不觉自动保存的输入，和丢了字的输入框长得一模一样
- [x] **设置面板死行清理**：删掉那排点了不会有任何反应的行（最小化到托盘 / 开机自启 / 归档 / 安静时段 / 已完成置底…），接上「保存后收起抽屉」（`shell/drawerPref.ts`），分区页改成活的条数与锁标记。原则同当初删 AI 页签：**一排看着能配、实则无用的开关，比没有这一页更误导人**
- [x] **CI**（`.github/workflows/desktop.yml`）：类型检查 + 构建 + 端到端冒烟。此前唯一的自动关卡是 `tsc`，而它看不出「点下去没反应」这类运行时故障

