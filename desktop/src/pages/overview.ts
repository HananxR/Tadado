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

import { activeTasks, countByStatus, partitionTasks } from "../data/mock";
import { activePartition } from "../data/partitions";
import { completedOn, onDataChange } from "../data/store";
import { TIMELINE_RANGES, timelineWindow, type TimelineRange } from "../data/timeline";
import type { Activity, Task } from "../data/types";
import { el } from "../shell/dom";
import { currentPage, subscribePages } from "../shell/router";
import { seg } from "../shell/seg";
import { toast } from "../shell/toast";
import {
  jumpToTask,
  showArchivedTasks,
  showTasksDueToday,
  showTasksWithFilter,
  showTasksWithUrgency,
} from "./focus";
import { pager } from "./pager";
import {
  DAY_MS,
  FEED_LIMIT,
  FEED_PAGE_SIZE,
  GANTT_LIMIT,
  TODAY,
  URGENCY_COLORS,
  URGENCY_LEVELS,
  dayNumber,
  dayOfStamp,
  isDueToday,
  isoDay,
  matchesStatus,
  minuteOfStamp,
  monthDayText,
  nowMinutes,
  pad2,
  setTaskStatus,
  stampText,
  statusVar,
  urgencyText,
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
    legendItem("逾期", statusVar("overdue")),
  ]);
}

// ─── 焦点时间轴：当日轴 ──────────────────────────────────────────────────────

/**
 * 这一天的一个任务（已换算成当天的分钟数）。
 *
 * 不是「一条活动」：一个任务今天记三笔就占三个气泡、标题重复三遍，而它一行（一个气泡）
 * 就说得清 —— 与近期活动同一个理由，那张卡也是一个任务一行。
 */
interface AxisEntry {
  task: Task;
  /** 落点：这个任务这一天**最后**一次动的时刻。 */
  minutes: number;
  /** 这个任务这一天的活动条数。 */
  count: number;
}

/** 轴上的一个位置：要么是一个任务，要么是挤在一起的一簇。 */
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

/** 「已过期未完成」那一栏最多摆几条，其余折成「等 N 个」（点它去逾期清单）。 */
const LATE_SHOWN = 3;

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

/**
 * 分钟 → 轴上的百分比。
 *
 * **结果钳在 0–100**：轴只覆盖 06:00–24:00，凌晨的「现在」算出来是负数
 * （01:00 → -27.8%），标记会跑到轴的左边之外 —— 压在别的区块上或者被裁掉，
 * 看着像页面坏了。钳到 0 之后它贴在左端，标题里仍然是真实时刻（「现在 01:00」），
 * 信息不丢。
 *
 * 对气泡没有影响：它们在 `pct < 1 || pct > 99` 时本来就要转到轴下面那条去
 * （见下面的 offAxis），钳制不会把它们留在轴上。
 */
const axisPct = (minutes: number): number =>
  Math.max(0, Math.min(100, ((minutes - AXIS_FROM * 60) / AXIS_SPAN) * 100));

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
    setTaskStatus(task, reopen ? "doing" : "done");
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
   * 轴上放的是**任务**，不是一条条活动（2026-09-20 改）：气泡写「任务名 · 更新了 N 条记录」，
   * N 是这个任务这一天的活动条数，明细不给 —— 一条活动一个气泡时，同一个任务今天记三笔
   * 就占三个位置、标题重复三遍，扫一眼看见的只是「有个任务动了很多次」。
   *
   * 更远的来历：这一块最早放的是任务本身，判据是「起止日期盖住今天」+ 有没有填 at。
   * 于是结束在 9/12 的任务会杵在 9/16 的轴上写着「08:30」，而旁边的卡片写着「今日到期 2」：
   * 两个数各自都没算错，摆在一起就是同一个「今天」两种口径。
   *
   * 这条轴要回答的是「这一天**哪些任务**动过」，不是「这一天该做什么」——后者是任务页
   * 和上面那排指标卡的事。所以没动静的任务不占位置：这一天没有活动的，就不显示。
   */
  const entries: AxisEntry[] = [];
  /** 这一天的活动，但时刻落在 6:00–24:00 之外（或只有日期、没有时刻）的。 */
  const offAxis: { task: Task; note: string }[] = [];
  /** 结束日已经过去、但还没做完的任务 —— 窗口外的任务提示，另起一条。 */
  const late: { task: Task; days: number }[] = [];

  /** 同一个任务这一天的活动收在一起：轴上一个位置只代表一个任务。 */
  const byTask = new Map<string, AxisEntry>();

  for (const task of activeTasks()) {
    const to = dayNumber(task.end);
    // 过期**只记一笔提示**，不把这个任务的活动一起埋掉：它今天确实动过，「这一天
    // 发生了什么」就该有它。以前这里 continue，于是给一个已过期的任务补一条进展，
    // 那条进展在轴上反而消失了 —— 越忙一天，轴越空
    // 口径与「逾期」**同一个谓词**（`status === "overdue"`，即 store.refreshOverdue
    // 的产物）。以前这里写 `status !== "done" && end < target` —— 比「逾期」宽：把
    // 「进行中但已过期」也算进去（refreshOverdue 故意不动 doing，见 store），于是
    // 这一栏报「过期 47 项未清」、点「等 N 个」过去，逾期清单却写着 40 —— 两个数
    // 各自都没算错，摆在一起就像数据坏了。收进同一个口径后：这一栏 = 「逾期」指标卡
    // = 任务页的逾期筛选，三处同一个数。「进行中但已过期」的那些不在这里出现，
    // 是**既有设计**（系统不抢用户手动设的状态），不是漏
    if (task.status === "overdue" && to < target) late.push({ task, days: target - to });

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
      const current = byTask.get(task.id);
      if (!current) {
        byTask.set(task.id, { task, minutes, count: 1 });
        continue;
      }
      current.count += 1;
      // 落点取**最后**一笔：那是这个任务今天最后一次动的时间。早些时候那几笔
      // 不另外占位置 —— 一整天的流水铺在轴上，就没有「一眼看出动过什么」了
      if (minutes > current.minutes) current.minutes = minutes;
    }
  }

  entries.push(...byTask.values());
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
        // 簇里装的是**任务**（一个位置一个任务），不是活动条数
        el("span", { class: "tdt-tx", text: `${item.items.length} 个任务` }),
      );
      pill.title = `${hhmm(item.start)}–${hhmm(item.end)} 这 ${item.items.length} 个任务挨得太近 · 点击展开`;
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
      // 只报**条数**，不铺活动明细：明细在抽屉的时间线里，点这一下就到那儿。
      // 「+N」绿字（2026-09-20）：以前写「任务名 · 更新了 N 条记录」，气泡一宽，
      // 轴上就摆不下几个 —— 一句完整的话挤占了它作为**标记**的空间，数字才是重点
      el("span", { class: "tdt-tx", text: item.task.title }),
      el("span", { class: "tdt-cn", text: `+${item.count}`, title: `今天更新了 ${item.count} 条记录` }),
    );
    // 气泡是**这一天最新的那一笔**的时刻，不是任务本身，所以没有勾选框 —— 勾一条
    // 「已经发生的事」没有意义。要改状态去列表或抽屉，那里会留一条新的活动，
    // 下一分钟就出现在这条轴上
    pill.title = `${hhmm(item.minutes)} · ${item.task.title} · 今天更新了 ${item.count} 条记录`;
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

  const rowOf = (
    label: string,
    items: { task: Task; note: string }[],
    /** 折叠掉的那部分：给个数、给去处（没有去处的话，折叠就是丢信息）。 */
    more?: { text: string; onClick: () => void },
  ): HTMLElement => {
    const row = el("div", { class: "tdt-untimed" }, [
      el("span", { class: "lbl", text: label }),
      ...items.map(({ task, note }) => chipOf(task, note)),
    ]);
    if (more) {
      const rest = el("button", { class: "tdt-more", type: "button", text: more.text });
      rest.title = "到任务页查看完整的逾期清单";
      rest.addEventListener("click", more.onClick);
      row.append(rest);
    }
    return row;
  };

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
          // 展开的也是**任务**：与轴上同一个说法（「+N」报条数，不给明细）
          ...open.items.map(({ task, minutes, count }) => {
            const chip = el("span", { class: `tdt-chip st-${task.status}` }, [
              el("span", { class: "tdt-tm", text: hhmm(minutes) }),
              el("span", { class: "tdt-tx", text: task.title }),
              el("span", { class: "tdt-cn", text: `+${count}` }),
            ]);
            chip.title = `${hhmm(minutes)} · ${task.title} · 今天更新了 ${count} 条记录`;
            chip.addEventListener("click", () => jumpToTask(task.id));
            return chip;
          }),
        ]),
      );
    }
  }
  if (late.length > 0) {
    // 只摆前 LATE_SHOWN 条，其余折成一个「等 N 个」（2026-09-20）：
    // 这一栏是**提示**，不是清单 —— 逾期一多就把它撑成第二张表，把上面的轴挤没了。
    // 而旁边就有「逾期」那张指标卡，点进去是完整清单，所以折叠掉的那些**有去处**；
    // 总条数也还在卡片头那个「过期 N 项未清」里 —— 折的是位置，不是数。
    // 排序按**拖得越久越靠前**（days 大在前）：只留三个位置时，该先看见的是最久的
    late.sort((a, b) => b.days - a.days);
    const head = late.slice(0, LATE_SHOWN).map(({ task, days }) => ({ task, note: `已超 ${days} 天` }));
    // 「等 N 个」的 N 是**总数**（含摆出来的这几条）—— 中文里「A、B、C 等 N 个」
    // 的 N 就是全部；写成「剩余 37 个」那种减出来的数，读者还得自己做一遍减法
    wrap.append(
      rowOf(
        "已过期未完成",
        head,
        late.length > head.length
          ? {
              text: `等 ${late.length} 个`,
              onClick: () => showTasksWithFilter("overdue"),
            }
          : undefined,
      ),
    );
  }

  // 计数是「轴上占了几处」：一簇算一处（它代表好几个任务，簇上写着 N 个任务，点开看明细）。
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

function renderTiles(): HTMLElement {
  const counts = countByStatus();

  // 「归档」那张卡数的是**已归档**的那批（其余四张都只数未归档）。归档不是「不存在」，
  // 是「收进另一处」，所以它得有个看得见的位置 —— 见下面那张卡的说明
  const archived = partitionTasks().filter((task) => task.archived);

  // 今日到期。判据在 pages/shared.ts 的 `isDueToday` —— 任务页那条「今日到期」筛选
  // 用的是**同一个函数**（卡片数它、点进去筛它）。两处各写一份，就等于给「卡片上
  // 写 1、点进去 0 条」留了门，而那正是这一页最容易被投诉的一类问题
  const dueToday = activeTasks().filter(isDueToday);
  // 副标写「已排时刻 N 项」而不是编一个「较昨日 +2」：这个值点开下面的轴就能对上
  // （排了时刻的会进轴，没排的在「未落在轴上」那条里），编出来的差值对不上任何东西
  const scheduledToday = dueToday.filter((task) => task.at !== null).length;

  // 「进行中」= 还没做完、也还没过期的那批。判据走 shared.ts 的 `matchesStatus` ——
  // 任务页与管理页那条「进行中」筛选用的是**同一个谓词**。
  // （「待办」删掉之前这里是个合并口径「待办 + 进行中」；两者现在是同一档，见 types.ts）
  const ongoing = activeTasks().filter((task) => matchesStatus(task, "doing"));

  // 「其中 N 个今日更新」也必须只数**这批**：以前它数的是**全部未归档任务**，于是
  // 那个「其中」是假的 —— 卡上 2 条进行中，副标里那个 1 却可能是某条逾期的，
  // 点进去当然找不到它，只会以为「今天更新过的那条丢了」。
  // 判据仍是活动时刻**落在今天**（以前是拿展示串 startsWith("今天") —— 那句话
  // 只在当天成立，而数据里存的就是这句话，于是隔一天这个数就全错了）
  const touchedToday = ongoing.filter((task) =>
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
          : `其中 ${scheduledToday} 项已排时刻 · 点击查看`,
      ],
      "",
      // 这张卡曾经**点不动**：`tile()` 只在给了 onClick 时才加 clickable / 监听，
      // 而它漏传了 —— 卡片上写着 1 条，点上去没有任何反应。这几张卡现在都是入口，
      // e2e 也改成**遍历界面上所有的 .tile**（不再是一张写死的清单），漏一张就红
      () => showTasksDueToday(),
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
      ongoing.length,
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
    // 归档（2026-09-21 加的第五张）。两个理由：
    // ① 开着自动归档时，一条任务的「完成」与「归档」几乎同时发生 —— 「已完成」那枚数字
    //    会先加后减、看着像什么也没发生，其实它只是**换了个地方**。把归档数摆出来，两处
    //    数字此消彼长，收走的东西就是看得见的，而不是凭空少掉的；
    // ② 它是唯一**不落在任务页**的数字卡：已归档的任务在任务页根本不列（归档的意思就是
    //    「从「任务」界面收走」），所以点它去任务管理页的「已归档」—— 那页是唯一能看见
    //    这批的地方（§4.5）。与其让这张卡点了没反应，不如把它送到能看见那批东西的地方
    tile(
      // 叫「已归档」而不是「归档」：与旁边三张同一句式（已完成 / 进行中 / 逾期），
      // 卡上那个数是「**已经是这个状态的**」有多少
      "已归档",
      archived.length,
      archived.length === 0 ? ["还没有归档的任务"] : ["任务页不再列它 · 点击查看"],
      "",
      () => showArchivedTasks(),
    ),
  ]);
}

// ─── 近期活动 ────────────────────────────────────────────────────────────────
//
// **一个任务一行**，不是一条活动一行（2026-09-20 改）。这是一张「最近哪些任务动过」
// 的清单：同一个任务连着记三条进展就占三行、标题跟着重复三遍，扫一眼看见的其实只是
// 「有一个任务动了很多次」—— 它明明一行就说得清。
//
// 一行里给的是这个任务**最新**的一条活动，折叠掉的条数写在它后面（不写出来就成了
// 丢信息：「动过一次」和「动过八次、只看见最后一条」在页面上长得一模一样）；
// 完整的过程在抽屉的时间线里，点这一行就到那儿。
//
// 排序跟着**最新一次活动**走：聚成任务之后，「每一条活动的时间」这个排序键就没有了。

/** 近期活动的一行 = 一个任务（+ 它最新的一条活动 + 它被折叠了几条）。 */
interface FeedEntry {
  task: Task;
  /** 这个任务最新的一条活动。 */
  latest: Activity;
  /** 这个任务一共有几条活动。 */
  count: number;
}

function renderFeed(refresh: () => void): HTMLElement {
  // 只看当前分区：切了分区还看见别处的动态，属于「显示不全」的另一面 —— 显示多余。
  // 归档任务也一并排除，与其余四个页面的口径一致（见 mock.ts 的 activeTasks）
  const entries: FeedEntry[] = [];

  for (const task of activeTasks()) {
    // 一条活动都没有的任务没有「近期」可言 —— 它还没动过
    if (task.activities.length === 0) continue;
    entries.push({
      task,
      latest: task.activities.reduce((newest, item) => (item.at > newest.at ? item : newest)),
      count: task.activities.length,
    });
  }

  // 时间戳直接比大小（以前要比「昨天 / 今天」这些文案的排序键）
  entries.sort((a, b) => b.latest.at - a.latest.at);

  // 只留**最近的 FEED_LIMIT 个任务**（2026-09-20 用户定的：这张卡只显示近期 50 条，
  // 不想显示太多）。上限是这张卡的定位 —— 一眼看最近发生了什么，**不承担「翻遍历史」
  // 的职责**（那件事归活动分析页，那边有标签/时间范围/分页）。所以这里直接截断，
  // 分页器只在**这 50 条以内**翻（默认每屏就摆满，平时只有一页、连箭头都不出现）
  const recent = entries.slice(0, FEED_LIMIT);

  const list = el("div", { class: "feed" });

  const pageCount = Math.max(1, Math.ceil(recent.length / feedPageSize));
  if (feedPage >= pageCount) feedPage = pageCount - 1;
  const shown = recent.slice(feedPage * feedPageSize, (feedPage + 1) * feedPageSize);
  /** 这一屏看到「最近第几个任务」（末页按实际条数收口）。卡片头那句「前 N 个」用它。 */
  const shownTo = Math.min((feedPage + 1) * feedPageSize, recent.length);

  for (const { task, latest, count } of shown) {
    const row = el("div", { class: "feed-item" }, [
      el("span", { class: "tm", text: stampText(latest.at) }),
      // 状态色点：一条流里混着已完成和进行中的任务，光看标题分不出来
      el("i", { class: "dot" }),
      el("span", { class: "tx" }, [el("b", { text: task.title }), ` · ${latest.text}`]),
      ...(count > 1 ? [el("span", { class: "cn", text: `共 ${count} 条` })] : []),
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
      // 后缀这句给的是**窗口**，不是总数（2026-09-20 用户改的）：原来写「共 88 个任务」，
      // 88 是聚合后的任务总数 —— 会被读成「这一屏显示了 88 条」，跟每屏行数（20/50）
      // 不是一回事。现在写「前 50 个任务」：读者一眼知道这份清单是**最近的、截到这里**
      // （上限见 shared.ts 的 FEED_LIMIT）。空表时不带这句（「前 0 个」不是人话）
      el("span", {
        class: "d",
        text: recent.length === 0 ? "按最近活动倒序" : `按最近活动倒序 · 前 ${shownTo} 个任务`,
      }),
    ]),
    el("div", { class: "card-b" }, [
      list,
      // 和其余三张表同一个分页器（各自的上限由 total 决定：这张卡就是 FEED_LIMIT）
      pager({
        page: feedPage,
        pageCount,
        total: recent.length,
        size: feedPageSize,
        // 这张表按**任务**聚合，单位就得是「个任务」：按默认的「条」写，
        // 会和同一张卡里的「共 N 条」（那是某个任务的活动条数）串味
        unit: "个任务",
        // 也不报总数：只写「第 1–50 个任务」。带「共」字那句会被读成「这一屏有 88 条」
        showTotal: false,
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
  for (const level of URGENCY_LEVELS) {
    // 名字带上编号（`紧急(P0)`）：只写「紧急」，用户得自己猜它对应列表里哪个 Px
    const label = urgencyText(level);
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
    row.addEventListener("click", () => showTasksWithUrgency(level));
    list.append(row);
  }

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
        // 年份从天数里读（isoDay），不在页面里写死 2026 —— 跨年之后这一行会一直说 2026。
        // 分区名也写在这一行：rail 上虽然有（图标下面那行），但这里是「今天」的**一句话
        // 总结** —— 日期 · 星期 · 分区 · 条数 连起来读才成句，少一项就不成句。
        // 口径就是**当前分区**（切分区时这一页跟着 dataChanged 重画）
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
  // 切回这一页时立刻重画一次。下面那个定时器只在**本页可见**时才画，于是留了一个
  // 最长 60 秒的窗口：页面在 10:59 装载、11:00 切回来，问候语还停在「早上好」，
  // 「现在」标记也停在上一分钟（e2e 就是在这个窗口里抓到的）。图谱 / 任务页都是
  // 「切回前台重画一次」，这里跟上。
  subscribePages(render);

  // 「现在」标记要跟着钟走：这一页只在数据变化时重画，页面开着不动的话，标记会
  // 一直停在打开那一刻 —— 修掉「写死 09:30」之后，仍然要防它变成「写死打开时刻」。
  // 每分钟重画一次，且只在本页可见时做（别的页面上重画纯属白干）。
  window.setInterval(() => {
    if (currentPage() === "overview") render();
  }, 60_000);
}
