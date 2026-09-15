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

import { TASKS } from "../data/mock";
import { onDataChange } from "../data/store";
import type { Task } from "../data/types";
import { el } from "../shell/dom";
import { toast } from "../shell/toast";
import { jumpToTask } from "./focus";
import {
  RELATIVE_DAYS,
  activitySortKey,
  dayNumber,
  monthDayText,
  TODAY,
  weekdayOf,
} from "./shared";

/** 热力图跨度，单位是周。 */
const RANGES = [
  { value: 12, label: "近一月" },
  { value: 26, label: "近半年" },
  { value: 52, label: "近一年" },
] as const;

const WEEKDAY_ROWS = ["日", "一", "二", "三", "四", "五", "六"];

/** 单格活动条数 → 档位。 */
const levelOf = (count: number): number =>
  count === 0 ? 0 : count === 1 ? 1 : count <= 3 ? 2 : count <= 5 ? 3 : 4;

// ─── 页面状态 ────────────────────────────────────────────────────────────────

let weeks = 26;
/** 报告当前翻到第几个标签（在已勾选的标签里循环）。 */
let reportCursor = 0;
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

/** 「今天 09:12」/「昨天 17:20」/「09-11 09:30」→ 演示年内的天数。解析不出返回 null。 */
function activityDay(at: string): number | null {
  const relative = /^(今天|昨天)(?:\s|$)/.exec(at);
  if (relative) return RELATIVE_DAYS[relative[1]] ?? null;

  const absolute = /^(\d{2})-(\d{2})(?:\s|$)/.exec(at);
  if (absolute) return dayNumber([Number(absolute[1]), Number(absolute[2])]);

  return null;
}

interface ActivityRow {
  task: Task;
  at: string;
  text: string;
}

const allActivities = (): ActivityRow[] =>
  TASKS.flatMap((task) => task.activities.map((activity) => ({ task, at: activity.at, text: activity.text })));

function tagActivities(tag: string): ActivityRow[] {
  return allActivities().filter((row) => row.task.tags.includes(tag));
}

// ─── 热力图 ──────────────────────────────────────────────────────────────────

function buildHeatmap(wide: boolean): HTMLElement {
  const cell = wide ? 13 : 11;
  const gap = wide ? 4 : 3;

  const counts = new Map<number, number>();
  for (const row of allActivities()) {
    const day = activityDay(row.at);
    if (day === null) continue;
    counts.set(day, (counts.get(day) ?? 0) + 1);
  }

  // 最后一列必须是含今天的那一周，所以起点往前推到那一周的周日
  const todayWeekday = new Date(TODAY * 86400000).getUTCDay();
  const firstDay = TODAY - todayWeekday - (weeks - 1) * 7;

  const block = el("div", { class: "hm-block" });
  block.style.setProperty("--cell", `${cell}px`);
  block.style.setProperty("--gap", `${gap}px`);

  const days = el("div", { class: "hm-days" });
  for (const label of WEEKDAY_ROWS) days.append(el("span", { text: label }));

  // grid-auto-flow: column + 7 行，按周顺序追加就是按列填充，不需要每周围一层
  const grid = el("div", { class: "hm" });
  for (let week = 0; week < weeks; week += 1) {
    for (let weekday = 0; weekday < 7; weekday += 1) {
      const day = firstDay + week * 7 + weekday;
      // 未来那几天不画（不是「0 条活动」，是「还没发生」）
      if (day > TODAY) {
        grid.append(el("span", { class: "hc", style: "background:transparent;cursor:default" }));
        continue;
      }
      const count = counts.get(day) ?? 0;
      const box = el("span", { class: `hc h${levelOf(count)}` });
      box.title = `${monthDayText(day)} ${weekdayOf(day)} · ${count} 条活动`;
      if (day === TODAY) box.style.outline = "1.5px solid var(--accent)";
      box.addEventListener("click", () => {
        toast(
          count === 0
            ? `${monthDayText(day)} · 当天没有活动`
            : `${monthDayText(day)} · ${count} 条活动`,
        );
      });
      grid.append(box);
    }
  }

  // 月份标签：只在月份第一次出现的那一列标一次
  const months = el("div", { class: "hmcols" });
  // 标签是绝对定位的，.hmcols 自己不随网格变宽，靠显式宽度把滚动区域撑到位
  months.style.width = `${weeks * (cell + gap)}px`;
  let lastMonth = -1;
  for (let week = 0; week < weeks; week += 1) {
    const month = new Date((firstDay + week * 7) * 86400000).getUTCMonth();
    if (month === lastMonth) continue;
    lastMonth = month;
    const label = el("span", { text: `${month + 1} 月` });
    label.style.left = `${week * (cell + gap)}px`;
    months.append(label);
  }

  const scroller = el("div", { class: "hmwrap" }, [months, grid]);

  const legend = el("div", { class: "hmlegend" }, [
    "少",
    el("i", { class: "l0" }),
    el("i", { class: "l1" }),
    el("i", { class: "l2" }),
    el("i", { class: "l3" }),
    el("i", { class: "l4" }),
    "多",
  ]);

  block.append(days, scroller, legend);
  return block;
}

function rangeChips(onPick: (value: number) => void): HTMLElement {
  const root = el("div", { class: "chips" });
  for (const range of RANGES) {
    const chip = el("button", {
      class: `chip ${weeks === range.value ? "on" : ""}`,
      type: "button",
      text: range.label,
    });
    chip.addEventListener("click", () => onPick(range.value));
    root.append(chip);
  }
  return root;
}

// ─── 挂载 ────────────────────────────────────────────────────────────────────

let host: HTMLElement | null = null;

export function mount(target: HTMLElement): void {
  host = target;

  const rows = allActivities();
  // 解析不出日期的（抽屉里新追加的「刚刚」）不算一天，否则这个数会虚高
  const activeDays = new Set(
    rows.map((row) => activityDay(row.at)).filter((day) => day !== null),
  ).size;

  // ── 热力图卡 ──
  const heatCard = el("div", { class: "card" }, [
    el("div", { class: "card-h" }, [
      el("span", { class: "t", text: "活动热力图" }),
      el("span", {
        class: "d",
        // 样例数据只覆盖 2026-09-06 起的一周，跨度开大了会显得整张图是空的
        text: `共 ${rows.length} 条活动 · 分布在 ${activeDays} 天（样例数据集中在最近一周）`,
      }),
      el("span", { class: "grow" }),
      rangeChips((value) => {
        weeks = value;
        remount();
      }),
    ]),
    el("div", { class: "card-b" }, [buildHeatmap(true)]),
  ]);

  // ── 标签筛选卡 ──
  const selection = checkedTags();
  const tagList = el("div");
  for (const tag of [...new Set(TASKS.flatMap((task) => task.tags))].sort()) {
    const count = tagActivities(tag).length;
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
      el("span", { class: "d", text: `已选 ${selection.size}` }),
      el("span", { class: "grow" }),
      (() => {
        const button = el("button", { class: "btn sm", type: "button", text: "全选" });
        button.addEventListener("click", () => {
          for (const tag of TASKS.flatMap((task) => task.tags)) selection.add(tag);
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
  const selected = [...selection];
  const current = selected.length > 0 ? selected[reportCursor % selected.length] : null;
  const reportRows = current ? tagActivities(current) : [];
  reportRows.sort(
    (a, b) => activitySortKey(b.at, RELATIVE_DAYS) - activitySortKey(a.at, RELATIVE_DAYS),
  );

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

  const exportButton = el("button", { class: "btn sm", type: "button", text: "导出" });
  exportButton.addEventListener("click", () =>
    toast(current ? `已导出「${current}」的 ${reportRows.length} 条活动（演示）` : "先勾选标签再导出"),
  );

  const list = el("div");
  const countText = el("span", { class: "d" });

  const renderList = (): void => {
    const needle = reportQuery.trim().toLowerCase();
    const rows = needle
      ? reportRows.filter((row) =>
          `${row.task.title} ${row.text}`.toLowerCase().includes(needle),
        )
      : reportRows;

    list.replaceChildren();
    if (rows.length === 0) {
      list.append(
        el("div", {
          class: "empty",
          text: !current
            ? "左侧勾选标签后显示活动"
            : needle
              ? `没有含「${reportQuery.trim()}」的活动`
              : `${current} 暂无活动记录`,
        }),
      );
    } else {
      for (const row of rows) {
        const item = el("div", { class: "act-item" }, [
          el("span", { class: "tm", text: row.at }),
          el("span", { class: "c" }, [el("b", { text: row.task.title }), ` · ${row.text}`]),
        ]);
        item.title = "点击打开维护抽屉";
        item.addEventListener("click", () => jumpToTask(row.task.id));
        list.append(item);
      }
    }

    // 过滤时把「筛剩几条 / 一共几条」都写出来，否则看不出是没数据还是被筛掉了
    countText.textContent = current
      ? `${rows.length} 条活动${needle ? `（共 ${reportRows.length}）` : ""}`
      : "未选择标签";
  };

  searchBox.oninput = (): void => {
    reportQuery = searchBox.value;
    renderList();
  };
  renderList();

  const reportCard = el("div", { class: "card" }, [
    el("div", { class: "card-h" }, [
      el("span", { class: "t", text: "活动报告" }),
      countText,
      el("span", { class: "grow" }),
      prev,
      el("span", { class: "mono", style: "font-weight:600", text: current ?? "—" }),
      next,
      searchBox,
      exportButton,
    ]),
    el("div", { class: "card-b" }, [list]),
  ]);

  host.append(heatCard, el("div", { class: "split-filter" }, [filterCard, reportCard]));
}

function remount(): void {
  if (!host) return;
  host.replaceChildren();
  mount(host);
}

onDataChange(remount);
