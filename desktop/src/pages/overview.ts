// ─────────────────────────────────────────────────────────────────────────────
// 总览页：问候 + 快速新建 + 指标卡 + 焦点时间轴 + 近期活动 + 紧迫度分布。
//
// 「焦点时间轴」有六档，其实是两套渲染器：
//   昨天 / 今天  —— 以 6:00–24:00 为轴的当日时间线，气泡落在一根轴上
//   上周 / 本周 / 上月 / 本月 —— 甘特图，色条落在日期区间上
// 合成一个函数会让里面一半的分支互相不认识，所以拆成 renderDayAxis /
// renderGantt，由 renderFocus 按当前档位选一个。
//
// 页面整体重建而不是局部更新：树上任何一个数字都可能被抽屉里的操作改掉，
// 逐处做增量更新的收益在这个规模上不如「一眼看出渲染结果 = 数据」。
// ─────────────────────────────────────────────────────────────────────────────

import { activePartition } from "../data/partitions";
import {
  DEMO_NOW_MINUTES,
  DEMO_USER,
  TASKS,
  activeTasks,
  countByStatus,
} from "../data/mock";
import { dataChanged, onDataChange } from "../data/store";
import type { Task } from "../data/types";
import { el } from "../shell/dom";
import { seg } from "../shell/seg";
import { toast } from "../shell/toast";
import { jumpToTask, showTasksWithFilter } from "./focus";
import {
  DAY_MS,
  RELATIVE_DAYS,
  TODAY,
  URGENCY_LABEL,
  activitySortKey,
  dayNumber,
  monthDayText,
  pad2,
  statusVar,
  todayMonthDay,
  weekdayOf,
} from "./shared";

/** 六档时段。前两档走当日轴，后四档走甘特。 */
const FOCUS_MODES = ["昨天", "今天", "上周", "本周", "上月", "本月"] as const;
type FocusMode = (typeof FOCUS_MODES)[number];

const FOCUS_OPTIONS = FOCUS_MODES.map((mode) => ({ value: mode, label: mode }));

let focusMode: FocusMode = "今天";

/** 甘特档位的日期窗口。当日轴档位返回 null。 */
function focusRange(mode: FocusMode): { start: number; days: number } | null {
  switch (mode) {
    case "上周":
      return { start: dayNumber([8, 31]), days: 7 };
    case "本周":
      return { start: dayNumber([9, 7]), days: 7 };
    case "上月":
      return { start: dayNumber([8, 1]), days: 31 };
    case "本月":
      return { start: dayNumber([9, 1]), days: 30 };
    default:
      return null;
  }
}

// ─── 小部件 ──────────────────────────────────────────────────────────────────

function legendItem(label: string, color: string): HTMLElement {
  const dot = el("i");
  dot.style.cssText = `width:7px;height:7px;border-radius:50%;background:${color}`;
  return el("span", { class: "lg" }, [dot, label]);
}

function statusLegend(): HTMLElement {
  return el("div", { class: "legend" }, [
    legendItem("已完成", statusVar("done")),
    legendItem("进行中", statusVar("doing")),
    legendItem("待办", statusVar("todo")),
    legendItem("逾期", statusVar("overdue")),
  ]);
}

// ─── 焦点时间轴：当日轴 ──────────────────────────────────────────────────────

interface Bubble {
  task: Task;
  minutes: number;
  text: string;
  /** 昨天档的气泡代表一条活动记录，没有勾选框也不按状态着色。 */
  activity: boolean;
  /** 逾期任务只有日期没有时刻，钉在最左侧而不是塞进轴里。 */
  pinned: boolean;
}

const AXIS_FROM = 6;
const AXIS_TO = 24;
const AXIS_SPAN = (AXIS_TO - AXIS_FROM) * 60;

const axisPct = (minutes: number): number =>
  ((minutes - AXIS_FROM * 60) / AXIS_SPAN) * 100;

const hhmm = (minutes: number): string =>
  `${pad2(Math.floor(minutes / 60))}:${pad2(minutes % 60)}`;

function renderDayAxis(mode: "今天" | "昨天"): { node: HTMLElement; count: number } {
  const node = el("div", { class: "tdt" });

  const ticks: { text: string; left: number }[] = [];
  for (let hour = AXIS_FROM; hour <= AXIS_TO; hour += 2) {
    ticks.push({ text: `${pad2(hour)}:00`, left: axisPct(hour * 60) });
  }

  // 轴外面还要放「现在」标记和刻度，所以用一层包住轴本身
  node.append(el("div", { class: "tdt-axis" }));
  for (const tick of ticks) {
    const el_ = el("div", { class: "tdt-tick", text: tick.text });
    el_.style.left = `${tick.left}%`;
    node.append(el_);
  }

  const bubbles: Bubble[] = [];

  if (mode === "今天") {
    for (const task of activeTasks()) {
      if (task.status === "overdue") {
        bubbles.push({ task, minutes: 0, text: task.title, activity: false, pinned: true });
        continue;
      }
      if (!task.at) continue;
      const [hour, minute] = task.at.split(":").map(Number);
      bubbles.push({
        task,
        minutes: hour * 60 + minute,
        text: task.title,
        activity: false,
        pinned: false,
      });
    }
  } else {
    for (const task of TASKS) {
      for (const activity of task.activities) {
        const match = /^昨天\s+(\d{2}):(\d{2})$/.exec(activity.at);
        if (!match) continue;
        bubbles.push({
          task,
          minutes: Number(match[1]) * 60 + Number(match[2]),
          text: activity.text,
          activity: true,
          pinned: false,
        });
      }
    }
  }

  bubbles.sort((a, b) => a.minutes - b.minutes);

  // 交替上下，避免同一时段的气泡互相压住
  let side = 0;

  for (const bubble of bubbles) {
    const pct = axisPct(bubble.minutes);
    // 落在轴外的气泡直接丢掉：勉强贴在边缘只会和刻度糊在一起
    if (!bubble.pinned && !bubble.activity && (pct < 1 || pct > 99)) continue;
    if (bubble.activity && (pct < 1 || pct > 97)) continue;

    side = 1 - side;

    const classes = ["tdt-p", side ? "below" : "above"];
    if (bubble.pinned) classes.push("over-pill");
    if (bubble.activity) classes.push("st-plain");
    else classes.push(`st-${bubble.task.status}`);
    if (bubble.task.status === "done") classes.push("is-done");

    const pill = el("div", { class: classes.join(" ") });
    pill.style.left = bubble.pinned ? "1%" : `${pct}%`;

    if (bubble.activity) {
      pill.append(
        el("span", { class: "tdt-tm", text: hhmm(bubble.minutes) }),
        el("span", { class: "tdt-tx", text: bubble.text }),
      );
    } else {
      const box = el("span", { class: "tdt-cb" });
      box.title = bubble.task.status === "done" ? "标记为未完成" : "标记为已完成";
      box.addEventListener("click", (event) => {
        event.stopPropagation();
        const task = bubble.task;
        const reopen = task.status === "done";
        task.status = reopen ? "todo" : "done";
        if (!reopen) task.progress = 100;
        dataChanged();
        toast(reopen ? `「${task.title}」已重新打开` : `「${task.title}」已完成 · 指标卡已更新`);
      });

      pill.append(
        box,
        el("span", { class: "tdt-tx", text: bubble.text }),
        el("span", { class: "tdt-tm", text: bubble.task.at ?? "逾期" }),
      );
    }

    pill.title = `${bubble.task.title} · ${bubble.task.tags.join(" ")} · 点击打开维护抽屉`;
    pill.addEventListener("click", () => jumpToTask(bubble.task.id));
    node.append(pill);
  }

  if (mode === "今天") {
    const now = el("div", { class: "tdt-now" }, [el("span", { text: "现在" })]);
    now.style.left = `${axisPct(DEMO_NOW_MINUTES)}%`;
    node.append(now);
  }

  return { node, count: bubbles.length };
}

// ─── 焦点时间轴：甘特 ────────────────────────────────────────────────────────

function renderGantt(start: number, days: number): { node: HTMLElement; count: number } {
  const node = el("div", { class: "fg" });
  node.append(el("div", { class: "fg-axis" }));

  // 日期多的时候每格都标会糊成一片，按跨度抽稀
  const tickEvery = days > 14 ? 3 : days > 7 ? 2 : 1;
  for (let offset = 0; offset < days; offset += 1) {
    if (offset % tickEvery !== 0 && offset !== days - 1) continue;
    const tick = el("div", { class: "fg-tick", text: monthDayText(start + offset) });
    tick.style.left = `${((offset + 0.5) / days) * 100}%`;
    node.append(tick);
  }

  const clamped = activeTasks()
    .map((task) => ({
      task,
      from: Math.max(dayNumber(task.start), start),
      to: Math.min(dayNumber(task.end), start + days - 1),
    }))
    .filter((item) => item.to >= item.from)
    .sort((a, b) => a.from - b.from || a.to - b.to);

  // 贪心分道：一条道空出来就能给下一个任务用
  const laneEnds: number[] = [];
  const placed = clamped.map((item) => {
    let lane = laneEnds.findIndex((end) => item.from > end);
    if (lane === -1) {
      lane = laneEnds.length;
      laneEnds.push(0);
    }
    laneEnds[lane] = item.to;
    return { ...item, lane };
  });

  const laneCount = Math.max(1, laneEnds.length);
  node.style.height = `${46 + laneCount * 16}px`;

  for (const item of placed) {
    const left = ((item.from - start) / days) * 100;
    const width = ((item.to - item.from + 1) / days) * 100;

    const bar = el("div", { class: `fg-bar st-${item.task.status}` });
    bar.style.left = `${left}%`;
    bar.style.width = `${width}%`;
    bar.style.top = `${32 + item.lane * 16}px`;
    bar.title = `${item.task.title} · ${monthDayText(item.from)} → ${monthDayText(item.to)} · 点击打开`;
    // 太窄的条塞不下文字，硬塞会把色条撑破
    if (width > 13) bar.append(el("b", { text: item.task.title }));

    bar.addEventListener("click", () => jumpToTask(item.task.id));
    node.append(bar);
  }

  if (TODAY >= start && TODAY < start + days) {
    const now = el("div", { class: "fg-now" });
    now.style.left = `${((TODAY - start + 0.5) / days) * 100}%`;
    node.append(now);
  }

  return { node, count: placed.length };
}

// ─── 焦点时间轴：外壳 ────────────────────────────────────────────────────────

/**
 * @param refresh 换档位只需要重画本页。走 dataChanged() 会把图谱也重建一遍，
 *                顺手清掉用户在图上调好的缩放，而档位和图谱毫无关系。
 */
function renderFocus(refresh: () => void): HTMLElement {
  const range = focusRange(focusMode);
  const { node, count } =
    range === null
      ? renderDayAxis(focusMode as "今天" | "昨天")
      : renderGantt(range.start, range.days);

  return el("div", { class: "card" }, [
    el("div", { class: "card-h" }, [
      el("span", { class: "t", text: "焦点时间轴" }),
      el("span", {
        class: "d",
        text: range === null ? "按 6:00 – 24:00 排布 · 勾选框直接改状态" : "按天展示起止区间",
      }),
      el("span", { class: "grow" }),
      seg(FOCUS_OPTIONS, focusMode, (mode) => {
        focusMode = mode;
        refresh();
      }).root,
      el("span", { class: "dim mono", text: `${count} 项` }),
      statusLegend(),
    ]),
    el("div", { class: "card-b" }, [node]),
  ]);
}

// ─── 指标卡 ──────────────────────────────────────────────────────────────────

function tile(
  label: string,
  value: number,
  delta: (Node | string)[],
  variant: "" | "alert" | "focus",
  onClick?: () => void,
): HTMLElement {
  const root = el("div", { class: `tile ${variant} ${onClick ? "clickable" : ""}`.trim() }, [
    el("div", { class: "lbl" }, [el("i"), label]),
    el("div", { class: "num", text: String(value) }),
    el("div", { class: "delta" }, delta),
  ]);
  if (onClick) {
    root.title = "点击查看对应任务";
    root.addEventListener("click", onClick);
  }
  return root;
}

function renderTiles(): HTMLElement {
  const counts = countByStatus();

  // 今日到期 = 今天结束且未完成。判断用「结束日」而不是截止文案：
  // 「今天 15:00」和「今天」都得算进来，文案会变，日期不会。
  // 比对的是**真实的今天**（DEMO_TODAY 是演示数据的排布锚点，不是日期）
  const today = todayMonthDay();
  const dueToday = activeTasks().filter(
    (task) => task.end[0] === today[0] && task.end[1] === today[1] && task.status !== "done",
  ).length;

  // 本周从真实今天往前退到周一，而不是写死某一周的起止
  const weekStart = TODAY - ((new Date(TODAY * DAY_MS).getUTCDay() + 6) % 7);
  const doneThisWeek = TASKS.filter(
    (task) => task.status === "done" && dayNumber(task.end) >= weekStart && dayNumber(task.end) <= weekStart + 6,
  ).length;

  // 「其中 N 个今日更新」直接数活动流，不另外维护一个计数器
  const touchedToday = activeTasks().filter((task) =>
    task.activities.some((activity) => activity.at.startsWith("今天")),
  ).length;

  const earliestOverdue = activeTasks()
    .filter((task) => task.status === "overdue")
    .map((task) => dayNumber(task.end))
    .sort((a, b) => a - b)[0];

  return el("div", { class: "tiles" }, [
    // 「较昨日 / 较上周」需要历史快照，样例里没有可比对的昨天与上周，
    // 这两处是原型里的固定文案，等有了历史数据再换成真实差值。
    tile("今日到期", dueToday, ["较昨日 ", el("b", { text: "+2" })], ""),
    tile(
      "逾期",
      counts.overdue,
      earliestOverdue === undefined ? ["暂无逾期"] : [`最早 ${monthDayText(earliestOverdue)} · 点击查看`],
      "alert",
      () => showTasksWithFilter("overdue"),
    ),
    tile(
      "进行中",
      counts.doing,
      [touchedToday > 0 ? `其中 ${touchedToday} 个今日更新` : "今日暂无更新"],
      "focus",
      () => showTasksWithFilter("doing"),
    ),
    tile("本周完成", doneThisWeek, ["较上周 ", el("b", { text: "+3" })], "", () =>
      showTasksWithFilter("done"),
    ),
  ]);
}

// ─── 近期活动 ────────────────────────────────────────────────────────────────

function renderFeed(): HTMLElement {
  const entries = TASKS.flatMap((task) =>
    task.activities.map((activity) => ({ task, activity })),
  ).sort(
    (a, b) =>
      activitySortKey(b.activity.at, RELATIVE_DAYS) -
      activitySortKey(a.activity.at, RELATIVE_DAYS),
  );

  const list = el("div", { class: "feed" });
  for (const { task, activity } of entries.slice(0, 7)) {
    const row = el("div", { class: "feed-item" }, [
      el("span", { class: "tm", text: activity.at }),
      el("span", { class: "tx" }, [el("b", { text: task.title }), ` · ${activity.text}`]),
    ]);
    row.title = "点击打开维护抽屉";
    row.addEventListener("click", () => jumpToTask(task.id));
    list.append(row);
  }

  return el("div", { class: "card" }, [
    el("div", { class: "card-h" }, [
      el("span", { class: "t", text: "近期活动" }),
      el("span", { class: "d", text: `按时间倒序 · 共 ${entries.length} 条` }),
    ]),
    el("div", { class: "card-b" }, [list]),
  ]);
}

// ─── 紧迫度分布 ──────────────────────────────────────────────────────────────

const URGENCY_COLORS = ["var(--danger)", "var(--doing)", "var(--todo)", "var(--text-3)"];

function renderUrgency(): HTMLElement {
  const buckets = [0, 0, 0, 0];
  for (const task of activeTasks()) buckets[task.urgency] += 1;
  const max = Math.max(1, ...buckets);

  const list = el("div");
  URGENCY_LABEL.forEach((label, level) => {
    const fill = el("i");
    fill.style.width = `${(buckets[level] / max) * 100}%`;
    fill.style.background = URGENCY_COLORS[level];
    list.append(
      el("div", { class: "ubar" }, [
        el("span", { class: "un", text: label }),
        el("span", { class: "tr" }, [fill]),
        el("span", { class: "uc", text: String(buckets[level]) }),
      ]),
    );
  });

  return el("div", { class: "card" }, [
    el("div", { class: "card-h" }, [
      el("span", { class: "t", text: "紧迫度分布" }),
      el("span", { class: "d", text: `${activeTasks().length} 个未归档任务` }),
    ]),
    el("div", { class: "card-b" }, [list]),
  ]);
}

// ─── 问候与快速新建 ──────────────────────────────────────────────────────────

/**
 * 问候条。这里只问候，不建东西 ——
 *
 * 快速新建以前挂在这一管澡页面的输入框上，但总览没有任何「按天 × 任务」的追踪
 * 手段：建完就沉进列表底部，回头找只能靠搜索。任务页有一整条时间轴，建完立刻
 * 出现在今天那一列上，能接着往下追 —— 所以那个输入框整个搬过去了（见 tasks.ts）。
 * 顺带把这里挪走的日期也算成了真实的今天：以前它读 DEMO_TODAY，日历上说今天是
 * 9 月 12 号星期六，而墙上挂着的是 9 月 15 号星期二。
 */
function renderGreet(): HTMLElement {
  return el("div", { class: "greet" }, [
    el("div", {}, [
      el("div", { class: "g1", text: `早上好，${DEMO_USER}` }),
      el("div", {
        class: "g2",
        text: `2026-${monthDayText(TODAY)} · ${weekdayOf(TODAY)} · ${activePartition().name} 分区 · ${activeTasks().length} 个未归档任务`,
      }),
    ]),
  ]);
}

// ─── 挂载 ────────────────────────────────────────────────────────────────────

export function mount(host: HTMLElement): void {
  const root = el("div");

  const render = (): void => {
    root.replaceChildren(
      renderGreet(),
      renderTiles(),
      renderFocus(render),
      el("div", { class: "split-feed" }, [renderFeed(), renderUrgency()]),
    );
  };

  host.append(root);
  render();
  onDataChange(render);
}
