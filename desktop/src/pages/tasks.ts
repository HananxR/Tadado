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

import { parseTasks } from "../data/markdown";
import { TASKS, activeTasks } from "../data/mock";
import { activePartitionId } from "../data/partitions";
import { dataChanged, onDataChange } from "../data/store";
import {
  TIMELINE_RANGES,
  onTimelineRangeChange,
  setTimelineRange,
  timelineRange,
  type TimelineRange,
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
  removeTask,
  statusVar,
  timelineWindow,
  todayMonthDay,
} from "./shared";
import { onTaskOpen, openTask } from "./taskDrawer";

/** 时间轴的日期窗口：起点天数 + 列数。 */
type TimelineWin = ReturnType<typeof timelineWindow>;

/** 左侧任务列宽（px）。同上，pages.css 里 .tt-label 也写着 248。 */
const LABEL_W = 248;

/** 列宽自适应区间（px）：数据少时不至于胖成一列上百像素，多时不至于挤成一根线。 */
const COL_MIN = 15;
const COL_MAX = 34;

/** 竖向滚动条的宽度余量。不留的话铺满之后右边会溢出第二条滚动条。 */
const SCROLL_GUTTER = 16;

/** 窗口左右各留的白边天数。0 会让首尾两条色条贴着表格边界。 */
const WIN_PAD = 2;

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

const PLUS_ICON =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>';

const WEEKDAY_SHORT = ["日", "一", "二", "三", "四", "五", "六"];

// ─── 日期窗口与列宽 ──────────────────────────────────────────────────────────

/**
 * 真正拿来画表的窗口 = 粒度给的最小窗口 ∪ 数据自身的跨度 ∪ 今天。
 *
 * 只按粒度算（以前就是这样）有两个后果：跨出窗口的任务整条消失 —— 数据里写着
 * 09-25 的任务在「本周」这一档里根本看不见；而窗口里没有任务的那一段，会变成
 * 一大片空白列铺到表格右端。所以粒度现在只当作「最少要看多宽」的下限，
 * 列数跟着数据的起止走。
 */
function windowFor(range: TimelineRange, tasks: Task[]): TimelineWin {
  const base = timelineWindow(range);
  let start = base.start;
  let end = base.start + base.days - 1;

  if (tasks.length > 0) {
    start = Math.min(start, ...tasks.map((task) => dayNumber(task.start)));
    end = Math.max(end, ...tasks.map((task) => dayNumber(task.end)));
  }

  // 今天必须在窗口里：它是唯一一个「没有任务也要能对着看」的日期
  start = Math.min(start, TODAY) - WIN_PAD;
  end = Math.max(end, TODAY) + WIN_PAD;
  return { start, days: end - start + 1 };
}

/** 列宽 = 可用宽度按天数平分后再夹到区间里 —— 表格因此永远铺满右侧。 */
function columnWidth(days: number, available: number): number {
  const room = Math.max(available - SCROLL_GUTTER - LABEL_W, COL_MIN * days);
  return Math.min(COL_MAX, Math.max(COL_MIN, room / days));
}

// ─── 右键菜单 ────────────────────────────────────────────────────────────────

let ctxMenu: HTMLElement | null = null;

function closeCtxMenu(): void {
  ctxMenu?.remove();
  ctxMenu = null;
}

/**
 * 任务行的右键菜单。以前右键和双击等价（都只是打开抽屉），于是「右键功能」形同
 * 不存在 —— 右键该给的是「不用挪视线就能处置」的那一列动作，而不是把打开再走一遍。
 */
function openCtxMenu(task: Task, x: number, y: number): void {
  closeCtxMenu();

  const done = task.status === "done";
  const item = (label: string, onClick: () => void, danger = false): HTMLElement => {
    const row = el("div", { class: `menu-item ${danger ? "danger" : ""}`, text: label });
    row.addEventListener("click", () => {
      closeCtxMenu();
      onClick();
    });
    return row;
  };

  const menu = el("div", { class: "ctx-menu" }, [
    item("打开维护抽屉", () => openTask(task.id)),
    item(done ? "标记为待办" : "标记完成", () => {
      task.status = done ? "todo" : "done";
      if (!done) task.progress = 100;
      dataChanged();
      toast(`「${task.title}」${done ? "已回到待办" : "已标记完成"}`);
    }),
    item("删除任务", () => void removeTask(task), true),
  ]);

  document.body.append(menu);

  // 贴边时收回来：fixed 定位越界就被窗口边缘吃掉
  const rect = menu.getBoundingClientRect();
  menu.style.left = `${Math.max(8, Math.min(x, window.innerWidth - rect.width - 8))}px`;
  menu.style.top = `${Math.max(8, Math.min(y, window.innerHeight - rect.height - 8))}px`;
  ctxMenu = menu;
}

// pointerdown 早于 click：点在菜单里不算关闭，点别处才关
document.addEventListener("pointerdown", (event) => {
  if (ctxMenu && !ctxMenu.contains(event.target as Node)) closeCtxMenu();
});

window.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeCtxMenu();
});

// ─── 批量新建 ────────────────────────────────────────────────────────────────

/**
 * 一次粘贴多行、每行一条任务，方言和 md 导入完全一致（data/markdown.ts）。
 *
 * 两个刻意的设计：
 *   1. 预览实时更新 —— 解析出几条要在点「创建」**之前**就看见，而不是建完才发现
 *      少了一半；
 *   2. 提交用 Ctrl+Enter —— 多行文本里单独的 Enter 是换行，抢走它会让
 *      「想换行结果提交了」。
 */
function openBatchCreate(): void {
  const area = el("textarea", {
    class: "md",
    spellcheck: "false",
    placeholder: "- [ ] 任务名 #标签 ⏰09-20 14:30 :: 30%\n- [x] 已完成的活 #工作",
  });

  const preview = el("div", { class: "modal-detail", text: "将创建 0 条" });
  const cancelBtn = el("button", { class: "btn", type: "button", text: "取消" });
  const createBtn = el("button", { class: "btn primary", type: "button", text: "创建" });

  const card = el("div", { class: "modal-card" }, [
    el("div", { class: "modal-title", text: "批量新建" }),
    el("div", {
      class: "modal-detail",
      text: "一行一条任务，可带 #标签 ⏰截止 :: 进度% +1w；空行和认不出的行会跳过。",
    }),
    area,
    preview,
    el("div", { class: "modal-actions" }, [cancelBtn, createBtn]),
  ]);
  const mask = el("div", { class: "mask" }, [card]);

  const drafts = (): Omit<Task, "partition">[] => parseTasks(area.value);

  const sync = (): void => {
    const total = drafts().length;
    preview.textContent = total > 0 ? `将创建 ${total} 条` : "还没解析出任务行";
    createBtn.disabled = total === 0;
  };

  function close(): void {
    mask.classList.remove("show");
    window.removeEventListener("keydown", onKey, true);
    window.setTimeout(() => mask.remove(), 180);
  }

  function onKey(event: KeyboardEvent): void {
    if (event.key !== "Escape") return;
    event.stopPropagation();
    close();
  }

  area.addEventListener("input", sync);
  area.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      createBtn.click();
    }
  });

  cancelBtn.addEventListener("click", close);
  mask.addEventListener("click", (event) => {
    if (event.target === mask) close();
  });

  createBtn.addEventListener("click", () => {
    const items = drafts().map((draft) => ({
      ...draft,
      id: `batch-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      partition: activePartitionId(),
    }));
    if (items.length === 0) return;

    TASKS.unshift(...items);
    // 新建的可能在当前筛选 / 搜索词之外，先复位，否则建完一条都看不见
    statusFilter = "all";
    query = "";
    dataChanged();
    close();
    toast(`已新建 ${items.length} 条任务`);
  });

  document.body.append(mask);
  window.addEventListener("keydown", onKey, true);
  requestAnimationFrame(() => {
    mask.classList.add("show");
    area.focus();
  });
  sync();
}

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

function renderRow(task: Task, win: TimelineWin, colW: number): HTMLElement {
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
  const barWidth = Math.max(span * colW - 4, 10);
  // 左右各留 2px：相邻任务挨在一起时还看得出是两条
  bar.style.left = `${(first - win.start) * colW + 2}px`;
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
  track.style.width = `${win.days * colW}px`;

  const row = el(
    "div",
    { class: `tt-row ${task.id === selectedId ? "selected" : ""}`, "data-task": task.id },
    [label, track],
  );

  row.addEventListener("click", () => {
    selectedId = task.id;
    paintSelection();
  });

  // 双击才是「打开」，单击留给选中 —— 表格里误触打开抽屉，回来还得重新找那一行。
  row.addEventListener("dblclick", () => openTask(task.id));
  // 右键给处置菜单，并把当前选中带过去：菜单里删除的那一项就该作用在
  // 右键点的这一行上，而不是上一次点选的那行。
  row.addEventListener("contextmenu", (event) => {
    event.preventDefault();
    selectedId = task.id;
    paintSelection();
    openCtxMenu(task, event.clientX, event.clientY);
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

  // 快速新建。它以前住在总览页 —— 那里没有任何「按天 × 任务」的追踪手段，
  // 任务建完就沉到列表底部看不见了；这里是时间轴，建完立刻出现在今天那一列上，
  // 能接着往下追。
  const quick = el("input", {
    class: "qc-input",
    placeholder: "快速新建：任务名 #标签（回车创建）",
  });
  const runQuick = (): void => {
    const raw = quick.value.trim();
    if (!raw) return;

    const tags = [...raw.matchAll(/#\S+/g)].map((match) => match[0]);
    const title = raw.replace(/#\S+/g, "").trim();
    // 不允许无名任务：只剩标签的任务在时间轴上没有名字可认，一旦得到
    // 「未命名任务」这种东西，回头只能靠抽屉里的 id 去猜它是谁。宁可在这一步拦下。
    if (!title) {
      toast("先写个任务名 —— 只有标签的任务没法在时间轴上认出来");
      return;
    }

    const today = todayMonthDay();
    const id = `quick-${Date.now()}`;
    TASKS.unshift({
      id,
      title,
      status: "todo",
      tags: tags.length > 0 ? tags : ["#工作"],
      due: null,
      at: null,
      start: today,
      end: today,
      progress: 0,
      urgency: 3,
      repeat: "",
      created: today,
      archived: false,
      // 建在当前分区下 —— 切了分区再建，它出现在别的分区里会像凭空消失
      partition: activePartitionId(),
      related: [],
      activities: [{ at: "刚刚", text: "创建任务", kind: "create" }],
    });

    quick.value = "";
    // 新任务可能在当前筛选/搜索词之外，先复位再定位，否则建完就消失
    statusFilter = "all";
    query = "";
    selectedId = id;

    dataChanged();
    toast(`已新建「${title}」· 在今天的列上`);
  };
  quick.addEventListener("keydown", (event) => {
    if (event.key === "Enter") runQuick();
  });

  // 批量新建：一次粘贴多行，走的是同一套 Markdown 方言（data/markdown.ts）。
  // 原版有「多任务创建对话框」，桌面端只有单行快速新建 —— 一次录十条的时候
  // 单行框要来回十趟。
  const batchBtn = el("button", { class: "btn sm", type: "button", text: "批量" });
  batchBtn.addEventListener("click", () => openBatchCreate());

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
          el("span", { class: "ic", html: PLUS_ICON }),
          quick,
        ]),
        el("span", { class: "searchbox" }, [
          el("span", { class: "ic", html: SEARCH_ICON }),
          search,
        ]),
        batchBtn,
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

    // 先取数据再定窗口：窗口本身要并上数据的跨度，拿 rows 去算就绕成环了
    const tasks = visibleTasks();
    const win = windowFor(timelineRange(), tasks);
    const winEnd = win.start + win.days - 1;

    // 正常情况下这个过滤拦不掉任何东西（窗口本来就是按它们算出来的），留着是给
    // 「窗口被外力改坏」兜底 —— 色条算成负宽度会把相邻几行的节奏整个打乱。
    const rows = tasks.filter(
      (task) => dayNumber(task.end) >= win.start && dayNumber(task.start) <= winEnd,
    );

    // 页面隐藏时 clientWidth 量不到（display:none 下是 0），给个够用的兜底值，
    // 切回前台会再 render 一次重算（见 mount 末尾的 subscribePages）
    const colW = columnWidth(win.days, table.clientWidth > 0 ? table.clientWidth : 1080);

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
      dayCells.push(cell);
    }

    const body = rows.map((task) => renderRow(task, win, colW));

    const grid = el("div", { class: "tt-grid" });
    grid.style.width = `${LABEL_W + win.days * colW}px`;
    // 列宽交给 CSS 变量：表头日期格的宽度和 .tt-track 的格线周期都从这里取，
    // 于是「让列宽铺满」这件事只有 tasks.ts 一个地方说了算
    grid.style.setProperty("--tt-col", `${colW}px`);
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
      todayLine.style.left = `${LABEL_W + (TODAY - win.start) * colW + colW / 2}px`;
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

  // 窗口宽窄变了，列数不变但列宽要重算 —— 否则右边重新空出来
  let resizeTimer: number | undefined;
  window.addEventListener("resize", () => {
    window.clearTimeout(resizeTimer);
    resizeTimer = window.setTimeout(render, 140);
  });

  // 别的页面喊「定位到某个任务 / 按某状态筛选」时，在本页自己的地盘上复位
  subscribePages((id) => {
    if (id !== "tasks") return;

    const request = consumeTasksRequest();
    if (request.filter === null && request.taskId === null) {
      // 页面隐藏时量不到可用宽度（clientWidth 是 0），回到前台重新量一次，
      // 否则列宽会停在挂载时的兜底值上，右侧又空出一条
      render();
      return;
    }

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


