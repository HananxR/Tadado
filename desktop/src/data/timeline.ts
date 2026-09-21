// ─────────────────────────────────────────────────────────────────────────────
// 时间轴档位（昨天 / 今天 / 上周 / 本周 / 上月 / 本月）与它覆盖的窗口。
//
// **现在只有总览的焦点时间轴在用**：任务页工具行那排档位 2026-09-21 撤了（见下面那段）。
// 它是「现在想看多长一段时间」的视图偏好，不持久化 —— 刷新回到默认档。
//
// 放在 data/ 而不是页面里：档位名和它覆盖的天数必须是同一份定义（以前总览的「本周」与
// 任务页的「本周」各写一份，同名的两个按钮给的窗口不一样）。
//
// 窗口的算法也放在这里：以前档位只当作「最小宽度」，真正的窗口还要并上数据跨度 ∪ 今天，
// 于是点「今天」看到的仍是好几周 —— 名字和它实际做的事对不上，等于假功能。
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

/**
 * 任务页那排档位（全部 / 昨天 / 今天 / 上周 / 本周 / 上月 / 本月）**2026-09-21 撤了**。
 *
 * 它 2026-09-20 的用途是「点一下，除了筛出这段时间**动过**的任务，还把这一段范围内的
 * **进度在条上突出来**」；而条在那之后改回了标准甘特（整块实色、不画进度、不按档位切段，
 * 见 DESIGN §4.2），这个用途就没有承载物了 —— 剩下的那件事（只列这段时间动过的任务）
 * 读起来像「看哪一段时间」，实际会让任务成批消失，于是变成「我看到的本周」与「我库里
 * 有的」两套口径，反而不容易理解（2026-09-21 用户：这些没有用）。
 *
 * 想「看最近动过的」有更直白的地方：总览的**近期活动**卡片本来就是按最近活动聚合的
 * （前 50 个任务）；任务页要收窄范围，用状态筛选 / 搜索 / 排序 / 分页就够了。
 */

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
