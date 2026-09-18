// ─────────────────────────────────────────────────────────────────────────────
// 活动分析页：热力图 + 标签筛选 + 分标签活动报告。
//
// 热力图的列是「周」，行是「周几」，格子尺寸和间距由 TS 提供给 CSS 变量
// （见 buildHeatmap 里的 --cell / --gap）—— 月份标签要按列号算绝对位置，
// 两个数字放两处迟早对不上。
//
// 活动归属到哪一天靠 at 文案反解（「今天 09:12」/「昨天 17:20」/「09-11 09:30」），
// 和总览的活动流共用 shared.ts 里的 activitySortKey 之外的同一套规则。
// 这是样例数据的形态决定的：真实数据里 at 会是一个时间戳，反解整段删掉即可。
// ─────────────────────────────────────────────────────────────────────────────

import { groupedText, type ExportGroup, type ExportTable } from "../data/export";
import { TASKS } from "../data/mock";
import { activePartitionId } from "../data/partitions";
import { onDataChange } from "../data/store";
import type { Task } from "../data/types";
import { el } from "../shell/dom";
import { exportButton } from "../shell/exportMenu";
import { subscribePages } from "../shell/router";
import { SCHEMES, getScheme, onSchemeChange, setScheme } from "../shell/scheme";
import { jumpToTask } from "./focus";
import { pager } from "./pager";
import {
  DAY_MS,
  REPORT_PAGE_SIZE,
  STATUS_LABEL,
  dayOfStamp,
  isoDay,
  stampText,
  TODAY,
  weekdayOf,
} from "./shared";

/** 行标签。周一开头：网格按周（周一起）切列，标签跟着走才不会错行。 */
const WEEKDAY_ROWS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];

/** 单格活动条数 → 档位。 */
const levelOf = (count: number): number =>
  count === 0 ? 0 : count === 1 ? 1 : count <= 3 ? 2 : count <= 5 ? 3 : 4;

// ─── 页面状态 ────────────────────────────────────────────────────────────────

/**
 * 热力图看的是**一整年**，年份可切，与「看多少天」无关。
 *
 * 这里曾经挂着一排跨度档位（今年 / 近一月 / 近半年 / 近一年），按「从今天往回
 * 数 N 个月」取数据窗口。那套东西和日历视图是打架的：窗口的起止点落在月中间，
 * 网格就既不是自然月、也不是自然周，月末那几天还会因为归属规则掉到窗口外面去
 * （9/28–9/30 就这么消失过）。日历就是日历 —— 网格按年份铺满 12 个自然月，
 * 任务的活动只决定格子怎么上色。要按时间段看，用下面活动报告的快捷范围。
 */
let year = new Date(TODAY * DAY_MS).getUTCFullYear();
/** 报告当前翻到第几个标签（在已勾选的标签里循环）。 */
let reportCursor = 0;
/**
 * 报告翻到第几页（0 起）。换标签 / 换范围 / 改搜索词都回到第一页 ——
 * 停在第 3 页再切个标签，看到的是另一批数据的中段，没有意义。
 */
let reportPage = 0;
/** 报告每页几条。分页器上那个下拉改它。 */
let reportPageSize = REPORT_PAGE_SIZE;
let checked: Set<string> | null = null;

/**
 * 活动报告的搜索词，以及那个输入框本身。
 *
 * 两者都必须是模块级的：这个页面一有变化就 `remount()` 整页重建，
 * 搜索词跟着页面状态一起没了的话，勾一个标签就清空一次搜索条件；
 * 输入框跟着重建的话，每敲一个字焦点就掉一次。
 */
let reportQuery = "";
let searchInput: HTMLInputElement | null = null;

// 刷新后 checked 可能指向已经不存在的标签（比如任务被删掉了）
function checkedTags(): Set<string> {
  const existing = new Set(TASKS.flatMap((task) => task.tags));
  if (checked === null) {
    // 默认只勾有活动的标签 —— 一共 6 个标签，全勾上报告里大半是空的
    checked = new Set([...existing].filter((tag) => tagActivities(tag).length > 0));
  } else {
    for (const tag of [...checked]) if (!existing.has(tag)) checked.delete(tag);
  }
  return checked;
}

// ─── 活动归日 ────────────────────────────────────────────────────────────────
//
// 这里曾经有一个解析函数：把「今天 09:12」/「昨天 17:20」/「09-11 09:30」这几句
// 人话反解回天数，认不出就返回 null（于是「无日期」成了一类要单独交代的数据）。
// 现在 `at` 就是时间戳，归日是一句除法（dayOfStamp），「解析不出」不存在了。

interface ActivityRow {
  task: Task;
  /** 活动时刻（epoch 毫秒）。一行活动归哪一天、显示成什么，都从它算。 */
  at: number;
  text: string;
}

const allActivities = (): ActivityRow[] =>
  TASKS.flatMap((task) => task.activities.map((activity) => ({ task, at: activity.at, text: activity.text })));

function tagActivities(tag: string): ActivityRow[] {
  return allActivities().filter((row) => row.task.tags.includes(tag));
}

// ─── 热力图 ──────────────────────────────────────────────────────────────────

/** 天数 → 周几（0 = 周日）。和 weekdayOf 用的是同一套 UTC 换算。 */
const weekdayNumber = (day: number): number => new Date(day * DAY_MS).getUTCDay();

const monthOf = (day: number): number => new Date(day * DAY_MS).getUTCMonth();

/** [年, 月, 日] → 天数，与 TODAY / dayNumber 同一坐标。 */
const dayNumberOf = (year: number, month: number, date: number): number =>
  Math.floor(Date.UTC(year, month, date) / DAY_MS);

/** 周一开头：把 date 的 getUTCDay（0 = 周日）换成 0 = 周一。 */
const mondayIndex = (day: number): number => (weekdayNumber(day) + 6) % 7;

/** 该日所在周的周一。 */
const weekStart = (day: number): number => day - mondayIndex(day);

/** 一个月在这个网格里的所有列（每列是一周的周一）。 */
interface MonthBlock {
  year: number;
  month: number;
  /** 该月覆盖到的每一周的周一（天数），首尾两周可能是半截的。 */
  weeks: number[];
}

/**
 * 把一年切成 12 个月块，每块都是一张**完整日历**。
 *
 * 每一列是自然周（周一起），每一行是周几；该月有几周就有几列。月初、月末那两列
 * 里不属于本月的日子留空 —— 这是日历本来就有的空位，不是数据缺失。整块里该月的
 * 每一个日期都恰好出现一次，位置由「这天是周几」决定，和任务的活动分布无关。
 *
 * 早先这里是「一周只归一个月」（按周四归属，ISO 那套），结果月尾几天被算到邻月去，
 * 自己块里就出现空洞，看起来像日期丢了。日历就该按日历排。
 */
function yearBlocks(year: number): MonthBlock[] {
  return Array.from({ length: 12 }, (_, month) => {
    const monthFirst = dayNumberOf(year, month, 1);
    const monthEnd = dayNumberOf(year, month + 1, 0);
    const weeks: number[] = [];

    for (let monday = weekStart(monthFirst); monday <= monthEnd; monday += 7) weeks.push(monday);
    return { year, month, weeks };
  });
}

/** 一列（一周）在该月里的第一个日期，用来给列标一个日期序号。 */
function firstDayOfColumnInMonth(monday: number, year: number, month: number): number {
  return Math.max(monday, dayNumberOf(year, month, 1));
}

/**
 * 格子尺寸：按可用宽度反算，让整年铺满整块卡片。
 *
 * 以前格子写死 13px（间距 4px），53 列只占 900px —— 在 1180 宽的窗口里看着还满，
 * 窗口一放大就全挤在左边，右侧空一大片。这里把宽度均分给所有列：先扣掉块内间距、
 * 块间间距和左侧星期列，再除以总列数。上下限是给极端窗口宽度兜底的（太小的格
 * 子点不中，太大的格子会让热力图高得像表格）。
 */
const CELL_MIN = 8;
const CELL_MAX = 22;
const GAP = 3;
const BLOCK_GAP = 12;

function fitCells(root: HTMLElement, totalCols: number, blockCount: number): void {
  const area = root.querySelector<HTMLElement>(".hm-area");
  if (!area) return;
  const available = area.clientWidth;
  // 页面还没显示（别的页签）时量到 0，算出来的格子会是 -N —— 保持上一次的值
  if (available <= 0) return;

  const gaps = (totalCols - blockCount) * GAP + Math.max(0, blockCount - 1) * BLOCK_GAP;
  const cell = Math.min(CELL_MAX, Math.max(CELL_MIN, Math.floor((available - gaps) / totalCols)));
  // 间距也由这里写进 CSS：上面按它们算宽度，CSS 再各写一份的话迟早对不上
  root.style.setProperty("--gap", `${GAP}px`);
  root.style.setProperty("--block-gap", `${BLOCK_GAP}px`);
  root.style.setProperty("--cell", `${cell}px`);
}

function buildHeatmap(): HTMLElement {
  const counts = new Map<number, number>();
  for (const row of allActivities()) {
    const day = dayOfStamp(row.at);
    counts.set(day, (counts.get(day) ?? 0) + 1);
  }

  const blocks = yearBlocks(year);
  const totalCols = blocks.reduce((sum, block) => sum + block.weeks.length, 0);

  const root = el("div", { class: "hm" });
  // 兜底格子尺寸：fitCells 量到真实宽度后会覆盖它（首帧、页面隐藏时用这个值）
  root.style.setProperty("--cell", "13px");

  // 左侧星期列。行高必须和右侧逐行同源，否则标签会一行一行越错越远 ——
  // 首行（月份名）和末行（日期序号）在这里留空占位，两边的高度写死在 CSS 里。
  const labels = el("div", { class: "hm-lab" }, [
    el("span", { class: "hm-sp" }),
    ...WEEKDAY_ROWS.map((text) => el("span", { text })),
    el("span", { class: "hm-sp" }),
  ]);

  const area = el("div", { class: "hm-area" });

  for (const block of blocks) {
    // 追加顺序必须和 CSS 的填充方向一致：网格是 grid-auto-flow: column + 7 行，
    // 也就是**列优先** —— 先铺满一列（周一到周日），再换下一列。
    // 按行优先追加过一版：日期全被放到错误的行上（8 号是周二却画在周三的位置），
    // 整整一年的格子位置都是错的，而它看起来只是「有点怪」。
    const grid = el("div", { class: "hm-grid" });
    for (const monday of block.weeks) {
      for (let weekday = 0; weekday < 7; weekday += 1) {
        const day = monday + weekday;
        // 首末两列里不属于本月的日子：日历本来就有的空位。占位但不上色，
        // 也不可点 —— 它不是一个「没有活动的日期」，而是「这一天不在本月」。
        if (monthOf(day) !== block.month || new Date(day * DAY_MS).getUTCFullYear() !== block.year) {
          grid.append(el("span", { class: "hc blank" }));
          continue;
        }
        if (day > TODAY) {
          grid.append(el("span", { class: "hc future", title: `${isoDay(day)} · 还没到` }));
          continue;
        }
        const count = counts.get(day) ?? 0;
        const box = el("span", { class: `hc h${levelOf(count)}` });
        box.title = `${isoDay(day)} ${weekdayOf(day)} · ${count} 条活动`;
        if (day === TODAY) box.style.outline = "1.5px solid var(--accent)";
        box.addEventListener("click", () => {
          // 点某一天 = 报告只看那天。网格本身不动（日历和任务分布无关），
          // 变的是下面那张报告。
          reportRange = "custom";
          customFrom = day;
          customTo = day;
          remount();
        });
        grid.append(box);
      }
    }

    // 底部日期序号：一列一个数，取该列在本月里的第一个日期（1、8、15…）
    const dateRow = el(
      "div",
      { class: "hm-weeks" },
      block.weeks.map((monday) =>
        el("span", {
          text: String(new Date(firstDayOfColumnInMonth(monday, block.year, block.month) * DAY_MS).getUTCDate()),
        }),
      ),
    );

    const node = el("div", { class: "hm-mo" }, [
      el("div", { class: "hm-mo-t", text: `${block.month + 1} 月` }),
      grid,
      dateRow,
    ]);
    node.style.setProperty("--weeks", String(block.weeks.length));
    area.append(node);
  }

  root.append(labels, area);
  fitCells(root, totalCols, blocks.length);
  return root;
}

/** 色板：四套色阶早就写在 tokens.css 里，这里只是给它一个入口。 */
function schemePicker(): HTMLElement {
  const root = el("div", { class: "hmscheme" }, [el("span", { class: "dim", text: "配色" })]);
  const buttons = SCHEMES.map((item) => {
    const button = el("button", {
      class: `hmsw ${getScheme() === item.id ? "on" : ""}`,
      type: "button",
      title: item.label,
    });
    button.style.background = item.swatch;
    button.addEventListener("click", () => setScheme(item.id));
    return { item, button };
  });

  for (const { button } of buttons) root.append(button);
  onSchemeChange((next) => {
    for (const { item, button } of buttons) button.classList.toggle("on", item.id === next);
  });
  return root;
}

// ─── 活动报告的时间范围 ──────────────────────────────────────────────────────

/**
 * 报告看哪一段时间。
 *
 * 热力图是日历（整年、和任务分布无关），报告才是「按时间段查活动」的地方 ——
 * 以前两者共用一套档位，结果是日历被数据窗口切得七零八落。现在拆开：
 * 年份由热力图的箭头决定，「全年」跟着那个年份走。
 */
type RangeKind = "today" | "yesterday" | "week" | "lastWeek" | "month" | "year" | "custom";

const RANGE_OPTIONS: { id: RangeKind; label: string }[] = [
  { id: "today", label: "今天" },
  { id: "yesterday", label: "昨天" },
  { id: "week", label: "本周" },
  { id: "lastWeek", label: "上周" },
  { id: "month", label: "本月" },
  { id: "year", label: "全年" },
  { id: "custom", label: "指定范围" },
];

let reportRange: RangeKind = "year";
/** 指定范围的两端（天数）。null = 还没选，按全年兜底。 */
let customFrom: number | null = null;
let customTo: number | null = null;

/** 当前范围覆盖的真实日期区间（天数，闭区间）。两端顺序反了就换回来。 */
function rangeDays(): { from: number; to: number } {
  const today = new Date(TODAY * DAY_MS);

  switch (reportRange) {
    case "today":
      return { from: TODAY, to: TODAY };
    case "yesterday":
      return { from: TODAY - 1, to: TODAY - 1 };
    case "week": {
      const from = weekStart(TODAY);
      return { from, to: from + 6 };
    }
    case "lastWeek": {
      const from = weekStart(TODAY) - 7;
      return { from, to: from + 6 };
    }
    case "month":
      return {
        from: dayNumberOf(today.getUTCFullYear(), today.getUTCMonth(), 1),
        to: dayNumberOf(today.getUTCFullYear(), today.getUTCMonth() + 1, 0),
      };
    case "custom": {
      const from = customFrom ?? dayNumberOf(year, 0, 1);
      const to = customTo ?? from;
      return from <= to ? { from, to } : { from: to, to: from };
    }
    case "year":
    default:
      return { from: dayNumberOf(year, 0, 1), to: dayNumberOf(year, 11, 31) };
  }
}

function rangeText(): string {
  const { from, to } = rangeDays();
  return from === to ? isoDay(from) : `${isoDay(from)} – ${isoDay(to)}`;
}

function rangeChips(onPick: () => void): HTMLElement {
  const root = el("div", { class: "chips" });
  for (const option of RANGE_OPTIONS) {
    const chip = el("button", {
      class: `chip ${reportRange === option.id ? "on" : ""}`,
      type: "button",
      text: option.label,
    });
    chip.addEventListener("click", () => {
      reportRange = option.id;
      // 第一次进「指定范围」：从今天起算。不这么做的话日期框是空的、上面的区间
      // 说明却写着「全年」（那是兜底值），两边说的不是一回事。
      if (option.id === "custom" && customFrom === null && customTo === null) {
        customFrom = TODAY;
        customTo = TODAY;
      }
      onPick();
    });
    root.append(chip);
  }
  return root;
}

/** 指定范围的两个日期框。改完立刻重画列表，不整页重建（输入框会丢焦点）。 */
function customRangeInputs(onPick: () => void): HTMLElement {
  const make = (which: "from" | "to"): HTMLInputElement => {
    const input = el("input", { type: "date", class: "act-date" });
    const current = which === "from" ? customFrom : customTo;
    if (current !== null) input.value = isoDay(current);
    input.addEventListener("input", () => {
      const day = input.value ? Math.floor(Date.parse(`${input.value}T00:00:00Z`) / DAY_MS) : null;
      if (which === "from") customFrom = day;
      else customTo = day;
      reportRange = "custom";
      onPick();
    });
    return input;
  };

  return el("div", { class: "act-range" }, [
    make("from"),
    el("span", { class: "dim", text: "至" }),
    make("to"),
  ]);
}

function heatLegend(): HTMLElement {
  return el("div", { class: "hmlegend" }, [
    "少",
    el("i", { class: "l0" }),
    el("i", { class: "l1" }),
    el("i", { class: "l2" }),
    el("i", { class: "l3" }),
    el("i", { class: "l4" }),
    "多",
  ]);
}


/** 年份切换：热力图本身只看一年，箭头翻年。 */
function yearPicker(): HTMLElement {
  const step = (delta: number): void => {
    year += delta;
    // 翻年就是换了一份数据窗口：报告跟着走（回到「全年」档）
    reportRange = "year";
    remount();
  };

  const prev = el("button", { class: "navbtn", type: "button", text: "◀", title: "上一年" });
  prev.addEventListener("click", () => step(-1));
  const next = el("button", { class: "navbtn", type: "button", text: "▶", title: "下一年" });
  next.addEventListener("click", () => step(1));

  const now = new Date(TODAY * DAY_MS).getUTCFullYear();
  const label = el("span", { class: "mono hmyear", text: `${year} 年` });
  label.title = year === now ? "当前年份" : `点一下回到 ${now} 年`;

  const wrap = el("div", { class: "chips" }, [prev, label, next]);
  if (year !== now) {
    label.addEventListener("click", () => {
      year = now;
      reportRange = "year";
      remount();
    });
    wrap.classList.add("hmyear-off");
  }
  return wrap;
}

// ─── 取数（模块级）───────────────────────────────────────────────────────────
// 下面这几个都是模块级函数而不是 mount 里的局部闭包：导出按钮跟着页面一起重画
// （remount 整页重建），而它要导的是**点开菜单那一刻**的查询结果 —— 现算，
// 不捕获 mount 里的任何局部变量。

/** 落在当前范围内的活动行。 */
function datedRowsOf(source: ActivityRow[]): ActivityRow[] {
  const { from, to } = rangeDays();
  return source.filter((row) => {
    const day = dayOfStamp(row.at);
    return day >= from && day <= to;
  });
}

/** 当前范围内有活动的标签（带条数）。 */
function tagStatsNow(): { tag: string; count: number }[] {
  return [...new Set(TASKS.flatMap((task) => task.tags))]
    .sort()
    .map((tag) => ({ tag, count: datedRowsOf(tagActivities(tag)).length }))
    .filter((item) => item.count > 0);
}

/**
 * 本次查询：当前范围 × 勾选标签，按「标签 → 任务 → 活动」三层排好。
 *
 * 一条活动挂在带多个标签的任务上时会被几个标签同时命中，按「任务 + 时间 + 内容」
 * 去重 —— 同一条进展在文件里出现两遍，谁都会以为数据重复了。
 */
function queryGroups(): ExportGroup[] {
  const selection = checkedTags();
  const seen = new Set<string>();
  const groups: ExportGroup[] = [];

  for (const { tag } of tagStatsNow()) {
    if (!selection.has(tag)) continue;

    const rows = datedRowsOf(tagActivities(tag))
      // 去重放在 filter 里顺手记账：只认第一个命中的标签，
      // 所以必须按这里的处理顺序，先来先拿
      .filter((row) => {
        const key = `${row.task.id}|${row.at}|${row.text}`;
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      })
      .sort((a, b) => b.at - a.at);
    if (rows.length === 0) continue;

    // 同一任务的多条活动收在这个任务下面：导出去要能一眼看出「这个任务做了什么」
    const byTask = new Map<string, ActivityRow[]>();
    for (const row of rows) {
      const list = byTask.get(row.task.id);
      if (list) list.push(row);
      else byTask.set(row.task.id, [row]);
    }

    const tasks = [...byTask.values()]
      .map((list) => ({
        title: list[0].task.title,
        status: STATUS_LABEL[list[0].task.status],
        rows: list,
      }))
      .sort((a, b) => b.rows[0].at - a.rows[0].at);

    groups.push({ tag, tasks });
  }

  return groups;
}

const countOf = (groups: ExportGroup[]): number =>
  groups.reduce(
    (sum, group) => sum + group.tasks.reduce((count, entry) => count + entry.rows.length, 0),
    0,
  );


function exportTable(): ExportTable {
  const groups = queryGroups();

  return {
    // 两份文本、同一套层次（生成逻辑在 data/export.ts，任务管理页用的是同一份）。
    // 文件头那行 `<!-- tadado · … -->` 整个去掉了：它是给机器看的元信息，
    // 摆在人的清单顶上只是噪音，而范围 / 条数在界面上本来就看得到
    text: { md: groupedText(groups, "md"), txt: groupedText(groups, "txt") },
    head: ["标签", "#", "任务", "状态", "时间", "内容"],
    rows: groups.flatMap((group) =>
      group.tasks.flatMap((entry, index) =>
        entry.rows.map((row) => [
          group.tag,
          String(index + 1),
          entry.title,
          entry.status ?? "",
          // 三种格式导的是同一批数据，时间都是同一个写法的绝对时间
          stampText(row.at),
          row.text,
        ]),
      ),
    ),
  };
}

// ─── 挂载 ────────────────────────────────────────────────────────────────────

let host: HTMLElement | null = null;

export function mount(target: HTMLElement): void {
  host = target;

  const rows = allActivities();
  // 每条活动都落在某一天（at 是时间戳），所以这里不需要「解析不出就算不了」那一步
  const activeDays = new Set(rows.map((row) => dayOfStamp(row.at))).size;

  const datedRows = datedRowsOf;

  // 当前区间的说明文字。这个节点由 renderList 在每次重画时更新，所以先建出来，
  // 挂在哪一行都行 —— 现在挂在横跨整页的过滤条右侧。
  const rangeTextNode = el("span", { class: "d mono" });

  // ── 热力图卡 ──
  // 网格是这一整年的日历（12 个自然月），任务的活动只决定格子上什么颜色。
  const heatCard = el("div", { class: "card" }, [
    el("div", { class: "card-h" }, [
      el("span", { class: "t", text: "活动热力图" }),
      el("span", {
        class: "d",
        text: `共 ${rows.length} 条活动，分布于 ${activeDays} 天 · 网格为 ${year} 年完整日历，颜色深浅表示当天活动数`,
      }),
      el("span", { class: "grow" }),
      yearPicker(),
    ]),
    el("div", { class: "card-b" }, [buildHeatmap()]),
    el("div", { class: "card-f" }, [heatLegend(), el("span", { class: "grow" }), schemePicker()]),
  ]);

  // ── 标签筛选卡 ──
  // 每个标签在当前范围内的活动数。这份统计是**两侧共用**的：左边列出来的标签，
  // 就是右边报告能翻到的标签。各算一份的话会出现「左边列着 0 条的标签、右边翻到
  // 它却空空如也」——两边都没错，但摆在一起就是不一致。
  const selection = checkedTags();
  const activeTags = tagStatsNow();
  /** 在当前范围里真的有活动、并且被勾选了的标签 —— 报告的切换范围。 */
  const reportTags = activeTags.filter((item) => selection.has(item.tag)).map((item) => item.tag);

  // ── 导出（md / txt / xlsx 三选一，见 shell/exportMenu.ts）─────────────────
  // 与「范围」同一行，但是一个**独立的按钮**，钉在那一行的最右（见下面 rangeBar
  // 末尾的 grow）：它按这个范围取数，所以和范围同行；它不是又一组时间档位，所以
  // 中间留一大段空白 —— 空白 + 按钮与 chip 的样式差异已经把两件事分开了。
  //
  // 导出的是**本次查询**：当前范围 × 所有勾选标签，不是报告正翻到的那一个标签。
  // 数据在点开菜单的那一刻现算（queryGroups 是模块级函数），所以按钮跟着页面
  // 重画也没关系。
  const exportBtn = exportButton({
    table: exportTable,
    baseName: () =>
      `tadado2-活动-${activePartitionId()}-${rangeText().replace(/\s*–\s*/g, "-")}-${queryGroups().length}个标签`,
    countText: () => `${countOf(queryGroups())} 条活动`,
    blocked: () => {
      if (checkedTags().size === 0) return "先在左侧勾选标签";
      return countOf(queryGroups()) === 0 ? `${rangeText()} 没有活动可导出` : "";
    },
  });

  // ── 范围过滤条 ──
  // 横跨整页压在「标签筛选 + 活动报告」之上：它同时决定左边标签行的条数和右边
  // 报告的内容，只挂在报告卡里的话，左边的数字会不跟着动，看着像两套数据。
  //
  // 这一行是**两个功能**，各占一头：从左排起的是范围（标题 + 档位 + 日期框 +
  // 区间说明 —— 那个区间是范围的产物，跟着范围走）；从右排起的是导出。
  // 交互顺序顺着这一行读：先在这里筛出一段时间，再把筛出来的活动导出去。
  const rangeBar = el("div", { class: "act-filter" }, [
    el("span", { class: "d", text: "范围" }),
    rangeChips(remount),
    // 日期框只在选了「指定范围」时才出现：平时摆着两个空框，看着像结果的一部分，
    // 也说不清和哪一档有关。
    ...(reportRange === "custom" ? [customRangeInputs(() => remount())] : []),
    rangeTextNode,
    el("span", { class: "grow" }),
    exportBtn,
  ]);

  // .taglist：标签多到装不下时在这一列内部滚，卡片头与「全选 / 清空」留在原地
  const tagList = el("div", { class: "taglist" });
  for (const { tag, count } of activeTags) {
    const box = el("span", { class: `tcb ${selection.has(tag) ? "on" : ""}` });

    const row = el("div", { class: "tagrow" }, [
      box,
      el("span", { text: tag }),
      el("span", { class: "cnt", text: `${count} 条` }),
    ]);

    row.addEventListener("click", () => {
      if (selection.has(tag)) selection.delete(tag);
      else selection.add(tag);
      box.classList.toggle("on", selection.has(tag));
      reportCursor = 0;
      remount();
    });

    tagList.append(row);
  }

  const filterCard = el("div", { class: "card" }, [
    el("div", { class: "card-h" }, [
      el("span", { class: "t", text: "标签筛选" }),
      el("span", { class: "d", text: `已选 ${reportTags.length}` }),
      el("span", { class: "grow" }),
      (() => {
        const button = el("button", { class: "btn sm", type: "button", text: "全选" });
        button.addEventListener("click", () => {
          // 只全选「当前范围内有活动」的那些：选上没有活动的标签，报告里也看不到
          for (const item of activeTags) selection.add(item.tag);
          reportCursor = 0;
          remount();
        });
        return button;
      })(),
      (() => {
        const button = el("button", { class: "btn sm", type: "button", text: "清空" });
        button.addEventListener("click", () => {
          selection.clear();
          reportCursor = 0;
          remount();
        });
        return button;
      })(),
    ]),
    el("div", { class: "card-b" }, [tagList]),
  ]);

  // ── 活动报告卡 ──
  // 切换范围 = 有活动且被勾选的标签（见上）。以前这里是「所有被勾选的标签」，
  // 于是 ▶ 能翻到在当前范围里一条活动都没有的标签，报告一片空白。
  const selected = reportTags;
  const current = selected.length > 0 ? selected[reportCursor % selected.length] : null;

  // 每条活动都归得到日子（at 是时间戳），不存在「无日期所以没算进来」这一类
  const reportRows = current ? datedRows(tagActivities(current)) : [];
  reportRows.sort((a, b) => b.at - a.at);

  const step = (delta: number): void => {
    if (selected.length === 0) return;
    reportCursor = (reportCursor + delta + selected.length) % selected.length;
    remount();
  };

  const prev = el("button", { class: "navbtn", type: "button", text: "◀", title: "上一个标签" });
  prev.addEventListener("click", () => step(-1));
  const next = el("button", { class: "navbtn", type: "button", text: "▶", title: "下一个标签" });
  next.addEventListener("click", () => step(1));

  // 搜索框是模块级单实例：整页 remount 会把它连焦点一起重建，
  // 「每敲一个字光标就跳一下」的搜索框等于不能用。所以它只建一次，
  // 输入时只重画列表，不 remount。
  if (!searchInput) {
    // 不用 .qc-input（那是任务页「快速新建」的类名）：两个页面都挂同一个类，
    // 选择器就会挑到另一个页面上那个已经隐藏的输入框
    searchInput = el("input", {
      class: "act-search",
      placeholder: "在报告里搜索任务名或内容…",
      style: "width:190px",
    });
    searchInput.value = reportQuery;
  }
  // 收窄：模块级 let 在 if 之后会被 TS 判定为仍可能是 null
  const searchBox = searchInput;

  // .act-list：报告列表吃掉卡片剩余高度（分页器钉在卡内底部）
  const list = el("div", { class: "act-list" });
  const countText = el("span", { class: "d" });
  // 报告是**分页**的：一次查询可能上百条，全倒进卡片会把下面整页撑开
  const pagerBox = el("div");

  const renderList = (): void => {
    const needle = reportQuery.trim().toLowerCase();
    const found = needle
      ? reportRows.filter((row) =>
          `${row.task.title} ${row.text}`.toLowerCase().includes(needle),
        )
      : reportRows;

    const pageCount = Math.max(1, Math.ceil(found.length / reportPageSize));
    if (reportPage >= pageCount) reportPage = pageCount - 1;
    const rows = found.slice(reportPage * reportPageSize, (reportPage + 1) * reportPageSize);

    list.replaceChildren();
    if (rows.length === 0) {
      list.append(
        el("div", {
          class: "empty",
          text: !current
            ? activeTags.length === 0
              ? `${rangeText()} 区间内没有活动`
              : "请在左侧勾选标签"
            : needle
              ? `没有包含「${reportQuery.trim()}」的活动`
              : `${current} 在 ${rangeText()} 区间内没有活动`,
        }),
      );
    } else {
      for (const row of rows) {
        const item = el("div", { class: "act-item" }, [
          el("span", { class: "tm", text: stampText(row.at) }),
          el("span", { class: "c" }, [el("b", { text: row.task.title }), ` · ${row.text}`]),
        ]);
        item.title = "点击打开维护抽屉";
        item.addEventListener("click", () => jumpToTask(row.task.id));
        list.append(item);
      }
    }

    // 过滤时把「筛剩几条 / 一共几条」都写出来，否则看不出是没数据还是被筛掉了
    countText.textContent = current
      ? `${found.length} 条活动${needle ? `（共 ${reportRows.length}）` : ""}`
      : "未选择标签";
    rangeTextNode.textContent = rangeText();

    pagerBox.replaceChildren(
      // 一条都没有时不必摆分页器：那时候「1 / 1」只会让人以为还有一页空的
      found.length === 0
        ? el("span")
        : pager({
            page: reportPage,
            pageCount,
            total: found.length,
            size: reportPageSize,
            onGo: (next) => {
              reportPage = next;
              renderList();
            },
            onSize: (size) => {
              reportPageSize = size;
              reportPage = 0;
              renderList();
            },
          }),
    );
  };

  searchBox.oninput = (): void => {
    reportQuery = searchBox.value;
    reportPage = 0;
    renderList();
  };
  renderList();

  const reportCard = el("div", { class: "card" }, [
    el("div", { class: "card-h" }, [
      el("span", { class: "t", text: "活动报告" }),
      el("span", { class: "grow" }),
      prev,
      el("span", { class: "mono", style: "font-weight:600", text: current ?? "—" }),
      next,
      // 计数放在标签切换组**外面**：它说的是当前这个标签在这个范围里有几条，而
      // 不是那一组的一部分 —— 插进 ◀ #标签 ▶ 中间会把这一组拆散。挂在标题旁边
      // 就更糟，读起来是「整份报告共几条」（报告按标签翻页，两个数不是一回事）
      countText,
      searchBox,
    ]),
    el("div", { class: "card-b" }, [list, pagerBox]),
  ]);

  // 顺序：日历 → 范围条 → 标签筛选 + 报告。范围条横跨整页，管下面整块
  host.append(heatCard, rangeBar, el("div", { class: "split-filter" }, [filterCard, reportCard]));
  // 排完版才量得准格子尺寸。首次 mount 时本页还在隐藏状态（量到 0），真正生效
  // 的是下面「切到本页」那一次。
  requestAnimationFrame(fitHeatmap);
}

/**
 * 重新量一次宽度，把整年铺满卡片。
 *
 * 什么时候需要：切回本页（隐藏时量到的宽度是 0）、窗口变大变小、换跨度档位。
 * 格子尺寸是靠可用宽度反算的，所以这三处必须重算，否则窗口一放大热力图就全缩在
 * 左边 —— 那正是「挤在左侧」的来源：以前格子写死 13px，53 列只占 900px。
 */
function fitHeatmap(): void {
  const root = host?.querySelector<HTMLElement>(".hm");
  if (!root) return;
  const blocks = yearBlocks(year);
  fitCells(
    root,
    blocks.reduce((sum, block) => sum + block.weeks.length, 0),
    blocks.length,
  );
}

subscribePages((id) => {
  if (id === "activity") requestAnimationFrame(fitHeatmap);
});

window.addEventListener("resize", () => requestAnimationFrame(fitHeatmap));

function remount(): void {
  if (!host) return;
  // 换了标签 / 范围就是换了另一批数据，停在原来的页码上没有意义
  reportPage = 0;
  host.replaceChildren();
  mount(host);
}

onDataChange(remount);
