// ─────────────────────────────────────────────────────────────────────────────
// 跨日续跑：过了午夜，让「今天」重新算一遍。
//
// **为什么需要它**：`data/time.ts` 的 `TODAY` 是**模块加载时算一次**的，而整个数据层
// 的「今天」都从它派生 —— `dayNumber` 补哪一年的年份、档位窗口、热力图的未来格子、
// 逾期判定、`nowStamp()` 写给新活动的时刻。要让它们跟着新的一天走，只能让模块重新
// 求值，也就是**再走一次启动流程**。
//
// **为什么非处理不可**：这个应用是**托盘常驻**的，「关窗口」只是收起常驻，开着过夜
// 属于正常用法。跨过午夜不重来一遍，应用里所有「今天」还停在昨天：逾期不重算、新建
// 任务的默认截止是昨天、新写进去的活动时刻也记在昨天 —— 而问候语与轴上的「现在」
// 读的是真实时钟，于是页面会自相矛盾（问候语说「早上好」，日期还停在昨天）。
//
// **为什么是重载，而不是把 `TODAY` 改成取值函数**：那要动数据层与二十来个调用点
// （`dayNumber` / `timelineWindow` / 热力图 / `countByStatus` …），而且每个派生值都得
// 各自订阅一次「跨日」事件 —— 漏一个就回到今天这个问题。重载走的是**设计里已经有**
// 的那条路：`main.ts` 开头就写着「托盘由 Rust 侧在进程启动时创建，与 webview 生命
// 周期解耦，不会随重载重复叠加」，也就是说重载本来就在这套架构的预期之内，代价只是
// 一次本地读盘。
//
// **只在 Tauri 里跑**：浏览器预览（`npm run dev` / e2e）没有托盘常驻这回事，而 e2e
// 跑到一半被重载会更难查。见 `main.ts` 的调用位置。
// ─────────────────────────────────────────────────────────────────────────────

/** 本地日历日（绝对天数），与 `data/time.ts` 的 `TODAY` 同一个口径。 */
function localDay(): number {
  const now = new Date();
  return Math.floor(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()) / 86_400_000);
}

/**
 * 现在能不能安全重载。
 *
 * 有**未提交的输入**时先不动：批量新建的草稿走 kv、重载后还在，但抽屉底部那段还没点
 * 「按 md 更新任务」的 md 没有别的地方存 —— 重载会把它无声地吃掉。所以这类浮层开着时
 * 跳过，等它关掉之后的那一分钟再来（定时器每分钟问一次，不着急）。
 */
function hasUncommitted(): boolean {
  if (document.querySelector(".modal-card") !== null) return true;
  const md = document.querySelector<HTMLTextAreaElement>("#task-drawer.open textarea.md");
  return md !== null && md.value.trim() !== "";
}

/** 每分钟看一眼日期变没变；变了就重载，让 `TODAY` 跟着走。 */
export function watchDayRollover(): void {
  // 起点是**当前**这一天，不是某个写死的值 —— 应用启动时本来就装着今天的数据
  let seen = localDay();

  window.setInterval(() => {
    const today = localDay();
    if (today === seen) return;
    // 别把没提交的字冲掉。这里**不更新 seen**：下一分钟还要再试
    if (hasUncommitted()) return;
    seen = today;
    location.reload();
  }, 60_000);
}
