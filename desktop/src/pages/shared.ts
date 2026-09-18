// ─────────────────────────────────────────────────────────────────────────────
// 页面共用的展示换算：状态文案、日期算数、活动时刻的显示。
//
// 放在这里的判断标准是「两个以上页面要用」，只有一个页面用到的留在那个页面里。
// ─────────────────────────────────────────────────────────────────────────────

import { TASKS } from "../data/mock";
import { dataChanged } from "../data/store";
import type { Task, TaskStatus, Urgency } from "../data/types";
import { confirmAction } from "../shell/confirm";
import { el } from "../shell/dom";
import { toast } from "../shell/toast";

// 时间基准住在 data/time.ts（data/markdown.ts 也要用，数据层不该反向依赖页面层），
// 这里取进来再原样转出，各页面继续从 shared 拿，import 一行都不用改。
// 只把本文件自己要用的取进作用域，其余纯转发（都 import 进来会触发 unused 报错）
import { nowStamp } from "../data/time";

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

export const STATUS_LABEL: Record<TaskStatus, string> = {
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

// ─── 一屏多少条 ──────────────────────────────────────────────────────────────
// **不进设置**：每页几条是「这一屏放得下多少」，不是用户偏好；入口就在各表的
// 分页器上。要调默认值 / 档位就在这里改。

/** 每页几条的可选档位 —— 四张表（管理页表格 / 任务页时间轴 / 活动报告 /
 *  总览近期活动）共用这一组，所以每页条数在哪儿都是同一套数。 */
export const PAGE_SIZES = [20, 30, 50, 100];

/**
 * 各表的默认每页：都是 20（档位里的第一档）。
 *
 * 分开四个常量不是为了让它们各不相同，而是**想单独调某一张表时不必改全局** ——
 * 比如时间轴一列一天、一屏放 30 行也不挤，那就只把 TASK_PAGE_SIZE 改成 30。
 */
export const PAGE_SIZE = 20; // 管理页表格
export const TASK_PAGE_SIZE = 20; // 任务页时间轴
export const REPORT_PAGE_SIZE = 20; // 活动分析报告
export const FEED_PAGE_SIZE = 20; // 总览近期活动

/** 总览焦点时间轴（甘特档）最多画几条 —— 它没有分页，是上限。 */
export const GANTT_LIMIT = 20;

/** 优先级配色。四档从「紧急」到「普通」，和总览的优先级分布同一套色。 */
export const URGENCY_COLORS = [
  "var(--danger)",
  "var(--doing)",
  "var(--todo)",
  "var(--text-3)",
];

/**
 * 优先级徽标（P0–P3 + 四档色）。
 *
 * 列表上原来只有那个 8px 圆点，而它是**状态色**（待办蓝 / 进行中橙 / 已完成绿 /
 * 逾期红）—— 优先级在列表上根本没有画出来。用户看到的「优先级圆点」其实是状态，
 * 自然分不出谁更急。现在优先级有自己的徽标，编辑界面里用同一套，两处一眼对得上。
 */
export function urgencyBadge(urgency: Urgency): HTMLElement {
  const node = el("span", {
    class: `urg u${urgency}`,
    title: `优先级：${URGENCY_LABEL[urgency]}`,
  });
  node.textContent = `P${urgency}`;
  return node;
}

/** 状态色变量名。逾期没有 `--overdue`，原型统一借 `--danger`。 */
export const statusVar = (status: TaskStatus): string =>
  status === "overdue" ? "var(--danger)" : `var(--${status})`;

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
