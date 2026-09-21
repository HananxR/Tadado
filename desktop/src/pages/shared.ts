// ─────────────────────────────────────────────────────────────────────────────
// 页面共用的展示换算：状态文案、日期算数、活动时刻的显示。
//
// 放在这里的判断标准是「两个以上页面要用」，只有一个页面用到的留在那个页面里。
// ─────────────────────────────────────────────────────────────────────────────

import { TASKS } from "../data/mock";
import { dataChanged } from "../data/store";
import type { StatusName, Task, TaskStatus, Urgency } from "../data/types";
import { confirmAction } from "../shell/confirm";
import { el } from "../shell/dom";
import { toast } from "../shell/toast";

// 时间基准住在 data/time.ts（data/markdown.ts 也要用，数据层不该反向依赖页面层），
// 这里取进来再原样转出，各页面继续从 shared 拿，import 一行都不用改。
// 只把本文件自己要用的取进作用域，其余纯转发（都 import 进来会触发 unused 报错）
import { nowStamp, todayMonthDay } from "../data/time";

export {
  DAY_MS,
  TODAY,
  dayNumber,
  dayOfStamp,
  isWeekend,
  isoDay,
  minuteOfStamp,
  monthDayText,
  nowMinutes,
  nowStamp,
  stampText,
  todayMonthDay,
  weekdayOf,
} from "../data/time";

/**
 * 任务是否**今天到期**：有截止 · 截止在今天 · 尚未完成。
 *
 * 抽成函数是因为它有**两个消费方**：总览的「今日到期」指标卡数它，任务页那条
 * 「今日到期」筛选按它列行。两处各写一份，等于给「卡片上写 1、点进去 0 条」留了门 ——
 * 而那正是这一页最容易被投诉的一类问题（数字点不开，或者点开了对不上）。
 *
 * 三个条件都不能省，理由各不同：
 *  · `due !== null` 是「**有没有截止**」的唯一开关。导入的旧数据里有一批没有截止的
 *    任务，它们的 `end` 落在今天（没有别的值可落），只看 `end` 会把它们全算成
 *    「今天到期」—— 那是把「没有这个信息」显示成了一个具体的日子；
 *  · 比 `end` 而不是比 `due` 那句文案：「今天 15:00」和「今天」都得算进来，文案会变，
 *    日期不会；
 *  · `status !== "done"`：已经做完的不用再提醒。
 */
export function isDueToday(task: Task): boolean {
  const today = todayMonthDay();
  return (
    task.due !== null &&
    task.end[0] === today[0] &&
    task.end[1] === today[1] &&
    task.status !== "done"
  );
}

// （这里原来有个 `isOngoing`：「进行中」= 待办 + 进行中 的合并口径。
//   **「待办」2026-09-21 删掉之后两者是同一档**，这个包装就没有内容了 ——
//   四个消费方统一走下面的 `matchesStatus(task, "doing")`。）

/**
 * 任务是否落在某个状态筛选里。
 *
 * 「待办」删掉之后（2026-09-21），这个判定就是**一对一**了 —— 以前只有它是个例外
 * （「进行中」= 待办 + 进行中 的合并口径）。仍然留成一个函数：总览那张卡、任务页那排
 * chip、管理页的筛选、图谱页的过滤，四个消费方共用一个谓词 —— 各写一份就是给
 * 「卡上写 41、点进去 17」留门。
 */
export function matchesStatus(task: Task, filter: TaskStatus | "all"): boolean {
  return filter === "all" || task.status === filter;
}

/**
 * 状态文案。**下标是 `StatusName` 而不是 `TaskStatus`** —— 「待办」作为当前状态已经删了，
 * 但活动记录里还写着它（`from: "todo"`），时间线上要照原样显示「待办 → 进行中」。
 */
export const STATUS_LABEL: Record<StatusName, string> = {
  overdue: "逾期",
  todo: "待办",
  doing: "进行中",
  done: "已完成",
};

/**
 * 改任务状态 —— 全应用只有这一条路径。
 *
 * 以前四个入口各自改 `task.status`（总览勾选框、任务页右键菜单、管理页批量、抽屉
 * 里的状态按钮），**没有一处写活动记录**。后果是：勾了「完成」，近期活动里没有这一
 * 条；「本周完成」也数不到它 —— 完成时间只能退化为结束日，于是「刚完成的这个任务
 * 结束日在上周」就被漏掉。用户做了事，页面上像没发生过。
 *
 * 留痕不只是为了统计：活动时间是这条任务唯一的「什么时候发生的」证据，写下来的
 * 才是历史，没写下来就只能靠日期字段去猜。
 */
export function setTaskStatus(task: Task, status: TaskStatus): void {
  if (task.status === status) return;
  const from = task.status;
  task.status = status;
  // 已完成就是 100%：留个 30% 的「已完成」在列表上自相矛盾
  if (status === "done") task.progress = 100;
  task.activities.unshift({
    at: nowStamp(),
    kind: "status",
    from,
    to: status,
    text: `${STATUS_LABEL[from]} → ${STATUS_LABEL[status]}`,
  });
  dataChanged();
}

export const URGENCY_LABEL = ["紧急", "重要", "关注", "普通"];

/**
 * 带上编号的优先级名：`紧急(P0)`。
 *
 * 名字与编号是两套说法，用户不该自己去记「紧急到底是 P0 还是 P1」。所以凡是**只显示
 * 名字**的地方（总览的优先级分布、任务页那个优先级下拉、任务行的悬停小卡）都走这个
 * 函数 —— 一眼就能和列表里那枚 `P0` 徽标对上。
 *
 * 两处**刻意不用**它：
 *  · `URGENCY_LABEL` 本身不能改。它会被拼进**活动记录的文本**（`紧急 → 关注`，见
 *    taskForm），那句话是写进历史的数据，读起来也该像人话，不该塞进编号；
 *  · 带彩色徽标的地方（编辑面板那排按钮）也不用：徽标本身就是编号，再写一遍就成了
 *    `P0 紧急(P0)`。「有徽标 → 徽标 + 名字；没有徽标 → 名字里带编号」，就这一条规矩。
 */
export const urgencyText = (urgency: Urgency): string =>
  `${URGENCY_LABEL[urgency]}(P${urgency})`;

/**
 * 四档的编号 `[0, 1, 2, 3]`，**带类型**的迭代用。
 *
 * 从 `URGENCY_LABEL` 推出来，所以档位数只有一处定义；有了它，遍历时不用再写
 * `as Urgency`（`URGENCY_LABEL.map((_, level) => …)` 回调里的 `level` 是 `number`，
 * 想当 `Urgency` 用就得断言一次 —— 而断言正是「档位悄悄多一个/少一个」时不会报错的那种写法）。
 */
export const URGENCY_LEVELS: Urgency[] = URGENCY_LABEL.map((_, level) => level as Urgency);

// ─── 一屏多少条 ──────────────────────────────────────────────────────────────
// **不进设置**：每页几条是「这一屏放得下多少」，不是用户偏好；入口就在各表的
// 分页器上。要调默认值 / 档位就在这里改。

/** 每页几条的可选档位 —— 四张表（管理页表格 / 任务页时间轴 / 活动报告 /
 *  总览近期活动）共用这一组，所以每页条数在哪儿都是同一套数。 */
export const PAGE_SIZES = [20, 30, 50, 100];

/**
 * 各表的默认每页。三张「带日期列的表」是 20；**总览近期活动是 50**（2026-09-20 用户
 * 定的：这张卡问的是「最近发生了什么」，20 行只够看半天）。50 后续可能**搬到设置里**
 * 做成可配项 —— 真搬的时候改这一处常量即可（分页器上那个下拉仍是临时的每屏调节）。
 *
 * 分开四个常量不是为了让它们各不相同，而是**想单独调某一张表时不必改全局** ——
 * 比如时间轴一列一天、一屏放 30 行也不挤，那就只把 TASK_PAGE_SIZE 改成 30。
 */
export const PAGE_SIZE = 20; // 管理页表格
export const TASK_PAGE_SIZE = 20; // 任务页时间轴
export const REPORT_PAGE_SIZE = 20; // 活动分析报告

/**
 * 总览近期活动的**上限**：这张卡只摆**最近的 50 个任务**（2026-09-20 用户定的：
 * 「我只想显示近期的 50 条，不想显示太多」）。
 *
 * 它和「每页几条」是两件事：上限是这张卡的定位 —— 一眼看最近发生了什么，**不承担
 * 「翻遍历史」的职责**（那件事归活动分析页）；每页几条只是这一屏放多少。默认每屏
 * 就等于上限，所以平时只有一页（一页时连翻页箭头都不摆）。
 */
export const FEED_LIMIT = 50;
export const FEED_PAGE_SIZE = FEED_LIMIT; // 一屏摆满上限，默认一页看完

/** 总览焦点时间轴（甘特档）最多画几条 —— 它没有分页，是上限。 */
export const GANTT_LIMIT = 20;

/**
 * 优先级配色：**红 → 绿**（tokens.css 的 `--p0`…`--p3`，取现有语义色当停靠点）。
 *
 * 「红=急、绿=稳」不需要解释，四档一眼分得开；字重同时递减（800 → 500），颜色之外
 * 还有一层区分。
 *
 * ⚠️ 与状态色的关系要说清：色相**不再独立**（P0/P1/P3 分别与「逾期 / 进行中 / 已完成」
 * 同色），区分靠形状与位置 —— 状态是行首那个 8px 圆点，优先级是任务列**右端**的 `Px`
 * 文字，一左一右，一个是色块一个是字。曾经用过「与状态同色系的色块」那种做法：
 * 徽标当时是色块，与圆点同色又同样显眼，扫一眼分不出哪个在说什么。
 *
 * 这条规则在列表、编辑表单、总览的优先级分布、抽屉的活动详情里一致。
 */
export const URGENCY_COLORS = [
  "var(--p0)",
  "var(--p1)",
  "var(--p2)",
  "var(--p3)",
];

/**
 * 优先级徽标（P0–P3）：**红阶文字**，越紧急越深越粗（P0 深红加粗 → P3 细体浅红）。
 * 样式在 styles/controls.css 的 `.urg`。
 *
 * 列表上原来只有那个 8px 圆点，而它是**状态色** —— 优先级在列表上根本没有画出来，
 * 用户看到的「优先级圆点」其实是状态。现在优先级有自己的徽标，编辑界面里用同一套，
 * 两处一眼对得上。
 */
export function urgencyBadge(urgency: Urgency): HTMLElement {
  const node = el("span", {
    class: `urg u${urgency}`,
    title: `优先级：${URGENCY_LABEL[urgency]}`,
  });
  node.textContent = `P${urgency}`;
  return node;
}

/**
 * 状态色变量名。
 *
 * 两个特例：逾期没有 `--overdue`（原型统一借 `--danger`）；**「待办」已经没有自己的色了**
 * —— 那档删掉之后，蓝也跟着从色相体系里撤了（见 types.ts 与 tokens.css），而活动记录里
 * 那张旧的「待办 → 进行中」还要着色，让它跟「进行中」同色：两者本来就是同一档的前后两面。
 */
export const statusVar = (status: StatusName): string =>
  status === "overdue"
    ? "var(--danger)"
    : status === "todo"
      ? "var(--doing)"
      : `var(--${status})`;

/** 列表行上的截止文案用得上，与时间基准同一个来源。 */
export { pad2 } from "../data/time";

/**
 * 删除一条任务（含二次确认），返回是否真的删了。
 *
 * 抽屉的单条删除和任务页的右键菜单共用这一条路径：破坏性操作的确认条件与措辞
 * 必须在两处一致，否则用户会以为其中一处「点了就真删」。返回布尔值让调用方自己
 * 决定后续动作 —— 抽屉删完要顺手收起，任务页删完要清掉选中态。
 */
export async function removeTask(task: Task): Promise<boolean> {
  const ok = await confirmAction({
    title: "删除这个任务？",
    detail: `「${task.title}」和它名下的活动时间线会一并移除，删除后无法恢复。`,
    confirmText: "删除任务",
  });
  if (!ok) return false;

  const index = TASKS.findIndex((item) => item.id === task.id);
  if (index >= 0) TASKS.splice(index, 1);
  dataChanged();
  toast(`已删除「${task.title}」`);
  return true;
}
