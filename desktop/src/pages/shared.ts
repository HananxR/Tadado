// ─────────────────────────────────────────────────────────────────────────────
// 页面共用的展示换算：状态文案、日期算数、时间排序键。
//
// 放在这里的判断标准是「两个以上页面要用」，只有一个页面用到的留在那个页面里。
// ─────────────────────────────────────────────────────────────────────────────

import { TASKS } from "../data/mock";
import { dataChanged } from "../data/store";
import type { TimelineRange } from "../data/timeline";
import type { Task, TaskStatus } from "../data/types";
import { confirmAction } from "../shell/confirm";
import { toast } from "../shell/toast";

// 时间基准住在 data/time.ts（data/markdown.ts 也要用，数据层不该反向依赖页面层），
// 这里取进来再原样转出，各页面继续从 shared 拿，import 一行都不用改。
// 只把本文件自己要用的取进作用域，其余纯转发（都 import 进来会触发 unused 报错）
import { DAY_MS, TODAY, dayNumber } from "../data/time";

export {
  DAY_MS,
  TODAY,
  dayNumber,
  isWeekend,
  monthDayText,
  todayMonthDay,
  weekdayOf,
} from "../data/time";

export const STATUS_LABEL: Record<TaskStatus, string> = {
  overdue: "逾期",
  todo: "待办",
  doing: "进行中",
  done: "已完成",
};

export const URGENCY_LABEL = ["紧急", "重要", "关注", "普通"];

/** 状态色变量名。逾期没有 `--overdue`，原型统一借 `--danger`。 */
export const statusVar = (status: TaskStatus): string =>
  status === "overdue" ? "var(--danger)" : `var(--${status})`;

export { pad2 } from "../data/time";

/**
 * 活动时间的排序键。
 *
 * 原型直接拿「今天 08:40」「昨天 17:20」「09-11 09:30」这些展示串做字符串比较，
 * 结果是「昨天」排在「今天」前面（昨 U+6628 > 今 U+4ECA）—— 而卡片标题写着
 * 「按时间倒序」。这里换成按真实时刻排序：相对词先落回具体日期，再乘上天内的
 * 分钟数。展示串本身不变。
 */
export function activitySortKey(at: string, relativeDays: Record<string, number>): number {
  const relative = /^(今天|昨天)\s+(\d{2}):(\d{2})$/.exec(at);
  if (relative) {
    const day = relativeDays[relative[1]];
    if (day !== undefined) {
      return day * 1440 + Number(relative[2]) * 60 + Number(relative[3]);
    }
  }

  const absolute = /^(\d{2})-(\d{2})(?:\s+(\d{2}):(\d{2}))?$/.exec(at);
  if (absolute) {
    const day = dayNumber([Number(absolute[1]), Number(absolute[2])]);
    return day * 1440 + Number(absolute[3] ?? 0) * 60 + Number(absolute[4] ?? 0);
  }

  return 0;
}

/** 相对日期词到天数的映射，供上面的排序使用。 */
export const RELATIVE_DAYS: Record<string, number> = {
  今天: TODAY,
  昨天: TODAY - 1,
};

/**
 * 任务页时间轴的**最小**日期窗口：三档都是以今天为锚点的相对窗口。
 *
 * 注意它是「下限」不是最终窗口：任务页会把数据自身的跨度并进来再向右展开
 * （见 tasks.ts 的 windowFor）。以前这里就是最终窗口，于是「本周」只有 7 列，
 * 而数据是跨月排的 —— 后半截任务整条消失，右边还留着一大片没有任务的空格。
 */
export function timelineWindow(range: TimelineRange): { start: number; days: number } {
  const today = new Date(TODAY * DAY_MS);

  if (range === "month") {
    const year = today.getUTCFullYear();
    const month = today.getUTCMonth();
    const start = Date.UTC(year, month, 1) / DAY_MS;
    // Date.UTC(y, m+1, 0) 就是当月最后一天，闰年和 30/31 天都不用自己判
    const days = Date.UTC(year, month + 1, 0) / DAY_MS - start + 1;
    return { start, days };
  }

  if (range === "30d") return { start: TODAY - 29, days: 30 };

  // 本周从周一开头。getUTCDay 里周日是 0，先换算成「周一 = 0」再回退。
  const offset = today.getUTCDay();
  return { start: TODAY - ((offset + 6) % 7), days: 7 };
}

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
