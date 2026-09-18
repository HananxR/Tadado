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

本轮（2026-09-16）继续：

- [x] **改状态必须留痕**（`pages/shared.ts` 的 `setTaskStatus`）：总览勾选框 / 任务页右键菜单 / 管理页批量 / 抽屉状态按钮这四处此前各自改 `task.status`，**没有一处写活动记录** —— 勾了「完成」，近期活动里没有这一条，「本周完成」也数不到它（完成时间只能退化为结束日，于是「刚完成的这个任务结束日在上周」被漏掉）。现在四处收口到 `setTaskStatus` 统一补一条 `status` 活动；「本周完成」改按这条活动的日期算（`completedOn`），没有活动时退化到结束日。总览那句写死的「较昨日 +2 / 较上周 +3」一并撤掉，换成点开轴就能对上的真实值
- [x] **总览焦点时间轴的档位窗口不再写死**：删掉「本周 = 9/7–9/13」这类日期表，改读 `data/timeline.ts` 那一份定义，与任务页、设置里的「任务视图」同一个窗口 —— 同一个按钮名两页给不同窗口，换一天打开就整体错位
- [x] **当日轴按日期区间取任务**：以前只看「有没有填 at」，于是结束在 9/12 的任务会杵在 9/16 的轴上写着「08:30」，而旁边卡片写着「今日到期 2」：两个数各自都没算错，摆一起就是同一个「今天」两种口径。现在判据是起止日期盖住这一天；过期未完成的从轴上挪到独立一条「已过期未完成 N 项未清」并标出超了几天（以前钉在轴最左侧，那里只放得下 4 条，第 5 条起静悄悄掉进列表），计数也拆成「这一天的 N 项」与「过期 N 项」两个数
- [x] **活动页「导出」真的落一个 csv**（`shell/download.ts`）：以前只弹一句「已导出（演示）」，点了什么都没发生 —— 这比没有这个按钮更糟，用户会去找一个不存在的文件。管理页 md 导出一并走同一条下载路径，文件名带真实日期
- [x] **年份不再写死 2026**：问候条与两处导出文件名改从天数里读年份（`data/time.ts` 的 `isoDay`），跨年之后不会一直说 2026
- [x] `npm run e2e` 之前不触发构建，`vite preview` 跑的是 dist 里的旧包，曾让改动「看起来没生效」。现在 e2e 先跑 `npm run build`
- [x] **焦点时间轴改成「活动驱动」**：轴上只列这一天的活动记录（含新建任务那一条），没动静的任务不占位置 —— 未完成、当前粒度下接下来也没有活动的就不显示。以前判据是「起止日期盖住今天」+ 有没有填 `at`，于是结束在 9/12 的任务会杵在 9/16 的轴上写着「08:30」，而旁边卡片写着「今日到期 2」：两个数各自都没算错，摆在一起就是同一个「今天」两种口径。这条轴回答的是「发生了什么」，不是「该做什么」——后者归任务页和四张指标卡。连带：气泡不再带勾选框（勾一条已经发生的事没有意义）、计数改报「N 条活动」、甘特档同样只画窗口内有活动的任务（条本身仍是起止区间，排的是**计划**）
- [-] ~~「这一天是怎么过的」日回顾~~：**不做**。全库检索「回顾 / 这一天是怎么过」0 命中，从未实现过；且与活动报告页（热力图 + 标签筛选）重合，属于同一个需求的第二张皮
- [x] **气泡挤在一起时同侧自动多开一条道**（`overview.ts` 的 `spreadPills`）：分道只能在进了文档之后做 —— 气泡的 left 是百分比，真实像素要等容器有宽度才量得出来，量不到（页面不可见）就保持原样。**不采用「重合就切甘特」**：甘特的粒度是**天**、当日轴的粒度是**分钟**，今天的十几条活动切过去全落在同一格，照样叠着，还顺带把时刻弄丢了。重合是「同一粒度里放不下」，解法只能是加道。`.tdt` 高度在 CSS 里写死，多开的道由 JS 撑开，否则新道会溢出卡片（基准高度当天 172px，后来总览分两列时降到 150 —— 见「一屏到底」那条；两处现在共用一个 `AXIS_H` 常量）
- [-] ~~焦点时间轴做成鱼骨状~~：**不做**。它想解决的「跨窗口任务」和「条太挤」有更便宜的解法；代价是起止日期要靠斜刺端点读、对齐刻度的精度掉一截，而这条轴的用途恰恰是「什么时候有什么」
- [x] **设置模块精简**：撤掉「安全」「自动化」两组 —— 前者只剩「分区口令」，而它是**某个分区**的属性，摆在那儿得先挑分区；后者只有一行只读说明（逾期标记每次加载顺手扫一遍，本就不给开关），一行占一整组不值当。空闲锁定并入「窗口」，自动归档并入「任务与归档」。从五组两页变成两个页签
- [x] **分区能增 / 删 / 改名 / 各设各的口令**（`data/partitions.ts` 的 `addPartition / renamePartition / removePartition / bootPartitions`）：列表存库、启动读存档 —— 用户自己分过的区不能被内置那四个盖回去。删的时候任务先迁到别的分区：不迁就等于凭空消失，各页都按当前分区过滤，而一个已经不存在的分区永远不会成为「当前」。口令从「常规」挪进分区页签，跟着分区那一行走
- [x] rail 底部的分区切换器不再只画一次：订阅 `onPartitionListChange` 重画 —— 只画一次的菜单里，新建的分区根本切不过去
- [x] **自动归档**：设置里「关 / 7 / 30 / 90 天」，已完成任务结束 N 天后收进归档（`data/store.ts`）。按**结束日**算而不是完成日：完成日要从活动记录里反推，而解析函数在 pages 层，store 在 data 层，反过来 import 会把依赖方向搞乱；结束日只可能晚于完成日，晚几天收比把还在用的数据收走安全。手动「取消归档」的任务本次会话内不再被自动收走（`keepActive`）
- [x] `seg` 是无状态的，选中态得调用方 `setValue` —— 归档 / 空闲锁定原先点了档位高亮不动，看着像没生效（时间轴粒度那一行是因为有外部订阅才对的）
- [x] 种子数据里写死的「今天 15:03」在早上打开就成了「还没发生的活动」，还因为时刻最大排在所有活动最前面。`mock.ts` 的 `clampSeedClock` 把整批「今天 HH:MM」压到 5 分钟前以内，间隔等比保留（密集时段照样挤成一簇）
- [x] 过期未完成不再连带吞掉它**今天的活动**：以前一个 `continue` 让「过期」和「今天有活动」互斥 —— 给一个已过期的任务补一条进展，那条进展在轴上反而消失了，越忙一天轴越空。现在过期只作为任务维度的提示单独列一行
- [x] **自动归档与空闲锁定改成按分区**（`store.ts` / `lock.ts`）：它们和口令一样是**某个分区**的属性 —— 工作区的东西比个人区更需要自动挡一层、过期任务也更该收走。摆成全局要么得先挑分区（多一层），要么取一个两头都不对的折中值。存储从单个值改成 `Record<分区 id, 值>`；空闲到点只锁**当前**分区（`lockCurrent`，原来是 `lockAll`），切分区时重新起计时。「任务与归档」因此退回「任务视图」，只剩时间轴粒度
- [x] **有任务的分区不给删**：不做「自动迁到别的分区」—— 迁去哪儿用户没得选，等于替他决定一批任务的归属；真要留着那些任务，他自己先移走更清楚。所以按钮置灰并写明剩几条。空的分区照删
- [x] **设过的口令能改**：忘了旧的在别的分区里重设一个即可，**不校验旧口令** —— 它挡的是路过的人，没有「证明你是你」的必要；要旧口令反而多出一个「忘了就彻底进不去」的死结（`lock.ts` 顶部注释同步改了）
- [x] **设置里的「时间轴默认粒度」撤了**（`data/timeline.ts` / `pages/tasks.ts`）：它其实是任务页工具行那个 seg 的**第二个入口**，且改的是当前视图、不持久化（刷新回到「本周」）—— 叫「默认」名不副实，进设置还得解释为什么改了不记住。真正的入口就在时间轴正上方，顺手。两处共享一份状态要靠互相订阅防回声（`setTimelineRange` 里「值没变就返回」就是为挡这个环），现在单入口，广播层一并删掉，改完直接 `render()`。「任务视图」这组因此空了，整组撤掉 —— 常规页签剩「外观」「窗口」
- [x] **设置不再分页签，一页到底**（`shell/settings.ts` + `index.html` + `styles/shell.css`）：分「常规 / 分区 / 关于」三页时每页只剩两三行，翻页成本比滚动高，还得记「口令在哪一页」。现在整页是 外观 → 窗口 → 分区 → 关于，`.set-tab` / `.set-tab.active` 那两条 CSS 一并删（`renderTab` → `renderGroup`）
- [x] **切到别的模块自动收起设置抽屉**：`mountSettings` 里 `subscribePages`，与「编辑任务」抽屉（`taskDrawer.ts`）一致 —— 设置讲的是外壳与分区，翻页后还挂在那儿，看上去像新页面长出来的一层，也说不清它属于谁
- [x] **分区配置按上一版的样式合并成一行**：`工作 · 19 条 🔒 … [自动 ▾][口令][改名][删除]`。自动归档 / 空闲锁定默认关、是少数人用得着的那类设置，收在「自动 ▾」里、展开了才建那两个 seg（四个分区不会再各挂两个常年不动的控件）；两项只要有一项不是「关」，按钮染强调色，收着也看得出这个分区动过默认值。条数与锁挪到名字一侧 —— 抽屉只有 420px，摆右边会和四个按钮抢位置
- [x] **分区能指定默认分区**（`data/partitions.ts` / `shell/settings.ts` / `styles/shell.css` 的 `.part-dot`）：启动时进哪个区，和「现在在哪个区」是两件事 —— 切分区是随时都在做的事，默认不跟着切。以前只有 `active` 且不存盘，每次打开都落列表第一个，把自己常用的那个排在第二位的人每次都得再切一次。存 `partitions.default`，`bootPartitions` 里 `active` 落默认分区；删掉的正好是默认就退回第一个。UI 是行首一个**单选点**（一组里只能有一个，画成按钮的话「默认 / 设为默认」两种文字来回切反而看不清）；设到上锁的分区会 toast 提醒「启动时先要口令」
- [x] **导出全局统一：md / txt / xlsx 三选一**（新增 `data/export.ts` `data/xlsx.ts` `shell/exportMenu.ts`，改 `pages/manage.ts` `pages/activity.ts`）：以前两个页面各导出各的（管理页 .md 方言、活动页 .csv），「导出」在同一个应用里是两种互不相干的东西。现在 **md 与 txt 内容完全一致**（同一段文本，只有扩展名不同，与 python 版导出的排版一致），xlsx 是同一批数据的表格形态；文件名主体由调用方给、扩展名在 `buildExport` 补。xlsx 自己生成（zip store + CRC32 + `inlineStr`，无第三方依赖）：为一个按钮往依赖里塞几百 KB 不值当，而它是用户明确要的格式；e2e 里逐项校验 CRC —— 下载成功不代表包是好的，CRC 写错时 Excel 才报「文件已损坏」
- [x] **活动导出的排版：标签作标题、任务有序、活动无序**（`pages/activity.ts`）：md 与 txt 同一份文本 —— 标签本身就是分组标题（不再套 `##`），下面是**有序列表**的任务，任务底下的活动是**无序列表**（缩进三空格，对齐有序列表的内容列才会被当成嵌套）。xlsx 仍是扁平表：标签 / # / 任务 / 状态 / 时间 / 内容。管理页的任务导出不动 —— 它是 md 方言行（可回导的规范格式，DESIGN 2.11），改成分组就导不回来了
- [x] **任务管理：删除「导入 .md」**（`pages/manage.ts`）：方言本来就带不回状态（导出再导入会把已完成变成待办，见 `data/markdown.ts` 顶部），而任务页的批量新建框吃**同一套方言**、当场就能看见解析出几条 —— 先存成文件再导回来只是多绕一圈。「导出 .md」改名「导出 ▾」并走统一的三格式菜单，且跟着**当前筛选**走（表格上摆着状态 / 归档两个筛选，导出「这个分区全部」会让人以为筛选没生效）
- [x] **活动分析：导出与「范围」同一行、作为独立按钮钉在该行最右**（`pages/activity.ts` + `styles/pages.css`）：从左排起是范围组（标题 + 时间档位 + 日期框 + 区间说明 —— 那个区间是范围的产物，跟着范围走），从右排起是导出按钮；两者之间由弹性空白分开，它按这个范围取数所以同行，但不是又一组时间档位。**坑**：`.grow` 是按容器作用域定义的（`.card-h` / `.tools` / `.batchbar` … 各写一条），范围条里漏了这条 → 那个 span 宽 0，导出紧紧黏在区间说明后面（类名在、位置没变，看图才发现）。补 `.act-filter .grow { flex: 1 }`，e2e 也从「有 grow 类」升级为**量真几何**（按钮右边缘贴着范围条右内边距）。取数/排版是模块级函数 `datedRowsOf` / `tagStatsNow` / `queryGroups` / `exportTable`，不捕获 mount 的局部变量（页面随时 remount，捕获就会停在打开页面那一刻）
- [x] **标题栏左上角只留软件名**（`index.html` / `styles/shell.css` / `shell/titlebar.ts`）：LOGO 与版本号徽章都撤了 —— 图标在任务栏 / 托盘 / 安装包上已经见过一遍，标题栏里再来一张是同一句话重复三遍；版本号挪去设置 → 关于，那里由 Tauri 填**真实**版本（`#set-ver`，拿不到才退回写死的 0.1.0），不再是一枚写死的徽章。`.logo` / `.ver` 两条 CSS 一并删，`renderVersion()` 与 `getVersion` 的 import 跟着走
- [x] **设置里的「窗口置顶」撤了**（`shell/settings.ts` / `styles/shell.css`）：它是标题栏图钉的**第二个入口**，而图钉就在那儿一键切换 —— 与其他设置项不同，它是「现在就要这个窗口浮上来」的动作，不是一条要翻两层菜单去改的偏好。图钉保留（唯一入口），`pinControl` 与 `onPinChange` / `togglePinned` 的 import 一并删。顺带：上一轮为这一行加的 `SettingRow.hint` 与 `.set-lb` / `.set-hint` 也随之删掉 —— 没有第二行用得上它，留着是没人走的机制（「窗口」组现在只剩「全局热键」一行只读值）
- [x] **「常驻置顶」改名「窗口置顶」并补一句说明**（名字随后随本项一起撤了，改名只存在于 git 历史）（`shell/settings.ts` / `titlebar.ts` / `index.html`）：那四个字说不出它在干什么 ——「常驻」听上去像开机自启，「置顶」又像把任务钉在列表头上。它其实是窗口浮在所有应用之上，所以标签照实说，底下小字「浮在其他应用之上，切到别处也看得见」（`SettingRow.hint` + `.set-lb` / `.set-hint`）。图钉 `title` 与 toast 文案同步改
- [x] **锁屏上加「设置」出口**（`shell/lock.ts` / `panels.ts` / `shell/settings.ts` / `styles/controls.css`）：锁屏盖住整个应用，而重设口令不需要旧口令（只挡路过的人），所以没有这个入口就是**死循环** —— 想改口令先得进得去，进得去又得先知道口令。默认分区上着锁又忘了口令，等于开机即锁死。做法是「让位」而不是「解锁」：`openSettings` 若发现锁屏开着就 `suppressLockScreen()`（body 加 `.lock-suppressed`，只把抽屉 210 / 弹窗 220 抬到锁屏 200 之上），主区 / 侧栏 / 标题栏照旧被盖着点不到；`closeSettings` 配对 `restoreLockScreen()`，期间清了口令锁屏就自己收起。lock.ts 不能直接 import settings.ts（settings 依赖 lock，是环），所以 panels.ts 新增 `registerOpen` / `openPanel`，按 id 中转
- [x] **托盘菜单：重新划定为三项**（`src-tauri/src/lib.rs` + `shell/trayBridge.ts`）：最终是 `设置 / 显示窗口 / 退出 Tadado`，三项等距、**不加分隔线**（试过加：Windows 原生菜单的分隔线自带 8–10px 上下留白，插在中间会让那一处明显比其它相邻项松，看着像没对齐）。撤掉的：「收起窗口」（与「显示窗口」永远只有一项有效，而静态菜单不会变灰；左键单击托盘仍是切换显隐）、「新建任务」（点它只能把主窗口叫出来再弹一层浮层，而用户要的是「只有那个新建框、后面不出主界面」—— 那得另开一个窗口，不值当。**Rust → 前端的事件通道**保留：新增 `shell/trayBridge.ts`，Rust 只负责把窗口叫出来再 `app.emit("tray", "设置")`，真正的动作（开抽屉）在前端；浏览器预览里 listen 会失败，静默忽略
- [x] **设置里新增「开机自启动」**（`shell/autostart.ts` + `shell/settings.ts` + tauri-plugin-autostart）：Rust 侧 `.plugin(tauri_plugin_autostart::init(...))`，capabilities 加 `autostart:allow-enable/disable/is-enabled`，前端包一层「浏览器里也不会炸」的门面。设置面板是同步渲染的，而真实值要问系统（异步）—— 先渲染成「关」、拿到再翻过来；**问不到时（浏览器预览）整行标成 `.sw.disabled`**，而不是摆一个点了没反应的开关。原来那一组叫「窗口」，现在改叫**「启动」**（开机自启动是进程层面、全局热键是窗口层面，都是「怎么把它叫起来」）
- [x] **压测数据的时间关系修正**（`data/mock.ts` 的 `stressTasks`）：原来「创建任务」那条活动落在 `min(截止日, 昨天…)` 上，于是**截止日已过的任务，活动时间恰好等于它的截止日**（连钟点都一样，因为 `due` 和它共用 `hour`）—— 导出去看着像「创建于截止日」。现在按 `创建日 ≤ 开始日 ≤ 截止日` 生成，且创建日一定在过去（未来截止的任务也是过去某天建的）。e2e 加一条：导出里的活动时间**都不晚于今天**（活动记的是已经发生的事）
- [x] **压测数据的覆盖策略**（`data/store.ts`）：`STRESS_EXTRA > 0` 时让**种子说了算** —— 缺的补进来、已有的 `bulk-*` 用种子的版本覆盖。不这么做的话，改了生成逻辑后库里那份不会变（id 已存在就不补），刷新看到的还是旧数据。覆盖范围限定 `bulk-*`：那批是自动生成的演示数据，不是用户资产；手写的 28 条原型任务仍尊重库里的版本
- [x] **压测数据：种子任务 28 → 100 条**（`data/mock.ts` 的 `STRESS_EXTRA = 72` + `stressTasks()`）：看「一屏画多少条」这类上限（ROW_LIMIT / GANTT_LIMIT / FEED_LIMIT）在大批量数据下的样子。**生成而不是手写**（100 条字面量没人维护得动），取值全部由序号推出 —— **确定性**，每次启动是同一批，随机会让「刚才那条去哪了」没法回答。状态跟日期对得上（过去的要么完成要么逾期，未来的才是进行中 / 待办）；活动日一律落在**过去**（未来的活动会排到「刚刚」前面）。启动补齐：`bootStore` 在 `stressExtra() > 0` 时把种子里缺的按 id 补进库（改完常量重启就看得见，不用清库）；正常情况仍以库为准，设回 0 后这 72 条**不会自己消失**，要清就删 `tadado.data`（桌面端）/ localStorage 的 `tadado.tasks.v1`（浏览器）
- [x] **`clampSeedClock` 的调用时机**：种子拆成 `SEED_TASKS`（唯一实例）+ `TASKS`（深拷贝）之后，必须**先压时钟再拷** —— 拷完再压只改到种子，副本里仍是「今天 15:03」这种还没发生的时刻，它会排在「刚刚」前面，把刚建的任务挤出近期活动
- [x] **总览的数字点开必须对得上（窗口自适应）**（`pages/tasks.ts` 的 `fitWindow`）：以前任务页**先按档位定窗口、再拿窗口砍任务**，于是总览写「逾期 4」、点进来只有 3 条 —— 第 4 条的起止落在窗口外，它没丢，只是没被画出来，而用户只能认为数字是假的。顺序反过来：**先筛，再让窗口去迁就筛出来的这批**（窗口可能比档位宽，表头一直写着真实区间）。同理修掉「点近期活动 / 焦点时间轴 / 图谱跳过去，抽屉开了、列表里却没有它」—— 定位的那条若排在 `ROW_LIMIT` 之外，会提到最前面，保证列表里有它
- [x] **chips 数字 = 点开后的行数**（`poolTasks`）：状态 chips 的数按「优先级 + 搜索」算、唯独不含状态本身。以前按 `activeTasks` 全量算，于是「逾期 4」点进去 3 行
- [x] **优先级筛选**（`focus.ts` 的 `showTasksWithUrgency` + 任务页 dropdown）：总览「紧迫度分布」→ **「优先级分布」**（术语跟着编辑面板的「优先级 P0–P3」统一），每一档可点击 → 跳任务页并按该优先级筛出。以前这一整块点了没反应。`jumpToTask` / `showTasksWithFilter` 现在都会把**两个筛选维度一起复位**（留着上一次的「只看逾期」再定位一个进行中的任务，就是抽屉开了、列表里没有它）
- [x] **「本周完成」tile → 「已完成」**：点它进的是任务页的「已完成」筛选，那里列的是**全部**已完成；名字说本周、点开是全部，两个数对不上。本周的数挪到副标（「本周 N · 较上周 +x」）
- [x] **近期活动行更丰富**：时间 + **状态色点** + 标题 · 进展 + 右端**标签**（一行只有一句标题时右侧空着也是空着）
- [x] **任务管理的导出与活动分析统一**（`data/export.ts` 抽 `groupedText` + `ExportGroup`；`pages/manage.ts` 的 `exportGroups`）：两处都是「标签 → 任务（有序）→ 该任务的活动（无序）」，md / txt 各一套符号，生成逻辑**共用一份**（各写一份必然分叉）。管理页的任务按**第一个标签**分块 —— 一条任务只出现一次（这是任务清单，同一条出现两遍会让人以为有两件事；活动分析那边按标签查活动，天生会重复，所以那边做了去重）。**管理页原来的 md 方言（`- [ ] 标题 #标签 ⏰09-25`）不再用于导出** —— 那是为了能导回来，而导入 2026-09-17 已撤，约束消失。顺带删掉随之无人使用的 `tasksToMarkdown`，并把 `data/markdown.ts` 顶部说明改写成「现在只管单条编辑框与批量新建两处往返」
- [x] **活动时间改成真时间戳（模型层）**（`data/types.ts` 的 `At` + `data/time.ts` 的 `stampOf` / `dayOfStamp` / `minuteOfStamp` / `nowStamp` / `stampText`）：以前 `Activity.at` 存的是**展示串**（`"刚刚"` / `"今天 09:12"` / `"昨天 17:20"` / `"09-11 09:30"`），于是 —— 库里写着「昨天」，明天打开同一条就成了「前天」；界面和导出都要靠**正则反解这句话**才算得出日期（`activityDay`、`activitySortKey`、`RELATIVE_DAYS` 一整条链路）；「今天更新了几个」这句统计是拿 `at.startsWith("今天")` 数出来的。现在存 epoch 毫秒，归日是一句除法，相对词一个不留（界面 / 导出 / 库里都是 `09-17 14:19`）。**注意用 `nowStamp()` 而不是 `Date.now()`**：天数基准是「本地日历日的 UTC 型 anchor」，直接混真实 UTC 时刻会差一个时区（本地 09:12 存进去、显示成 01:12）。种子里仍写人话（那 28 条要和原型逐字对照），构建 `SEED_TASKS` 时由 `seedStamp()` 一次性换算 —— 顺序是先压时钟（`clampSeedClock`）再换算，反了就没得压。「无日期活动」这个概念随解析函数一起消失了（`undatedCount` 及相关文案删除）。**旧数据在读入口归一化**（`data/store.ts` 的 `normalizeStamps` + `data/time.ts` 的 `parseStampText`）：改造前活动时刻存的是展示串，直接当数字用会算出 `NaN-NaN 05:42`（那个 05:42 是 `new Date("09-16 13:42")` 按本地时区解析、取 UTC 再差 8 小时的结果，看着像真的）。**没有在显示层做「—」兜底** —— 那只是把「数据不合法」藏起来；模型的不变量是「at 永远是有效时间戳」，所以在读入口修一次并写回（相对词的换算是有损的，换不出的落到任务创建日上午）。e2e 把旧串塞回 localStorage 再 reload，验证它被归一化成数字、界面不出现 NaN
- [x] **活动导出的 md / txt 从「同一份文本」改成「同一套层次、两套符号」**（`data/export.ts` 的 `ExportTable.text` → `{ md, txt }`；`pages/activity.ts` 新增 `exportMarkdown` / `exportPlain`）：三层结构 = 标签分块 → 任务有序列表 → 活动无序列表。md 里标签行写 `#后端`（**`#` 后不留空格** —— 留了空格 md 就把它当一级标题渲染成一行大号字，比任务本身还抢眼；不留空格时它只是一句普通文本，仍然一眼看得出分块的开头）、`1.` 任务、缩进 **3 空格** 的 `-` 活动 —— 3 格正好对齐 `1. ` 的内容列，缩 2 格会变成「懒惰续行」、缩 4 格直接变代码块）；txt 一个 md 符号都不用（`【后端】` / `1)` / `·`，任务缩 2 格、活动缩 5 格对齐），因为它的用途就是丢给不认 markdown 的地方（记事本、工单），在那里 `# 后端` 会被原样显示、`- ` 是一串小横杠。文件头那行 `<!-- tadado · … -->` 元信息去掉（范围 / 条数在界面上本来就看得见）。管理页的任务导出**不动**：它导的是可回导的方言行（DESIGN 2.11），把 `- [ ]` 换成 `·` 就再也导不回来了
- [x] **四张表都分页、档位统一为 20/30/50/100**（`pages/pager.ts` + `pages/shared.ts`）：在管理页表格 / 任务页时间轴 / 活动分析报告之外，总览「近期活动」也加上了分页（一次查询可能上百条，全倒进卡片会把下面整页撑开）。四张表共用同一个 `pager()`，所以「第几条到第几条 + 翻页 + 每页几条」在哪儿都长一个样；档位只有一组 `PAGE_SIZES=[20,30,50,100]`，默认每页都是 20（四个常量分开是为了想单独调某张表时不必改全局）。近期活动原来是 `FEED_LIMIT=7` 截断，现在改成 `FEED_PAGE_SIZE` 分页
- [x] **三张表都分页**（新增 `pages/pager.ts`，管理页表格 / 任务页时间轴 / 活动分析报告共用一份）：抽出来是因为三处都要「第几条到第几条 + 翻页 + 每页几条」，各写一份迟早出现一处翻到最后一页夹不住、一处换了每页条数没回第一页。默认每页：管理页 12（`PAGE_SIZE`）、任务页 25（`TASK_PAGE_SIZE`）、活动报告 20（`REPORT_PAGE_SIZE`），档位共用 `PAGE_SIZES=[12,25,50,100]`。任务页的 25 以前是**截断**（只画前 25 条，翻不到后面），现在能翻页；窗口按**当前页**的行去撑（`fitWindow`），所以翻页时表头区间跟着变。定位某个任务时会先算出它在第几页再翻过去（跨页跳转仍能看到它）；换筛选 / 排序 / 档位 / 搜索词 / 标签 / 范围都回到第一页
- [x] **显示条数：常量集中 + 每页条数有入口**（`pages/shared.ts` + `pages/manage.ts`）：`ROW_LIMIT=25`（任务页时间轴**上限**，截断）、`PAGE_SIZE=12` / `PAGE_SIZES=[12,25,50,100]`（管理页表格**每页**，有翻页器）、`GANTT_LIMIT=20`（总览甘特）、`FEED_LIMIT=7`（近期活动）。**不进设置** —— 上限是渲染上限不是偏好；而「每页几条」的入口就放在**分页器上**（下拉 12/25/50/100），它只影响眼前这张表，不该让人去设置里翻。截断了就把三个数都写出来（「前 25 条 · 筛出 30 · 共 42」），别让人以为「只画了这么多」＝「只有这么多」。管理页那个 `PAGE_SIZE=12` 以前是写死在 manage.ts 里的局部常量，所以「改常量」对它根本不生效 —— 一并收进 shared.ts
- [x] **两条 flaky 用例的真因：新建的任务不在当前页**（`e2e/smoke.mjs`）：「不带 # 的多个标签能入库」「标签独立成行」偶发失败，报的是「(没有标签)」这种看不出所以然的信息。真因不是时序而是**分页**：100 条数据下这张表按截止排序，今天截止的新任务排在几十条逾期任务**后面**，多半落在第 2 页 —— `locator` 在当前页一行都匹配不到。改成先搜出来再断言（与「批量建出两条」同一种处理），并在断言后清掉搜索词免得污染后面的用例。之前两次都当成 flaky 放过去了 —— 那种「偶发」往往只是**条件没凑齐**
- [x] **打包 Tadado2 v1.0.0**（`npm run tauri build`）：release 编译 4m06s，出两个安装包 —— NSIS `Tadado2_1.0.0_x64-setup.exe`（2.6 MB，双击即装）与 MSI `Tadado2_1.0.0_x64_en-US.msi`（3.6 MB，给静默/企业分发），都在 `src-tauri/target/release/bundle/` 下；另拷了一份便携版 `bundle/portable/Tadado2.exe`。**验证不是「能打开就行」**：读主程序的版本资源，确认 `ProductName = Tadado2`、`FileVersion` / `ProductVersion = 1.0.0` —— 这正好回答之前那个「版本号没变」的疑问：当时是 Rust 二进制没重编译，不是改错了地方。安装后主程序叫 `Tadado2.exe`；`target/release/desktop.exe` 那个名字来自 Cargo 包名（故意没动，见改名的说明）
- [x] **方言支持「活动行」：活动清单可以直接导入**（`data/markdown.ts` + `pages/tasks.ts` + `pages/overview.ts` + e2e）：活动分析导出的清单是「标签 → 任务 → 活动」三层，而导入通道此前只认任务行 —— 把清单粘进批量新建，活动会一条不剩地丢掉（在一份真实清单里那是 82% 的行）。现在方言多认一种行：**缩进在任务下面、以 `MM-DD HH:MM` 开头的一行**属于该任务的时间线（缩进 ≥2 格、`- ` 前缀可选，两种导出写法都能直接粘）。时刻交给现成的 `parseStampText`（它本来就认这个写法），活动文本一个字符不改。配套三条：① 带了活动行就**不再**补那条假的「导入任务」；② 活动按「新的在前」排一次（数组的既有约定）；③ 总览「今日到期」加 `due !== null` 判据 —— 迁移来的旧数据里有一批**没有截止**的任务，它们的 end 只能落今天，只看 end 会把「没有这个信息」显示成一个具体的日子。e2e 两条：带活动行的粘贴按一条任务预览、导入后活动进了时间线且新的在前
- [x] **新增 skill：`tadado-activity-import`（活动清单 → 可导入方言）**（`~/.claude/skills/tadado-activity-import/`：`SKILL.md` + `scripts/convert.mjs` + `convert.bat`）：设计原则是**先对账，再动手** —— 默认只解析只报告、不写任何文件；认不出的行必须停下问用户；源里每一行活动都要有去向（输出 / 并入续行 / 重复剔除），数字不平就不许写出；需要拍板的事（同名合并、截止缺失、标签超 3、优先级无来源）集中列出来问。**端到端核对抓出一个静默错误**：截止挖掘用了两条正则，后一条把前一条的结果覆盖回箭头**左边**的旧日期（`截止时间 A -> B` 读成了 A）—— 靠"把转换结果再喂回应用真正的解析器数一遍"才看出来。这是这轮最值钱的一步：**转换器的输出必须能被下游的解析器验一遍**，「数量对」不能只是自己说的
- [x] **改名 Tadado2 + 版本从 v1.0.0 起 + 重写「关于」**（`tauri.conf.json` `Cargo.toml` `package.json` `index.html` `src-tauri/src/lib.rs` `shell/settings.ts` + `styles/shell.css`）：`productName` / 窗口标题 / 标题栏品牌字 / `<title>` / 托盘 tooltip 与「退出 Tadado2」/ 开机自启那行的 tooltip 全部对齐；版本号四处一起提到 `1.0.0`（tauri.conf / Cargo / package.json / 设置里的兜底值），显示时补 `v` 前缀（Tauri 回话给的是纯数字）。**故意不动**：`identifier`（`com.tadado.app`）—— 它决定 `%APPDATA%\com.tadado.app` 这个数据目录，改了等于让用户现有的库、窗口位置、设置全部「消失」；同理数据库文件名 `tadado.data` 与 localStorage 的键、Cargo 的 package name（开机自启的注册项按它走）都保持原样。导出文件名前缀改成 `tadado2-`。「关于」重写成按实际功能写的介绍（`SettingGroup` 加 `intro`）：应用名 + 一句话定位 + 「功能」「特色」两份清单（对着五个页面与真实能力逐条列，不写技术栈、不提旧版本），e2e 断言两处：标题栏品牌 = `Tadado2`、关于面板的名/定位/两份清单/版本号都在
- [x] **真机验证的插曲：一次误判，和一条因此加上的自检**（`db.ts` 的 `sqliteApi`）：`npm run tauri dev` 起来正常、100 条数据照常显示，但我直接读库文件头（第 60–63 字节）读到 `user_version = 0`，于是断定「tauri-plugin-sql 上 PRAGMA 写不生效」，还把版本号搬进了 kv 表。**这个结论是错的** —— 应用当时还开着，最新写入躺在 951KB 的 `-wal` 里没 checkpoint，重启（关闭时 checkpoint）之后主文件里就是 1。**外部读到的值可能是陈旧视图，别拿它去推翻一个还在运行的进程**。最终回到 PRAGMA 单一来源（与 Py 版同一套，版本跟着数据库文件走），并加一条**写完读回核对**：PRAGMA 万一被忽略是静默的，而这套机制静默退化（每次启动重跑一遍迁移）要等某天真加了破坏性迁移才会暴露，那时它已经在用户的库上跑过好几遍了。更一般的教训：界面正常只说明「没抛错」，机制性的写入需要能独立核对
- [x] **存储版本与迁移：版本号 + 线性迁移链**（新增 `data/schema.ts`，改 `db.ts` `store.ts` `partitions.ts` `shell/lock.ts` `main.ts`）：桌面端此前**零机制** —— 只有一句 `CREATE TABLE IF NOT EXISTS`，没有任何版本号。现在照搬归档分支上 PySide6 版那套（`src/models/migrations.py`，那边跑到 8；配套文档 `docs/database-migration-technique.md`）：`MIGRATIONS: {from, to, sql?, run?}[]` 线性链，启动时读 `PRAGMA user_version` 顺序跑完写回。规矩照搬：**只能加不能改**（只 `ALTER TABLE ADD COLUMN`，不删列、不改类型）。`0 → 1` 就是「确保这套表在」—— **老库的 user_version 读出来也是 0，于是它一启动就被带上版本号，数据一条没动**，这是存量库零成本升级的路子。浏览器预览没有 SQLite，版本号落在 kv 的一个 key（`tadado.schema.version`），但迁移链是同一条 —— e2e 因此能真的验迁移
- [x] **读入口归位：`data` 列里的 JSON 也得有人管**（`data/schema.ts` 的 `normalizeTasks`）：业务字段整条塞在 `tasks.data` 里，所以「表结构」有版本号管、「列里的结构」只能靠读入口 —— 缺字段给默认值、类型不对的救回来、旧格式（活动时刻的展示串）换新格式、认不出的活动类型退成 `log`、连 id 或标题都没有的整条丢掉并计数。`JSON.parse(...) as Task` 原来是**断言不是校验**，少一个字段就是 `undefined` 一路带到界面（`tags.join()` 直接抛）。原先散在 `store.ts` 的 `normalizeStamps` 一并收编（两份归位逻辑并存的结果是「都修好了但没人知道哪份说了算」），kv 值也加了取证（`asStringRecord` / `asNumberRecord` / `asPartitionList`：存档形状不对就当没设过，以前是读出来直接用）
- [x] **库故障不再静默降级成「数据没了」**（`db.ts` 的 `connect` / `backend = "error"` + `main.ts` 的提示）：以前那个 `catch` 把「库打不开」和「浏览器里没有插件」当成同一件事，一律降级到 localStorage —— 后果是用户的库静静地不被读取、界面一个字不说、此后所有写入都落到 localStorage（数据被劈成两半，而表面上一切正常）。现在**先判环境再谈连库**（`isTauri()`，本来就是预期路径，不该产生告警），库故障是终态：不降级、不重试、不写入。另外读失败后**禁止写入**（`writeBlocked`）—— 少了这条，「坏存档原样留着」只是句好话：界面继续跑，用户随手一点就触发 `dataChanged` 全量覆盖，那份还能人工捞回来的存档当场没了。外壳用 toast 把原因说出来
- [x] **测试样例全部收进演示空间：100 条，其他分区为空**（`data/mock.ts` `data/partitions.ts` `data/store.ts` + e2e）：以前种子按标签匀到四个分区（「每个区都得有东西可看」），结果是每区都只有几条、看不出规模，压测也压不出东西。现在 `SEED_TASKS` 一律落在演示空间，规模 = 28 条原型手写 + 72 条压测生成 = **100**（`DEMO_TASK_COUNT`），默认分区也改成演示空间（否则开机进「工作」是一片空，像数据没加载）。**「自动清空」靠的是启动时归位**：老库里散在别区的种子由 `adoptSeedPartitions` 搬回演示空间（只动种子 id，用户自己建的任务一条都不碰）—— 光改种子只对全新安装成立。注意 100 里有 1 条是**已归档**样例（管理页归档列要有东西看），所以任务页列得出 99 条，e2e 两边一起数。e2e 顺带修了两处被这次改动暴露的问题：① 从总览点「逾期 38」进任务页停在上一轮翻到的第 2 页，看到的只是后半截 —— 换筛选/优先级就回第一页（`tasks.ts` 消费跨页请求时重置 `page`）；② `.card-b` 上的 `justify-content:center` + 滚动容器会把溢出的那半截推到**滚不回来**的一侧（被卡头盖住、点不到，e2e 卡在「点轴上那个簇」超时），改用 `margin: auto 0`。断言也从「当前页行数」改成「筛出来的总数」——100 条之后一页装不下，比行数会误判
- [x] **一屏到底：主区不再滚，五页各自撑满**（`styles/shell.css` `styles/pages.css` + `pages/overview.ts` `tasks.ts` `activity.ts` `manage.ts`）：原来 `.main` 是 `overflow:auto`、`.page` 由内容撑高，看全一页就得整页滚（页头 / 卡片头 / 分页器全被滚走）。现在高度从 `.main` 一路 flex 传到列表：固定的块（指标卡、热力图、工具行）留在原地，会长的那块在卡片内部吃掉剩余高度并滚。**四个坑**：① grid 的行高默认由**内容**决定 —— 列表装了 20 行就把行高顶到 700px，容器被压扁后行高照旧（总览实测溢出 186px），要 `grid-template-rows: minmax(0,1fr)` 把行高钉在容器上；② 总览那几块外面还包着一层无名 div，块级容器不做 flex 分配 —— flex 链断在那里，`flex:1` 全落空，得给它一个 `.ov-page`；③ 卡片等高之后，时间轴上的绝对定位气泡多出几像素就会盖住下面那张卡，**被盖的按钮点不到**（e2e 卡在那一步重试到超时），撑满场景的 `.card-b` 要 `overflow:hidden`；④ 每一层都得给 `min-height:0`，漏一层这条链就断在那一层。顺带把任务页的 `max-height: calc(100vh - 268px)`（拿一串写死的层高估可视高度）换成同一条 flex 链。总览下半页分两列（左：时间轴 + 优先级分布，右：活动流），近期活动列表从 100px → 404px；`.tdt` 基准高度 172 → 150，与 `overview.ts` 的 `AXIS_H` 共用一个常量（多开的气泡道在这个基准上往外加）
- [x] **界面小字提示全量审计**（`registry.ts` / 各页面 / `shell/lock.ts`）：逐条核对「是否正式 + 是否与当前功能一致」，**与功能不符的直接删**。查出的真问题：批量新建的说明里还写着 `+1w`（循环字段早已删除，见 `data/markdown.ts` 顶部）—— 留着就是让人照一个不存在的语法写；图谱详情的「根节点」是图论术语（对用户无信息量，改「分区」，与图例一致）；图谱筛选「紧急与重要」改成**「高优先级」**（全应用讨论的都是优先级 P0–P3，这里单用一组形容词会让人以为不是同一个字段）。正式化的一批：空态「这一档里没有任务 —— 换个档位、筛选或清空搜索」→「区间内没有任务，可切换档位、调整筛选或清空搜索」、抽屉「还没有记录 —— 在下面写第一条进展」→「暂无记录，可在下方添加第一条进展」、「记一条进展…」→「记录一条进展」、「认不出任务行。写法：」→「无法识别任务行，格式示例：」、锁屏「口令不对」→「口令错误」、标签管理卡头与编辑区两处重复的操作说明各留一处并改书面语、总览页头说明补上漏掉的「优先级分布」。tooltip 与分区注解（「这条任务是什么 / 经历过什么」）本来就在说当前功能，保留
- [x] **活动报告：条数挪到标签切换组外面**（`pages/activity.ts`）：那个「N 条活动」是**当前标签**在这个范围里的条数，挂在「活动报告」标题旁边会被读成「整份报告共几条」—— 而报告是按标签翻页的，两个数不是一回事。现在排成 `活动报告 … ◀ #健康 ▶ 1 条活动 [搜索]`：放在 ◀ #标签 ▶ **这组的外面**（紧跟 ▶ 之后），不插进组中间 —— 插进去会把标签切换那一组拆散。e2e 锁三点：在组外、不在标签名旁、不在标题旁
- [x] **分区口令的设 / 改 / 清合成一个入口**（`shell/prompt.ts` 新增 `promptWithExtra` + `shell/settings.ts`）：按钮文字恒为「设口令」，设没设用**点亮**（`.btn.sm.on`）表示。以前按有无口令在「设口令」与「改口令 + 清口令」之间换按钮，用户每次都得先判断自己处在哪种状态，而答案只有他自己知道。点开是同一个弹窗：填新口令 = 换一个，留着不填 = 不改，`清除`（danger，靠左）则不再要口令 —— 清口令不再二次确认（弹窗里那个按钮就是明确动作，口令随时能重设，没什么会因此丢掉）。`promptText` 保持返回 `string | null`，新增的 `promptWithExtra` 才带 `extra` 标记
- [x] 口令浮层里「这是防路过的人瞄一眼，不是加密存储……」那段小字撤掉：同理的话 `lock.ts` 顶部已经写了一遍，在弹窗里再来一遍只是逼人多读一段。清口令的确认框也去掉了「之后进入这个分区不再需要口令」—— 标题已经说清了
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
- ~~**时间轴按数据自适应**：窗口 = 粒度下限 ∪ 数据跨度 ∪ 今天~~ → **已推翻**，见下方「档位改成真正的聚焦窗口」
- **真实时钟**：`TODAY` 不再读 `DEMO_TODAY`（写死 09-12，害得时间轴上的「今天」指着 12 号星期六）。`DEMO_TODAY` 现在只负责排布演示数据本身
- ~~**快速新建搬到任务页**，替代页头「＋ 新建任务」~~ → **已推翻**，见下方「新建回到页头」
- 删除类操作的二次确认（`shell/confirm.ts`：抽屉单条 / 管理页批量 / 标签移除，默认焦点给「取消」，Esc 与点遮罩都算取消）
- 图谱：舞台按可用空间铺开（不再写死 900×520）、连线改弧线、节点按离中心的距离错峰入场、右上角加分区标注
- 设置面板 **AI 助手页签已移除**：7 行没有一行接了后端，其中「专用工作区」还指向已删除的目录

已完成（本轮）：

- **持久化**：启动时读库、改完落盘（`data/db.ts`）。Tauri 下走 `tauri-plugin-sql` 直连 SQLite（和原版同一个存储），纯浏览器预览降级到 localStorage —— 刷新不再丢数据
- **分区真正生效**：`partition` 进数据模型，`activeTasks()` 按当前分区过滤。以前 rail 底部的切换器只是弹个 toast
- **Markdown 导入 / 导出**（管理页）：方言实现在 `data/markdown.ts`，抽屉里的 md 源和导出共用同一份序列化
- **热力图对齐真实日历**（`pages/activity.ts` + `styles/pages.css`）：`.hm` 没给 `grid-auto-columns`，隐式列被 `justify-content: stretch` 拉到平分容器 —— 实测列距从 17px 变成 45px，而月份标签按 17px 算绝对位置，整条月份刻度都压在左边一小段；此外标签只按每列周日的月份判定，每月 1 号不在周日时就晚一格（08-01 在 07-26~08-01 那列，标却打到 08-02 那列）。另：「近一月」档位实际是 12 周 = 三个月，标签按周数说话改成了 5 周。冒烟新增断言把「标签列 vs 日历」钉住
- **图谱不再被切一半**（`pages/graph.ts`）：`.gpage` 那条规则从来没命中过任何节点（页面根节点是 `.page`），`.gwrap` 只能退回 min-height 320，而画布高度却按 `innerHeight - 268` 估算成 632 —— `overflow:hidden` 之下底下半张图没了。现在高度由 `#page-graph` 逐层传下来，画布按**量出来的**容器尺寸排布（工具行要先落地再量，否则又会差它那 36px），铺成一圈**椭圆**而不是按短边取半径的正圆 —— 节点占宽从 32% 提到 66%

本轮又推翻了上面两条结论，都是被实际使用打回来的：

- **档位改成真正的聚焦窗口**（`data/timeline.ts`）：档位从「本周 / 本月 / 近 30 天」换成「昨天 / 今天 / 上周 / 本周 / 上月 / 本月」，窗口严格按档位算，不再并数据跨度 —— 以前点「今天」看到的还是好几周，档位名和它实际做的事对不上。代价是窗口外的任务不进表，所以工具栏那个「N / M」计数必须一直看得见（它是「没有静默丢弃」的唯一交代）。窗口算法也搬进了 `data/timeline.ts`：档位名与它覆盖的天数必须是同一份定义
- **新建回到页头，工具行的「快速新建」撤掉**（`pages/tasks.ts` + `pages/taskForm.ts`）：那个框只能填名称和标签，建出来的永远是「待办 + 普通 + 无起止」，必须再开抽屉补一遍。现在页头「＋ 新建任务」开的是与编辑同一套的完整表单
- **抽屉重构**（`pages/taskDrawer.ts`，这个界面是软件核心）：① 分成「任务定义 / 活动时间线」两个有标题有边框的分区（以前两串内容平铺，读到中间分不清哪行属于哪一段）；② 时间补齐——开始只到日期、结束到年月日 + 时分，两者共用 `shell/dateTime.ts` 的同一个组件与同一套排布（列表上写着「⏰ 今天 15:00」，而抽屉里原本只有一个日期框，时分根本没有地方改）；③ 进度既能拖也能直接键入；④ 活动记录可编辑可删除（改过标「已编辑」；系统记录不给编辑入口）；⑤ 底部「删除 / 保存」整体撤掉——所有字段本来就即时保存，那个「保存」实际只做「收起抽屉」，名字在骗人。连带删掉 `shell/drawerPref.ts` 与设置里那行「保存后收起抽屉」
- **优先级终于出现在列表上**（`pages/shared.ts` 的 `urgencyBadge`）：列表行原来那个 8px 圆点是**状态**色（待办蓝 / 进行中橙 / 已完成绿 / 逾期红），优先级根本没画出来 —— 用户看到的「优先级圆点」其实在说状态，自然分不出谁更急。现在列表与编辑界面共用同一套 P0–P3 徽标
- **删掉「循环」字段**：它从来没有行为、界面上也没有编辑入口，只是随 md 文本空转。md 解析仍吃掉旧的 `+1w`（`LEGACY_REPEAT`），否则它会粘进标题变成「写周报 +1w」；存储是整份 JSON，不需要迁移
- **截止文案收敛成一处**（`data/time.ts` 的 `dueTextOf`）：md 导出改为直接读 `end` + `at`，不再 `due.includes("今天")` 倒推日期（加一个「明天」的写法就会导出 `⏰2026-明天`）

标签这一块的三处修正（用户报「维护了多个标签，列表里只有一个，图谱也没体现」）：

- **解析只认带 `#` 的写法**（`data/tags.ts` 的 `normalizeTags`）：`matchAll(/#[^\s#]+/g)` 把「学习 工作」解析成空数组，新建时又被兜底成单个 `#工作` —— 这就是「只剩一个」的根因。现在带不带 `#` 都认、去重、超 3 个明说被忽略了哪几个
- **图谱把标签集合写死在六个预置名里**（`data/mock.ts` 的 `TAG_NAMES`）：新标签不是节点，**挂在它上面的任务在图上根本不画**。现在标签集合按数据现算（预置的在前、新标签按字面接后面），多标签任务仍然只占一个节点，但连到自己拥有的**每一条**标签（原来只连「主标签」，第二标签完全不可见）；历史数据里没标签的任务归「未分类」
- **列表把标签和截止挤在同一行**：三个标签会被 `overflow:hidden` 静默裁掉。现在标题与截止同行、标签单独一行
- 连带：新建必填「任务名 / 标签 / 结束时间」，缺一个都不落库并提示缺什么（以前没写标签会偷偷塞 `#工作`）

- **总览焦点时间轴的「现在」改成读真实时钟**（`data/time.ts` 的 `nowMinutes()`）：`mock.ts` 里那个 `DEMO_NOW_MINUTES = 09:30` 是为了让标记和排在演示日期上的样例任务「说得通」，代价是这块界面永远在说错时间（晚上打开，标记停在上午九点半）。样例数据排在哪天是样例数据的事，界面上「现在」必须是真的；另加一分钟一跳（只在本页可见时重画），免得它变成「写死打开时刻」。e2e 按真实时刻算期望百分比来断言

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

