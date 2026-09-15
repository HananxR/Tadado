// ─────────────────────────────────────────────────────────────────────────────
// 任务页：时间轴表格。
//
// 左侧任务列吸附（横向滚动时留在原地），右侧是按日展开的格子。日期格线不是
// DOM 节点而是 repeating-linear-gradient —— 24 天 × 28 行会多出近 700 个
// 只用来画线的 div，而线宽和列宽本来就同源，交给 CSS 更准也更快。
//
// 列宽是 CSS 和 TS 各写一半的东西，所以抽成 COL_W 一个常量：pages.css 里
// .tt-track 的格线周期和这里的定位计算都引用它，改一处两边一起对。
//
// 工具行（搜索框 / 计数 / 排序）在 mount 里建一次就常驻，只有 chips 里的
// 数字和下面的表格随数据重建 —— 否则每次输入都要把搜索框重新造一遍，
// 光标和输入法组合状态都会断。
// ─────────────────────────────────────────────────────────────────────────────

import { TASKS, activeTasks } from "../data/mock";
import { dataChanged, onDataChange } from "../data/store";
import {
  TIMELINE_RANGES,
  onTimelineRangeChange,
  setTimelineRange,
  timelineRange,
} from "../data/timeline";
import type { Task } from "../data/types";
import { el } from "../shell/dom";
import { dropdown } from "../shell/menu";
import { subscribePages } from "../shell/router";
import { seg } from "../shell/seg";
import { toast } from "../shell/toast";
import { consumeTasksRequest, type StatusFilter } from "./focus";
import {
  DAY_MS,
  STATUS_LABEL,
  TODAY,
  dayNumber,
  monthDayText,
  statusVar,
  timelineWindow,
} from "./shared";
import { onTaskOpen, openTask } from "./taskDrawer";

/** 时间轴的日期窗口：起点天数 + 列数。 */
type TimelineWin = ReturnType<typeof timelineWindow>;

/** 日期列宽（px）。必须和 pages.css 里 .tt-track 的格线周期一致。 */
const COL_W = 22;

/** 左侧任务列宽（px）。同上，pages.css 里 .tt-label 也写着 248。 */
const LABEL_W = 248;

const SORTS = [
  { value: "due", label: "按截止日期" },
  { value: "urgency", label: "按优先级" },
  { value: "progress", label: "按进度" },
  { value: "created", label: "按创建时间" },
] as const;
type SortKey = (typeof SORTS)[number]["value"];

const FILTERS: { value: StatusFilter; label: string }[] = [
  { value: "all", label: "全部" },
  { value: "overdue", label: STATUS_LABEL.overdue },
  { value: "todo", label: STATUS_LABEL.todo },
  { value: "doing", label: STATUS_LABEL.doing },
  { value: "done", label: STATUS_LABEL.done },
];

const SEARCH_ICON =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><circle cx="11" cy="11" r="6.5"/><path d="M16 16l4.5 4.5"/></svg>';

const WEEKDAY_SHORT = ["日", "一", "二", "三", "四", "五", "六"];

// ─── 页面状态 ────────────────────────────────────────────────────────────────

let statusFilter: StatusFilter = "all";
let query = "";
let sortKey: SortKey = "due";
let selectedId: string | null = null;

// ─── 筛选与排序 ──────────────────────────────────────────────────────────────

function visibleTasks(): Task[] {
  const needle = query.trim().toLowerCase();

  const rows = activeTasks().filter((task) => {
    if (statusFilter !== "all" && task.status !== statusFilter) return false;
    if (!needle) return true;
    return [task.title, ...task.tags].join(" ").toLowerCase().includes(needle);
  });

  const endDay = (task: Task): number => dayNumber(task.end);

  const comparators: Record<SortKey, (a: Task, b: Task) => number> = {
    due: (a, b) => endDay(a) - endDay(b),
    urgency: (a, b) => a.urgency - b.urgency || endDay(a) - endDay(b),
    progress: (a, b) => b.progress - a.progress,
    created: (a, b) => dayNumber(b.created) - dayNumber(a.created),
  };

  return rows.sort(comparators[sortKey]);
}

// ─── 悬停提示 ────────────────────────────────────────────────────────────────

let tip: HTMLElement | null = null;

function tipNode(): HTMLElement {
  if (!tip) {
    tip = el("div", { class: "tt-tip" });
    document.body.append(tip);
  }
  return tip;
}

function moveTip(x: number, y: number): void {
  if (!tip) return;
  // 贴着右下会被窗口边缘切掉，靠近边界时翻到左侧 / 上方
  const rect = tip.getBoundingClientRect();
  const left = x + 16 + rect.width > window.innerWidth ? x - rect.width - 12 : x + 16;
  const top = y + 18 + rect.height > window.innerHeight ? y - rect.height - 12 : y + 18;
  tip.style.left = `${Math.max(8, left)}px`;
  tip.style.top = `${Math.max(8, top)}px`;
}

function showTip(task: Task, x: number, y: number): void {
  const node = tipNode();
  node.replaceChildren(
    el("div", { style: "font-weight:600;margin-bottom:5px", text: task.title }),
    el("div", {
      class: "mono dim",
      text: `${monthDayText(dayNumber(task.start))} → ${monthDayText(dayNumber(task.end))}`,
    }),
    el("div", {
      class: "mono dim",
      text: `${STATUS_LABEL[task.status]} · 进度 ${task.progress}%`,
    }),
    el("div", {
      class: "mono dim",
      text: `${task.tags.join(" ") || "无标签"}${task.repeat ? ` · ${task.repeat}` : ""}`,
    }),
    el("div", {
      class: "mono dim",
      style: "margin-top:5px",
      text: "双击或右键打开维护抽屉",
    }),
  );
  node.style.display = "block";
  moveTip(x, y);
}

function hideTip(): void {
  if (tip) tip.style.display = "none";
}

// ─── 行 ──────────────────────────────────────────────────────────────────────

function renderRow(task: Task, win: TimelineWin): HTMLElement {
  const dot = el("span", { class: "d" });
  dot.style.background = statusVar(task.status);

  const label = el("div", { class: "tt-label" }, [
    dot,
    el("div", { class: "lt" }, [
      el("div", { class: "lt1", text: task.title }),
      el("div", { class: "lt2" }, [
        ...task.tags.map((tag) => el("span", { class: "tag", text: tag })),
        el("span", { class: "dlt", text: task.due ? `⏰ ${task.due}` : "无截止" }),
      ]),
    ]),
  ]);

  // 起止跨出窗口时要夹到边界：一个跨月任务在「本周」里应该是一条顶住两边的
  // 长条，而不是溢出到表格外面的怪物。
  const first = Math.max(dayNumber(task.start), win.start);
  const last = Math.min(dayNumber(task.end), win.start + win.days - 1);
  const span = last - first + 1;

  const bar = el("div", { class: `tt-bar st-${task.status}`, "data-task": task.id });
  const barWidth = Math.max(span * COL_W - 4, 10);
  // 左右各留 2px：相邻任务挨在一起时还看得出是两条
  bar.style.left = `${(first - win.start) * COL_W + 2}px`;
  bar.style.width = `${barWidth}px`;

  const fill = el("i");
  fill.style.width = `${task.progress}%`;
  bar.append(fill);

  // 条内白字必须压在进度填充上才看得见 —— 没填满的那段是状态色的浅色版
  // （--todo-soft 是 #e2eaf5），白字落上去等于隐形。所以两个条件同时成立才写：
  // 条形够宽，且进度已经铺过文字区。其余情况由左侧任务列和悬浮提示来说。
  const fillWidth = (barWidth * task.progress) / 100;
  if (barWidth > 78 && fillWidth > 70) {
    const caption = el("b", { text: `${task.title} · ${task.progress}%` });
    caption.style.maxWidth = `${Math.max(fillWidth - 12, 40)}px`;
    bar.append(caption);
  }

  // 条形顶到最后一列时，收尾圆点会被表格右边界切掉一半
  if (last < win.start + win.days - 1) bar.append(el("span", { class: "end" }));

  bar.addEventListener("mouseenter", (event) => showTip(task, event.clientX, event.clientY));
  bar.addEventListener("mousemove", (event) => moveTip(event.clientX, event.clientY));
  bar.addEventListener("mouseleave", hideTip);

  const track = el("div", { class: "tt-track" }, [bar]);
  track.style.width = `${win.days * COL_W}px`;

  const row = el(
    "div",
    { class: `tt-row ${task.id === selectedId ? "selected" : ""}`, "data-task": task.id },
    [label, track],
  );

  row.addEventListener("click", () => {
    selectedId = task.id;
    paintSelection();
  });

  // 双击与右键都是「打开」。单击留给选中 —— 表格里误触打开抽屉，
  // 回来还得重新找那一行。
  row.addEventListener("dblclick", () => openTask(task.id));
  row.addEventListener("contextmenu", (event) => {
    event.preventDefault();
    openTask(task.id);
  });

  return row;
}

/** 只改选中类，不重建整棵树 —— 重建会把横向滚动位置一起丢掉。 */
function paintSelection(): void {
  for (const row of document.querySelectorAll<HTMLElement>(".tt-row")) {
    row.classList.toggle("selected", row.dataset.task === selectedId);
  }
  // 整行变色之外再给色条描一圈，长任务条一眼能从邻行里挑出来
  for (const bar of document.querySelectorAll<HTMLElement>(".tt-bar")) {
    bar.classList.toggle("sel", bar.dataset.task === selectedId);
  }
}

function scrollToSelected(): void {
  document
    .querySelector<HTMLElement>(`.tt-row[data-task="${selectedId}"]`)
    ?.scrollIntoView({ block: "nearest", inline: "nearest" });
}

// ─── 页面 ────────────────────────────────────────────────────────────────────

export function mount(host: HTMLElement): void {
  const search = el("input", { placeholder: "搜索任务名或标签…" });
  search.value = query;
  search.addEventListener("input", () => {
    query = search.value;
    render();
  });

  const chips = el("div", { class: "chips" });
  const count = el("span", { class: "dim mono" });

  const sortPick = dropdown<SortKey>({
    items: SORTS.map((sort) => ({ value: sort.value, label: sort.label })),
    value: sortKey,
    onPick: (value) => {
      sortKey = value;
      render();
    },
  });

  // 档位由 data/timeline 持有，设置面板里也能改同一个值 ——
  // 所以这里不自建状态，on/off 交给 setValue（订阅见 mount 末尾）
  const rangePick = seg(
    TIMELINE_RANGES.map((item) => ({ value: item.value, label: item.label })),
    timelineRange(),
    (value) => setTimelineRange(value),
  );
  rangePick.root.style.flex = "none";
  rangePick.root.style.width = "auto";

  const table = el("div");

  // 工具行和表格包在同一个容器里：直接挂两个子节点给 .page-body，
  // 它的 gap 会和 .tools 自己的 margin-bottom 叠加成 28px。
  host.append(
    el("div", {}, [
      el("div", { class: "tools" }, [
        el("span", { class: "searchbox" }, [
          el("span", { class: "ic", html: SEARCH_ICON }),
          search,
        ]),
        chips,
        el("span", { class: "grow" }),
        count,
        sortPick.root,
        rangePick.root,
      ]),
      table,
    ]),
  );

  const render = (): void => {
    // 输入框里的字可能被别处改过（新建任务会清空 query），搜索框自己不知道
    if (search.value !== query) search.value = query;

    const win = timelineWindow(timelineRange());
    const winEnd = win.start + win.days - 1;

    // 窗口外的任务不画。色条是从「起止」算出来的，一条排在窗口右边的任务
    // 只会得到一根宽度为负的条 —— 与其夹成一根假的短条，不如不出现在这一档里。
    const rows = visibleTasks().filter(
      (task) => dayNumber(task.end) >= win.start && dayNumber(task.start) <= winEnd,
    );

    // ── chips（数量随数据变）──
    chips.replaceChildren();
    for (const filter of FILTERS) {
      const total =
        filter.value === "all"
          ? activeTasks().length
          : activeTasks().filter((task) => task.status === filter.value).length;
      const chip = el("button", {
        class: `chip ${statusFilter === filter.value ? "on" : ""}`,
        type: "button",
      }, [filter.label, el("span", { class: "cn", text: String(total) })]);
      chip.addEventListener("click", () => {
        statusFilter = filter.value;
        render();
      });
      chips.append(chip);
    }

    count.textContent = `${rows.length} / ${activeTasks().length}`;

    const dayCells: HTMLElement[] = [];
    for (let offset = 0; offset < win.days; offset += 1) {
      const day = win.start + offset;
      const date = new Date(day * DAY_MS);
      const weekday = date.getUTCDay();
      const cell = el(
        "div",
        {
          class: `tt-date ${weekday === 0 || weekday === 6 ? "wknd" : ""} ${
            day === TODAY ? "today" : ""
          }`,
        },
        [
          el("span", { class: "dn", text: String(date.getUTCDate()) }),
          el("span", { class: "dw", text: WEEKDAY_SHORT[weekday] }),
        ],
      );
      cell.style.width = `${COL_W}px`;
      dayCells.push(cell);
    }

    const body = rows.map((task) => renderRow(task, win));

    const grid = el("div", { class: "tt-grid" });
    grid.style.width = `${LABEL_W + win.days * COL_W}px`;
    grid.append(
      el("div", { class: "tt-hrow" }, [
        el("div", { class: "tt-label" }, [
          el("span", { class: "dim mono", text: "任务" }),
          el("span", { class: "grow" }),
          el("span", {
            class: "dim mono",
            text: `${monthDayText(win.start)} – ${monthDayText(winEnd)}`,
          }),
        ]),
        ...dayCells,
      ]),
      ...(body.length > 0
        ? body
        : [el("div", { class: "empty", text: "这一档里没有任务 —— 换个粒度、筛选或清空搜索" })]),
    );

    if (TODAY >= win.start && TODAY <= winEnd) {
      const todayLine = el("div", { class: "tt-today" });
      todayLine.style.left = `${LABEL_W + (TODAY - win.start) * COL_W + COL_W / 2}px`;
      grid.append(todayLine);
    }

    table.replaceChildren(el("div", { class: "tt-wrap" }, [el("div", { class: "tt-scroll" }, [grid])]));
  };

  // 设置面板里也能改粒度，改完工具行那排按钮和表格都要跟上
  onTimelineRangeChange(() => {
    rangePick.setValue(timelineRange());
    render();
  });

  render();
  onDataChange(render);

  // 抽屉打开时同步选中态；关闭时保留上一次的选中（和表格里点一下的行为一致）
  onTaskOpen((task) => {
    if (!task) return;
    selectedId = task.id;
    paintSelection();
    scrollToSelected();
  });

  // 别的页面喊「定位到某个任务 / 按某状态筛选」时，在本页自己的地盘上复位
  subscribePages((id) => {
    if (id !== "tasks") return;

    const request = consumeTasksRequest();
    if (request.filter === null && request.taskId === null) return;

    if (request.filter !== null) statusFilter = request.filter;
    if (request.taskId !== null) {
      selectedId = request.taskId;
      // 搜索词是上一次留下的，不清掉目标任务可能根本不在结果里
      query = "";
      search.value = "";
    }

    render();
    if (request.taskId !== null) scrollToSelected();
  });
}

/** 页头主按钮：新建一条空任务并直接打开抽屉。 */
export function onAction(): void {
  const id = `new-${Date.now()}`;
  const today: [number, number] = [9, 12];

  TASKS.unshift({
    id,
    title: "未命名任务",
    status: "todo",
    tags: [],
    due: null,
    at: null,
    start: today,
    end: today,
    progress: 0,
    urgency: 2,
    repeat: "",
    created: today,
    archived: false,
    related: [],
    activities: [{ at: "刚刚", text: "创建任务", kind: "create" }],
  });

  // 新任务在「逾期」或某个搜索词下面根本不会出现，先复位再定位
  statusFilter = "all";
  query = "";
  selectedId = id;

  dataChanged();
  openTask(id);
  toast("已新建任务 · 在抽屉里改标题和标签");
}
