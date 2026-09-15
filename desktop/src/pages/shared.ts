// ─────────────────────────────────────────────────────────────────────────────
// 页面共用的展示换算：状态文案、日期算数、时间排序键。
//
// 放在这里的判断标准是「两个以上页面要用」，只有一个页面用到的留在那个页面里。
// ─────────────────────────────────────────────────────────────────────────────

import type { TimelineRange } from "../data/timeline";
import type { MonthDay, TaskStatus } from "../data/types";

export const DAY_MS = 86400000;

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

export const pad2 = (value: number): string => String(value).padStart(2, "0");

/** [月, 日] → 绝对天数。年份锚在 2026：样例数据就是按 2026 写的（见 mock.ts）。 */
export const dayNumber = ([month, day]: MonthDay): number =>
  Date.UTC(2026, month - 1, day) / DAY_MS;

/**
 * 「今天」的天数。
 *
 * 以前这里取的是 mock 的 DEMO_TODAY（写死 09-12）—— 那是给**演示数据**排布用的
 * 锚点，好让样例里的「今天 15:00」和甘特图上的那一天对得上。但演示归演示：
 * 真把应用拿来用的时候，时间轴上的「今天」必须指着墙上那一天，否则会看到
 * 「12 星期六」这么一列，而日历上明明是 15 号星期二。
 *
 * 现在按本地日历日算（UTC 型 anchor，与 dayNumber 同一套换算），
 * 演示数据仍然留在它自己写的那些日期上。
 */
const now = new Date();
export const TODAY = Math.floor(
  Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()) / DAY_MS,
);

/** 今天对应的 [月, 日]，新建任务时拿来当起点。 */
export const todayMonthDay = (): MonthDay => {
  const date = new Date(TODAY * DAY_MS);
  return [date.getUTCMonth() + 1, date.getUTCDate()];
};

const WEEKDAYS = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];

const utcDayOf = (day: number): number => new Date(day * DAY_MS).getUTCDay();

export const weekdayOf = (day: number): string => WEEKDAYS[utcDayOf(day)];

export const isWeekend = (day: number): boolean => {
  const weekday = utcDayOf(day);
  return weekday === 0 || weekday === 6;
};

export const monthDayText = (day: number): string => {
  const date = new Date(day * DAY_MS);
  return `${pad2(date.getUTCMonth() + 1)}-${pad2(date.getUTCDate())}`;
};

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
  const offset = (today.getUTCDay() + 6) % 7;
  return { start: TODAY - offset, days: 7 };
}
