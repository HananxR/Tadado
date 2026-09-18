// ─────────────────────────────────────────────────────────────────────────────
// 总览页：问候 + 快速新建 + 指标卡 + 焦点时间轴 + 近期活动 + 优先级分布。
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
import { activeTasks, countByStatus } from "../data/mock";
import { onDataChange } from "../data/store";
import { TIMELINE_RANGES, timelineWindow, type TimelineRange } from "../data/timeline";
import type { Task, Urgency } from "../data/types";
import { el } from "../shell/dom";
import { currentPage } from "../shell/router";
import { seg } from "../shell/seg";
import { toast } from "../shell/toast";
import { jumpToTask, showTasksWithFilter, showTasksWithUrgency } from "./focus";
import { pager } from "./pager";
import {
  DAY_MS,
  FEED_PAGE_SIZE,
  GANTT_LIMIT,
  TODAY,
  URGENCY_COLORS,
  URGENCY_LABEL,
  dayNumber,
  dayOfStamp,
  isoDay,
  minuteOfStamp,
  monthDayText,
  nowMinutes,
  pad2,
  setTaskStatus,
  stampText,
  statusVar,
  todayMonthDay,
  weekdayOf,
} from "./shared";

/**
 * 六档时段。前两档走当日轴，后四档走甘特。
 *
 * 档位名不再在这里写一遍：`data/timeline.ts` 的 TIMELINE_RANGES 才是定义处，
 * 任务页和设置里的「任务视图」也用那一份。以前这里是六个中文字面量 + 一张写死的
 * 日期表，于是总览的「本周」是 9/7–9/13、任务页的「本周」是今天所在的这一周 ——
 * 同一个按钮名字，两页给的窗口不一样。
 */
const FOCUS_OPTIONS = TIMELINE_RANGES.map((range) => ({
  value: range.value,
  label: range.label,
}));

/** 走当日轴的档位：窗口也是一天，但落点是一根 6:00–24:00 的时刻轴，不是日期区间。 */
const DAY_MODES: ReadonlySet<TimelineRange> = new Set<TimelineRange>(["yesterday", "today"]);

let focusMode: TimelineRange = "today";

/** 近期活动翻到第几页（0 起）。 */
let feedPage = 0;
/** 近期活动每页几条。分页器上那个下拉改它。 */
let feedPageSize = FEED_PAGE_SIZE;

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

/** 这一天的一条活动（已换算成当天的分钟数）。 */
interface AxisEntry {
  task: Task;
  minutes: number;
  /** 活动记录的文本（「创建任务」/「进行中 → 已完成」/ 人写的进展）。 */
  text: string;
}

/** 轴上的一个位置：要么是一条活动，要么是挤在一起的一簇。 */
type AxisItem =
  | ({ kind: "one" } & AxisEntry)
  | { kind: "cluster"; start: number; end: number; items: AxisEntry[] };

/**
 * 相邻活动间隔不到 30 分钟，在轴上必然互相压住 —— 1 小时只占 5% 宽，而一个气泡
 * 最宽 216px。簇内不到 3 条就各排各的：两条分上下两道就放得下，合成簇反而是把
 * 本来一眼能看完的信息藏起来。
 */
const CLUSTER_GAP = 30;
const CLUSTER_MIN = 3;

function clusterize(entries: AxisEntry[]): AxisItem[] {
  const items: AxisItem[] = [];
  let group: AxisEntry[] = [];

  const flush = (): void => {
    if (group.length === 0) return;
    if (group.length >= CLUSTER_MIN) {
      items.push({
        kind: "cluster",
        start: group[0].minutes,
        end: group[group.length - 1].minutes,
        items: group,
      });
    } else {
      for (const entry of group) items.push({ kind: "one", ...entry });
    }
    group = [];
  };

  for (const entry of entries) {
    const last = group[group.length - 1];
    if (last && entry.minutes - last.minutes <= CLUSTER_GAP) group.push(entry);
    else {
      flush();
      group = [entry];
    }
  }
  flush();
  return items;
}

/**
 * 展开的是哪一簇（记簇的起始分钟）。
 *
 * 加道对付得了三五条，对付不了一天几十条 —— 轴会一路长高，高到看不出这是一条
 * 时间轴。所以密集时段合成一簇，平时只占一个位置，点开才看明细。
 */
let openCluster: number | null = null;

/**
 * 焦点时间轴的渲染结果。
 *
 * 右上角的计数直接取 label —— 当日轴和甘特数的不是一回事（一个是「这一天的安排」，
 * 一个是「区间里的任务」），口径由各自的渲染器负责，外壳不做二次解释。
 */
interface AxisView {
  node: HTMLElement;
  label: string;
}

const AXIS_FROM = 6;
const AXIS_TO = 24;
const AXIS_SPAN = (AXIS_TO - AXIS_FROM) * 60;

const axisPct = (minutes: number): number =>
  ((minutes - AXIS_FROM * 60) / AXIS_SPAN) * 100;

const hhmm = (minutes: number): string =>
  `${pad2(Math.floor(minutes / 60))}:${pad2(minutes % 60)}`;

/**
 * 完成勾选框。轴上的气泡和下方「未排时刻」条共用一份 —— 改状态的行为只有一处，
 * 也不会出现「一处能勾、另一处点了没反应」。
 */
function statusBox(task: Task): HTMLElement {
  const box = el("span", { class: "tdt-cb" });
  box.title = task.status === "done" ? "标记为未完成" : "标记为已完成";
  box.addEventListener("click", (event) => {
    event.stopPropagation();
    const reopen = task.status === "done";
    setTaskStatus(task, reopen ? "todo" : "done");
    toast(reopen ? `「${task.title}」已重新打开` : `「${task.title}」已完成 · 指标卡已更新`);
  });
  return box;
}

function renderDayAxis(mode: "today" | "yesterday", refresh: () => void): AxisView {
  const target = mode === "today" ? TODAY : TODAY - 1;
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

  /**
   * 轴上只放**活动**：这一天的活动记录（含新建任务那一条）。
   *
   * 以前这里放的是任务本身 —— 判据是「起止日期盖住今天」+ 有没有填 at。于是结束在
   * 9/12 的任务会杵在 9/16 的轴上写着「08:30」，而旁边的卡片写着「今日到期 2」：
   * 两个数各自都没算错，摆在一起就是同一个「今天」两种口径。
   *
   * 这条轴要回答的是「这一天发生了什么」，不是「这一天该做什么」——后者是任务页
   * 和上面四张指标卡的事。所以没动静的任务不占位置：未完成、当前粒度下接下来
   * 也没有活动的，就不显示。
   */
  const entries: AxisEntry[] = [];
  /** 这一天的活动，但时刻落在 6:00–24:00 之外（或只有日期、没有时刻）的。 */
  const offAxis: { task: Task; note: string }[] = [];
  /** 结束日已经过去、但还没做完的任务 —— 窗口外的任务提示，另起一条。 */
  const late: { task: Task; days: number }[] = [];

  for (const task of activeTasks()) {
    const to = dayNumber(task.end);
    // 过期**只记一笔提示**，不把这个任务的活动一起埋掉：它今天确实动过，「这一天
    // 发生了什么」就该有它。以前这里 continue，于是给一个已过期的任务补一条进展，
    // 那条进展在轴上反而消失了 —— 越忙一天，轴越空
    if (task.status !== "done" && to < target) late.push({ task, days: target - to });

    for (const activity of task.activities) {
      // 时间戳直接拆成「第几天 + 当天第几分钟」，只有落在这一天的才进轴
      if (dayOfStamp(activity.at) !== target) continue;
      const minutes = minuteOfStamp(activity.at);
      const pct = axisPct(minutes);
      if (pct < 1 || pct > 99) {
        // 硬贴在边缘会和刻度糊在一起，所以转去轴下面那条，并写上它的真实时刻
        offAxis.push({ task, note: minutes === 0 ? "无时刻" : hhmm(minutes) });
        continue;
      }
      entries.push({ task, minutes, text: activity.text });
    }
  }

  entries.sort((a, b) => a.minutes - b.minutes);

  // 挤在一起的先合成簇，剩下的再靠 spreadPills 分道 —— 先把数量降下来，分道才
  // 不会把轴撑得老高
  const items = clusterize(entries);

  // 交替上下，避免同一时段的气泡互相压住
  let side = 0;

  for (const item of items) {
    side = 1 - side;

    if (item.kind === "cluster") {
      const pill = el("div", { class: `tdt-p st-plain ${side ? "below" : "above"}` });
      pill.style.left = `${axisPct(Math.round((item.start + item.end) / 2))}%`;
      pill.append(
        el("span", { class: "tdt-tm", text: `${hhmm(item.start)}–${hhmm(item.end)}` }),
        el("span", { class: "tdt-tx", text: `${item.items.length} 条` }),
      );
      pill.title = `${hhmm(item.start)}–${hhmm(item.end)} 这 ${item.items.length} 条挨得太近 · 点击展开`;
      pill.addEventListener("click", () => {
        openCluster = openCluster === item.start ? null : item.start;
        refresh();
      });
      node.append(pill);
      continue;
    }

    const classes = ["tdt-p", side ? "below" : "above", `st-${item.task.status}`];
    if (item.task.status === "done") classes.push("is-done");

    const pill = el("div", { class: classes.join(" ") });
    pill.style.left = `${axisPct(item.minutes)}%`;
    pill.append(
      el("span", { class: "tdt-tm", text: hhmm(item.minutes) }),
      el("span", { class: "tdt-tx", text: item.text }),
    );
    // 气泡是一条活动、不是任务本身，所以没有勾选框 —— 勾一条「已经发生的事」
    // 没有意义。要改状态去列表或抽屉，那里会留一条新的活动，下一分钟就出现在这条轴上
    pill.title = `${hhmm(item.minutes)} · ${item.task.title} · ${item.text}`;
    pill.addEventListener("click", () => jumpToTask(item.task.id));
    node.append(pill);
  }

  if (mode === "today") {
    // 「现在」读真实时钟（以前读的是 mock 里写死的 09:30，晚上打开也停在上午九点半）
    const minutes = nowMinutes();
    const now = el("div", { class: "tdt-now" }, [el("span", { text: "现在" })]);
    now.style.left = `${axisPct(minutes)}%`;
    now.title = `现在 ${hhmm(minutes)}`;
    node.append(now);
  }

  // 轴下面补两条：这一天有安排但没排时刻的，以及过了结束日还没做完的。
  // 包一层是因为轴本身高度写死（AXIS_H），多出来的一条要在它外面。
  const wrap = el("div", { class: "tdt-wrap" }, [node]);

  const chipOf = (task: Task, note: string): HTMLElement => {
    const chip = el("span", {
      class: `tdt-chip st-${task.status}${task.status === "done" ? " is-done" : ""}`,
    }, [
      statusBox(task),
      el("span", { class: "tdt-tx", text: task.title }),
      ...(note ? [el("span", { class: "tdt-tm", text: note })] : []),
    ]);
    chip.title = `${task.title} · ${task.tags.join(" ")} · 点击打开维护抽屉`;
    chip.addEventListener("click", () => jumpToTask(task.id));
    return chip;
  };

  const rowOf = (label: string, items: { task: Task; note: string }[]): HTMLElement =>
    el("div", { class: "tdt-untimed" }, [
      el("span", { class: "lbl", text: label }),
      ...items.map(({ task, note }) => chipOf(task, note)),
    ]);

  // 同一个任务可能有多条无时刻的活动，去重后再列
  const offRows: { task: Task; note: string }[] = [];
  const seen = new Set<string>();
  for (const item of offAxis) {
    if (seen.has(item.task.id)) continue;
    seen.add(item.task.id);
    offRows.push(item);
  }

  if (offRows.length > 0) wrap.append(rowOf("时刻在轴外", offRows));

  // 点开的那一簇：明细列在轴下面 —— 轴上只留一个「N 条」的位置，细节来这里看
  if (openCluster !== null) {
    const open = items.find((item) => item.kind === "cluster" && item.start === openCluster);
    if (open?.kind === "cluster") {
      wrap.append(
        el("div", { class: "tdt-untimed" }, [
          el("span", { class: "lbl", text: `${hhmm(open.start)}–${hhmm(open.end)}` }),
          ...open.items.map(({ task, minutes, text }) => {
            const chip = el("span", { class: `tdt-chip st-${task.status}` }, [
              el("span", { class: "tdt-tm", text: hhmm(minutes) }),
              el("span", { class: "tdt-tx", text: `${task.title} · ${text}` }),
            ]);
            chip.title = `${hhmm(minutes)} · ${task.title} · ${text}`;
            chip.addEventListener("click", () => jumpToTask(task.id));
            return chip;
          }),
        ]),
      );
    }
  }
  if (late.length > 0) {
    wrap.append(
      rowOf("已过期未完成", late.map(({ task, days }) => ({ task, note: `已超 ${days} 天` }))),
    );
  }

  // 计数是「轴上占了几处」：一簇算一处（它代表好几条，簇上写着 N 条，点开看明细）。
  // 写「N 条活动」会在有簇的时候对不上 —— 轴上明明只有 3 个气泡，却说 10 条
  const label = `${items.length + offRows.length} 处`;
  return {
    node: wrap,
    label: late.length > 0 ? `${label} · 过期 ${late.length} 项未清` : label,
  };
}

// ─── 焦点时间轴：甘特 ────────────────────────────────────────────────────────

function renderGantt(start: number, days: number): AxisView {
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

  // 与当日轴同一条判据：窗口内没有活动就不画。条本身仍是「起止区间」，
  // 排的是**计划**在什么时候，但一个在这段时间里毫无动静的任务不该占一行
  // —— 它既不解释过去也不预告接下来，占了位置只是噪音。
  const hasActivityIn = (task: Task): boolean =>
    task.activities.some((activity) => {
      const day = dayOfStamp(activity.at);
      return day >= start && day <= start + days - 1;
    });

  const matched = activeTasks()
    .filter(hasActivityIn)
    .map((task) => ({
      task,
      from: Math.max(dayNumber(task.start), start),
      to: Math.min(dayNumber(task.end), start + days - 1),
    }))
    .filter((item) => item.to >= item.from)
    .sort((a, b) => a.from - b.from || a.to - b.to);

  // 一次最多画 GANTT_LIMIT 条：格子是绝对定位的，几十条会把卡片撑成一张长条
  const clamped = matched.slice(0, GANTT_LIMIT);

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

  // 截断了就把两个数都写出来，别让人以为「只画了这么多」＝「只有这么多」
  return {
    node,
    label:
      matched.length > clamped.length
        ? `${placed.length} / ${matched.length} 项`
        : `${placed.length} 项`,
  };
}

/**
 * 气泡挤在一起时，同侧自动再开一条道 —— 轴自己长高，而不是把任务换到别处去。
 *
 * 为什么不是「重合就切甘特」：甘特的粒度是**天**，而当日轴的粒度是**分钟**。今天
 * 的十几条活动全落在同一格里，切过去照样叠在一起，还顺带把时刻弄丢了 —— 图换了，
 * 拥挤一点没解决，信息反倒少了。重合是「同一粒度里放不下」，解法只能是加道。
 *
 * 只能在进了文档之后做：气泡的 left 是百分比，真实像素位置要等容器有宽度才量得
 * 出来。量不到（页面不可见，rect 全是 0）就保持原样 —— 那时候也没人在看。
 */
const LANE_H = 28;
const LANE_GAP = 6;

/**
 * 轴的基准高度（px）。**必须和 CSS 里 .tdt 的 height 一致** —— 气泡多开一条道
 * 时是在这个基准上往外加的，两处对不上就会要么压着气泡、要么白白空一截。
 */
const AXIS_H = 150;

function spreadPills(node: HTMLElement): void {
  const pills = [...node.querySelectorAll<HTMLElement>(".tdt-p")];
  if (pills.length === 0) return;

  const boxes = pills.map((pill) => pill.getBoundingClientRect());
  if (boxes.every((box) => box.width === 0)) return;

  // 上下两侧各自贪心：同一侧被上一个气泡压住，就往外侧再开一条
  const laneEnds: Record<"above" | "below", number[]> = { above: [], below: [] };
  const lanes = new Map<HTMLElement, number>();

  pills
    .map((pill, index) => ({ pill, box: boxes[index] }))
    .sort((a, b) => a.box.x - b.box.x)
    .forEach(({ pill, box }) => {
      const side = pill.classList.contains("below") ? "below" : "above";
      const ends = laneEnds[side];
      let lane = ends.findIndex((right) => box.x > right + LANE_GAP);
      if (lane === -1) {
        lane = ends.length;
        ends.push(0);
      }
      ends[lane] = box.right;
      lanes.set(pill, lane);
    });

  let deepest = 0;
  for (const [pill, lane] of lanes) {
    const side = pill.classList.contains("below") ? "below" : "above";
    pill.style[side === "below" ? "top" : "bottom"] = `calc(50% + ${14 + lane * LANE_H}px)`;
    deepest = Math.max(deepest, lane);
  }

  // 多开的道得把轴撑开，否则新道会溢出卡片（基准高度见 AXIS_H）
  if (deepest > 0) node.style.height = `${AXIS_H + deepest * LANE_H * 2}px`;
}

// ─── 焦点时间轴：外壳 ────────────────────────────────────────────────────────

/**
 * @param refresh 换档位只需要重画本页。走 dataChanged() 会把图谱也重建一遍，
 *                顺手清掉用户在图上调好的缩放，而档位和图谱毫无关系。
 */
function renderFocus(refresh: () => void): HTMLElement {
  // 窗口来自 data/timeline.ts，与任务页、设置里的「任务视图」同一份定义
  const win = DAY_MODES.has(focusMode) ? null : timelineWindow(focusMode);
  const view = win
    ? renderGantt(win.start, win.days)
    : renderDayAxis(focusMode === "yesterday" ? "yesterday" : "today", refresh);

  // 分道要在下一帧做：此刻节点还没进文档，量不出真实像素
  if (!win) {
    const axis = view.node.querySelector(".tdt");
    if (axis instanceof HTMLElement) requestAnimationFrame(() => spreadPills(axis));
  }

  return el("div", { class: "card" }, [
    el("div", { class: "card-h" }, [
      el("span", { class: "t", text: "焦点时间轴" }),
      el("span", {
        class: "d",
        text: win
          ? `按天展示起止区间 · ${monthDayText(win.start)} – ${monthDayText(win.start + win.days - 1)}`
          : "只列这一天的活动记录 · 6:00 – 24:00",
      }),
      el("span", { class: "grow" }),
      seg(FOCUS_OPTIONS, focusMode, (mode) => {
        focusMode = mode;
        // 展开的簇记的是「当天的第几分钟」，换档位就对不上了，先收起来
        openCluster = null;
        refresh();
      }).root,
      el("span", { class: "dim mono", text: view.label }),
      statusLegend(),
    ]),
    el("div", { class: "card-b" }, [view.node]),
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

/**
 * 任务真正完成的那一天（绝对天数）。
 *
 * 改成「已完成」会写一条活动，那条活动的日期才是完成日 —— 用它算「本周完成」
 * 才对得上用户的心智（「我是昨天做的」，昨天的记录里就有）。没有这条活动时
 * （导入的 md、老数据直接改状态）退化为结束日，总比把任务从统计里漏掉好。
 *
 * 活动在数组里是新的在前，所以取第一条命中的。
 */
function completedOn(task: Task): number {
  for (const activity of task.activities) {
    if (activity.kind !== "status" || activity.to !== "done") continue;
    return dayOfStamp(activity.at);
  }
  return dayNumber(task.end);
}

function renderTiles(): HTMLElement {
  const counts = countByStatus();

  // 今日到期 = **有截止**、截止在今天、且未完成。判断用「结束日」而不是截止文案：
  // 「今天 15:00」和「今天」都得算进来，文案会变，日期不会。
  // 比对的是**真实的今天**（DEMO_TODAY 是演示数据的排布锚点，不是日期）
  //
  // `due !== null` 这条不能省：导入的旧数据里有一批**没有截止**的任务，它们的
  // end 落在今天（没有别的值可落），只看 end 会把它们全算成「今日到期」——
  // 那是把「没有这个信息」显示成了一个具体的日子
  const today = todayMonthDay();
  const dueToday = activeTasks().filter(
    (task) =>
      task.due !== null &&
      task.end[0] === today[0] &&
      task.end[1] === today[1] &&
      task.status !== "done",
  );
  // 副标写「已排时刻 N 项」而不是编一个「较昨日 +2」：这个值点开下面的轴就能对上
  // （排了时刻的会进轴，没排的在「未落在轴上」那条里），编出来的差值对不上任何东西
  const scheduledToday = dueToday.filter((task) => task.at !== null).length;

  // 「其中 N 个今日更新」直接数活动流，不另外维护一个计数器。
  // 判据是活动时刻**落在今天**（以前是拿展示串 startsWith("今天") —— 那句话
  // 只在当天成立，而数据里存的就是这句话，于是隔一天这个数就全错了）
  const touchedToday = activeTasks().filter((task) =>
    task.activities.some((activity) => dayOfStamp(activity.at) === TODAY),
  ).length;

  const earliestOverdue = activeTasks()
    .filter((task) => task.status === "overdue")
    .map((task) => dayNumber(task.end))
    .sort((a, b) => a - b)[0];

  // 本周从真实今天往前退到周一，而不是写死某一周的起止。
  // 完成日和上面其他计数一样只数当前分区 —— 切换分区后每个数字一起变，才叫口径一致
  const weekStart = TODAY - ((new Date(TODAY * DAY_MS).getUTCDay() + 6) % 7);
  const doneIn = (from: number): number =>
    activeTasks().filter(
      (task) =>
        task.status === "done" && completedOn(task) >= from && completedOn(task) <= from + 6,
    ).length;
  const doneThisWeek = doneIn(weekStart);
  const doneLastWeek = doneIn(weekStart - 7);
  const weekDiff = doneThisWeek - doneLastWeek;

  return el("div", { class: "tiles" }, [
    tile(
      "今日到期",
      dueToday.length,
      [
        dueToday.length === 0
          ? "今天没有到期的任务"
          : `其中 ${scheduledToday} 项已排时刻`,
      ],
      "",
    ),
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
    // 名字是「已完成」而不是「本周完成」：点它进的是任务页的「已完成」筛选，
    // 那里列的是**全部**已完成（可能比本周多）。名字说本周、点开是全部，
    // 两个数字对不上，看着就像数据错了 —— 本周的数放到副标里说
    tile(
      "已完成",
      counts.done,
      [
        `本周 ${doneThisWeek} · 较上周 `,
        el("b", { text: weekDiff > 0 ? `+${weekDiff}` : String(weekDiff) }),
      ],
      "",
      () => showTasksWithFilter("done"),
    ),
  ]);
}

// ─── 近期活动 ────────────────────────────────────────────────────────────────

function renderFeed(refresh: () => void): HTMLElement {
  // 只看当前分区：切了分区还看见别处的动态，属于「显示不全」的另一面 —— 显示多余。
  // 归档任务也一并排除，与其余四个页面的口径一致（见 mock.ts 的 activeTasks）
  const entries = activeTasks()
    .flatMap((task) => task.activities.map((activity) => ({ task, activity })))
    .sort(
    // 时间戳直接比大小（以前要比「昨天 / 今天」这些文案的排序键）
    (a, b) => b.activity.at - a.activity.at,
  );

  const list = el("div", { class: "feed" });

  const pageCount = Math.max(1, Math.ceil(entries.length / feedPageSize));
  if (feedPage >= pageCount) feedPage = pageCount - 1;
  const shown = entries.slice(feedPage * feedPageSize, (feedPage + 1) * feedPageSize);

  for (const { task, activity } of shown) {
    const row = el("div", { class: "feed-item" }, [
      el("span", { class: "tm", text: stampText(activity.at) }),
      // 状态色点：一条流里混着已完成和进行中的任务，光看标题分不出来
      el("i", { class: "dot" }),
      el("span", { class: "tx" }, [el("b", { text: task.title }), ` · ${activity.text}`]),
      // 标签挂到右端：这一行本来只有一句「标题 · 进展」，右侧空着也是空着
      ...(task.tags.length > 0
        ? [el("span", { class: "tags", text: task.tags.join(" ") })]
        : []),
    ]);
    // 色点的颜色跟着状态走（statusVar 是变量字符串，不能直接写进 class）
    const dot = row.querySelector(".dot");
    if (dot instanceof HTMLElement) dot.style.background = statusVar(task.status);
    row.title = "点击打开维护抽屉";
    row.addEventListener("click", () => jumpToTask(task.id));
    list.append(row);
  }

  return el("div", { class: "card" }, [
    el("div", { class: "card-h" }, [
      el("span", { class: "t", text: "近期活动" }),
      el("span", { class: "d", text: `按时间倒序 · 共 ${entries.length} 条` }),
    ]),
    el("div", { class: "card-b" }, [
      list,
      // 和其余三张表同一个分页器：一次查询可能上百条，全倒进卡片会把下面整页撑开
      pager({
        page: feedPage,
        pageCount,
        total: entries.length,
        size: feedPageSize,
        onGo: (next) => {
          feedPage = next;
          refresh();
        },
        onSize: (size) => {
          feedPageSize = size;
          feedPage = 0;
          refresh();
        },
      }),
    ]),
  ]);
}

// ─── 优先级分布 ──────────────────────────────────────────────────────────────
// 术语跟着编辑面板走：那里叫「优先级」（P0–P3），这里就不能再叫「紧迫度」——
// 同一样东西两个名字，用户得自己猜是不是同一回事。

function renderPriority(): HTMLElement {
  const buckets = [0, 0, 0, 0];
  for (const task of activeTasks()) buckets[task.urgency] += 1;
  const max = Math.max(1, ...buckets);

  const list = el("div");
  URGENCY_LABEL.forEach((label, level) => {
    const fill = el("i");
    fill.style.width = `${(buckets[level] / max) * 100}%`;
    fill.style.background = URGENCY_COLORS[level];

    const row = el("div", { class: "ubar clickable" }, [
      el("span", { class: "un", text: label }),
      el("span", { class: "tr" }, [fill]),
      el("span", { class: "uc", text: String(buckets[level]) }),
    ]);
    // 以前这一整块点了没反应 —— 一行数字摆在那里，谁都会去点它
    row.title = `点击查看「${label}」的 ${buckets[level]} 个任务`;
    row.addEventListener("click", () => showTasksWithUrgency(level as Urgency));
    list.append(row);
  });

  return el("div", { class: "card" }, [
    el("div", { class: "card-h" }, [
      el("span", { class: "t", text: "优先级分布" }),
      el("span", { class: "d", text: `${activeTasks().length} 个未归档任务 · 点击查看该优先级的任务` }),
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
/**
 * 问候语按墙上的时钟说。
 *
 * 以前这里是写死的「早上好」加一个占位用户名（mock 里的 DEMO_USER = "HananxR"）：
 * 晚上八点打开也说早上好，还把一个谁也不是的名字摆在页面最显眼的位置。问候语
 * 是唯一能证明「这个页面知道现在几点」的地方，读真实时钟才有意义；名字属于用户
 * 资料，在接入之前这里不提。
 */
function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 5) return "夜深了";
  if (hour < 11) return "早上好";
  if (hour < 13) return "中午好";
  if (hour < 18) return "下午好";
  return "晚上好";
}

function renderGreet(): HTMLElement {
  return el("div", { class: "greet" }, [
    el("div", {}, [
      el("div", { class: "g1", text: greeting() }),
      el("div", {
        class: "g2",
        // 年份从天数里读（isoDay），不在页面里写死 2026 —— 跨年之后这一行会一直说 2026
        text: `${isoDay(TODAY)} · ${weekdayOf(TODAY)} · ${activePartition().name} 分区 · ${activeTasks().length} 个未归档任务`,
      }),
    ]),
  ]);
}

// ─── 挂载 ────────────────────────────────────────────────────────────────────

export function mount(host: HTMLElement): void {
  // .ov-page：这几块（问候 / 指标 / 下半页两列）外面还包着一层 —— 而「吃掉
  // 剩余高度」的那条 flex 链必须一路传到 .ov-split。以前这层是没有样式的普通
  // div，块级容器不做 flex 分配，于是它的 flex:1 落空、列表按 20 行的内容高度
  // 把整页顶出 186px（见 pages.css 的一屏到底一节）
  const root = el("div", { class: "ov-page" });

  const render = (): void => {
    root.replaceChildren(
      renderGreet(),
      renderTiles(),
      // 下半页分成两列（2026-09-17）：左列是「今天」—— 焦点时间轴 + 优先级分布，
      // 右列是活动流。原来这四块纵向堆叠，常见窗口高度下装不下 —— 近期活动只剩
      // 三行（列表区实测 100px），要翻页得先滚。分列之后左列两块正好填满，
      // 右列整条高度都归列表
      el("div", { class: "ov-split" }, [
        el("div", { class: "ov-left" }, [renderFocus(render), renderPriority()]),
        el("div", { class: "ov-right" }, [renderFeed(render)]),
      ]),
    );
  };

  // 刷新模型：本页在外壳启动时挂载一次（nav 遍历 PAGES），此后**只靠 dataChanged
  // 事件重画**。页面节点一直留在 DOM 里（切页只是换 class），所以它在后台也跟着变
  // —— 不需要「切回总览」才更新，主区里那些「过期的快照」都是这么避免的。
  // 唯一的定时器是下面那个每分钟的「现在」跳动。
  host.append(root);
  render();
  onDataChange(render);

  // 「现在」标记要跟着钟走：这一页只在数据变化时重画，页面开着不动的话，标记会
  // 一直停在打开那一刻 —— 修掉「写死 09:30」之后，仍然要防它变成「写死打开时刻」。
  // 每分钟重画一次，且只在本页可见时做（别的页面上重画纯属白干）。
  window.setInterval(() => {
    if (currentPage() === "overview") render();
  }, 60_000);
}
