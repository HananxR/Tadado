// ─────────────────────────────────────────────────────────────────────────────
// 时间基准。
//
// 从 pages/shared.ts 下沉到这里的原因：data/ 下的模块（markdown.ts 要把「今天」
// 写进导出的 md 里）也要用这些换算，而数据层不该反过来依赖页面层。
// pages/shared.ts 原样再导出一遍，各页面不用改 import。
// ─────────────────────────────────────────────────────────────────────────────

import type { MonthDay } from "./types";

export const DAY_MS = 86400000;

export const pad2 = (value: number): string => String(value).padStart(2, "0");

/**
 * 「今天」的天数。
 *
 * 以前这里取的是 mock 的 DEMO_TODAY（写死 09-12）—— 那是给**种子数据**排布用的
 * 锚点，好让样例里的「今天 15:00」和甘特图上的那一天对得上。但演示归演示：
 * 真把应用拿来用的时候，时间轴上的「今天」必须指着墙上那一天，否则会看到
 * 「12 星期六」这么一列，而日历上明明是 15 号星期二。
 *
 * 现在按本地日历日算（UTC 型 anchor，与 dayNumber 同一套换算），
 * 种子数据仍然留在它自己写的那些日期上。
 */
const now = new Date();
export const TODAY = Math.floor(
  Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()) / DAY_MS,
);

/**
 * [月, 日] → 绝对天数。
 *
 * 模型里只存月和日（见 types.ts 的 MonthDay），年份得有人补上。以前补的是**写死的
 * 2026** —— 种子数据是按那一年写的，所以 2026 里怎么看都对。可 TODAY 读的是真实
 * 时钟：一跨年两边就差 365 天，症状是所有任务同时被判逾期、甘特图一条都不剩
 * （窗口按真实今天算，色条按 2026 算，压根不在一个区间里），而页面上一句解释都没有。
 *
 * 现在按「离今天最近的那一年」补：12 月排次年 1 月的任务、1 月回看去年的记录，
 * 都不会差出一年。MonthDay 依然不存年，只是不再假设今天是哪一年。
 */
export function dayNumber([month, day]: MonthDay): number {
  const year = new Date(TODAY * DAY_MS).getUTCFullYear();
  let best = Math.floor(Date.UTC(year, month - 1, day) / DAY_MS);
  for (const candidate of [year - 1, year + 1]) {
    const value = Math.floor(Date.UTC(candidate, month - 1, day) / DAY_MS);
    if (Math.abs(value - TODAY) < Math.abs(best - TODAY)) best = value;
  }
  return best;
}

/** 天数 → 「YYYY-MM-DD」。年份从天数里读，一处生成：日期框、问候条、下载文件名共用。 */
export const isoDay = (day: number): string => {
  const date = new Date(day * DAY_MS);
  return `${date.getUTCFullYear()}-${pad2(date.getUTCMonth() + 1)}-${pad2(date.getUTCDate())}`;
};

/**
 * 「现在」在当天的分钟数（0–1439）。
 *
 * 读真实时钟，而且是**函数**不是常量：总览的焦点时间轴要按它画「现在」标记，
 * 页面开着不动时那个标记也得跟着钟走。
 *
 * 以前这里读的是 mock 里的 DEMO_NOW_MINUTES（写死 09:30），理由很实在：样例任务
 * 都排在演示那个日期上，用真实时钟会让「现在」和旁边的任务差好几个月。但那是
 * **样例数据自己的问题** —— 界面上「现在」是唯一能证明它知道现在几点的地方，
 * 写死它就等于每天都在说谎（晚上九点打开，标记还停在上午九点半）。
 */
export const nowMinutes = (): number => {
  const now = new Date();
  return now.getHours() * 60 + now.getMinutes();
};

// ─── 活动时刻（epoch 毫秒）────────────────────────────────────────────────────
// 与上面的「天数」共用同一套基准：`stamp = 天数 * DAY_MS + 当天分钟 * 60_000`。
// 为什么不直接用 Date.now()：Date.now() 是真实 UTC 时刻，而这里的天数是**本地
// 日历日**的 anchor（见 TODAY 的说明），两者直接混用会差一个时区 —— 本地 09:12
// 存进去、显示出来会变成 01:12。所以「现在」也要走 nowStamp()。

/** 天数 + 当天分钟 → 时间戳。 */
export const stampOf = (day: number, minutes: number): number => day * DAY_MS + minutes * 60_000;

/** 时间戳落在哪一天（天数的逆运算）。 */
export const dayOfStamp = (stamp: number): number => Math.floor(stamp / DAY_MS);

/** 时间戳是当天的第几分钟。 */
export const minuteOfStamp = (stamp: number): number =>
  Math.floor((stamp - dayOfStamp(stamp) * DAY_MS) / 60_000);

/** 「此刻」的时间戳。写新活动一律用它，不要用 Date.now()（理由见上面）。 */
export const nowStamp = (): number => stampOf(TODAY, nowMinutes());

/**
 * 时间戳 → `MM-DD HH:MM`。**全应用只此一种活动时间写法**：
 * 列表、时间线、导出都是它 —— 存的是时间戳，显示的是绝对日期，
 * 不再出现「今天 / 昨天 / 刚刚」这种过一夜就自相矛盾的词。
 *
 * 这里**不做异常兜底**：模型的不变量是「at 永远是有效时间戳」，由读入口
 * （data/schema.ts 的 normalizeTasks）保证 —— 显示层再去猜一个「时间未知」，
 * 只会让「数据不合法」这件事一直藏着（曾经就把 `NaN-NaN 05:42` 送进了导出的文件）。
 */
export const stampText = (stamp: number): string => {
  const date = new Date(stamp);
  return `${monthDayText(dayOfStamp(stamp))} ${pad2(date.getUTCHours())}:${pad2(date.getUTCMinutes())}`;
};

/**
 * 旧的展示串 → 时间戳。**只在读入口用**（迁移改造前存下的数据），新代码一律
 * 直接写时间戳。
 *
 * 认得出「刚刚」「今天 HH:MM」「昨天 HH:MM」「MM-DD HH:MM」；认不出就用 fallback。
 * 相对词（「昨天」）的换算是**有损**的 —— 那句「昨天」到底是哪一天，只有写下它的
 * 那一刻知道 —— 所以这个函数只负责「给出一个真实存在的时刻」，不负责还原真相。
 */
export function parseStampText(text: string, fallback: number): number {
  if (text === "刚刚") return nowStamp();

  const relative = /^(今天|昨天)\s+(\d{2}):(\d{2})$/.exec(text);
  if (relative) {
    const day = relative[1] === "今天" ? TODAY : TODAY - 1;
    return stampOf(day, Number(relative[2]) * 60 + Number(relative[3]));
  }

  const absolute = /^(\d{2})-(\d{2})\s+(\d{2}):(\d{2})$/.exec(text);
  if (absolute) {
    const day = dayNumber([Number(absolute[1]), Number(absolute[2])]);
    return stampOf(day, Number(absolute[3]) * 60 + Number(absolute[4]));
  }

  return fallback;
}

/** 今天对应的 [月, 日]，新建任务时拿来当起点。 */
export const todayMonthDay = (): MonthDay => {
  const date = new Date(TODAY * DAY_MS);
  return [date.getUTCMonth() + 1, date.getUTCDate()];
};

/** 天数 → [月, 日]，与 dayNumber 互逆。表单里把日期框的值写回模型时用。 */
export const monthDayOf = (day: number): MonthDay => {
  const date = new Date(day * DAY_MS);
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
 * 截止时间的人话文案（列表行上「⏰ …」显示的就是它）。
 *
 * 全应用只此一份：抽屉写截止、列表显示、md 预览都要用它。以前这段拼装在
 * 抽屉的 applyDue 里各写一遍，加上 markdown.ts 又自己反解一遍文案（`due.includes
 * ("今天")` 然后倒推日期）—— 三处各说各话，加一个「明天」的写法就会让导出
 * 变成 `⏰2026-明天`。现在改成：文案只在这里生成，md 导出直接读 end + at。
 */
export const dueTextOf = (day: number, time: string | null): string => {
  if (day === TODAY) return time ? `今天 ${time}` : "今天";
  if (day === TODAY + 1) return time ? `明天 ${time}` : "明天";
  if (day === TODAY - 1) return "昨天";
  return `${monthDayText(day)}${time ? ` ${time}` : ""}`;
};
