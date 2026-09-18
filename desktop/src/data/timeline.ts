// ─────────────────────────────────────────────────────────────────────────────
// 时间轴档位（昨天 / 今天 / 上周 / 本周 / 上月 / 本月）与它覆盖的窗口。
//
// 任务页工具行里那个档位切换是**唯一**入口（设置里曾还有一份，两个入口互相订阅
// 才勉强同步，2026-09-17 撤了）。它是「现在想看多长一段时间」的视图偏好，不持久化
// —— 刷新回到「本周」，所以也不该进设置：进设置就要解释为什么改了不记住。
//
// 放在 data/ 而不是页面里：总览的焦点时间轴也用同一组档位（昨天 / 今天 / 上周…），
// 档位名和它覆盖的天数必须是同一份定义。
//
// 窗口的算法也放在这里：档位名和它覆盖的天数必须是同一份定义。以前档位只当作
// 「最小宽度」，真正的窗口还要并上数据跨度 ∪ 今天，于是点「今天」看到的仍是好几周
// —— 名字和它实际做的事对不上，等于假功能；而一旦改成严格按档位算，跨出窗口的
// 任务就不会再自动出现在表里，这件事必须由使用方（任务页）明确处理，不能悄悄发生。
// ─────────────────────────────────────────────────────────────────────────────

import { DAY_MS, TODAY } from "./time";

export const TIMELINE_RANGES = [
  { value: "yesterday", label: "昨天", short: "昨天" },
  { value: "today", label: "今天", short: "今天" },
  { value: "lastWeek", label: "上周", short: "上周" },
  { value: "week", label: "本周", short: "本周" },
  { value: "lastMonth", label: "上月", short: "上月" },
  { value: "month", label: "本月", short: "本月" },
] as const;

export type TimelineRange = (typeof TIMELINE_RANGES)[number]["value"];

let current: TimelineRange = "week";

export const timelineRange = (): TimelineRange => current;

/** 换档位。重画由调用方负责 —— 只有一个入口，不需要再绕一层事件广播。 */
export function setTimelineRange(value: TimelineRange): void {
  current = value;
}

/** 档位覆盖的日期窗口：起点天数 + 天数。 */
export function timelineWindow(range: TimelineRange): { start: number; days: number } {
  const today = new Date(TODAY * DAY_MS);
  const year = today.getUTCFullYear();
  const month = today.getUTCMonth();

  // 本月 / 上月都是整月。Date.UTC(y, m+1, 0) 就是当月最后一天，
  // 闰年与 30/31 天都不用自己判；月份给负数就是往前一年。
  const wholeMonth = (offset: number): { start: number; days: number } => {
    const start = Date.UTC(year, month + offset, 1) / DAY_MS;
    return { start, days: Date.UTC(year, month + offset + 1, 0) / DAY_MS - start + 1 };
  };

  // 一周从周一开头。getUTCDay 里周日是 0，先换算成「周一 = 0」再回退
  const weekStart = TODAY - ((today.getUTCDay() + 6) % 7);

  switch (range) {
    case "yesterday":
      return { start: TODAY - 1, days: 1 };
    case "today":
      return { start: TODAY, days: 1 };
    case "lastWeek":
      return { start: weekStart - 7, days: 7 };
    case "lastMonth":
      return wholeMonth(-1);
    case "month":
      return wholeMonth(0);
    case "week":
    default:
      return { start: weekStart, days: 7 };
  }
}
