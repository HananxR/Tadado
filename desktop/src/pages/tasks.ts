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
  setTimelineRange,
  timelineRange,
  timelineWindow,
} from "../data/timeline";
import type { Task, Urgency } from "../data/types";
import { el } from "../shell/dom";
import { dropDraft, loadDraft, saveDraft } from "../shell/draft";
import { dropdown } from "../shell/menu";
import { subscribePages } from "../shell/router";
import { seg } from "../shell/seg";
import { toast } from "../shell/toast";
import {
  consumeTasksRequest,
  type StatusFilter,
  type UrgencyFilter,
} from "./focus";
import {
  DAY_MS,
  STATUS_LABEL,
  TASK_PAGE_SIZE,
  TODAY,
  URGENCY_LABEL,
  dayNumber,
  monthDayText,
  nowStamp,
  removeTask,
  setTaskStatus,
  statusVar,
  urgencyBadge,
} from "./shared";
import { pager } from "./pager";
import { closeTask, isTaskOpen, onTaskOpen, openTask } from "./taskDrawer";
import { draftTask, taskForm } from "./taskForm";

/** 时间轴的日期窗口：起点天数 + 列数。 */
type TimelineWin = ReturnType<typeof timelineWindow>;

/** 左侧任务列宽（px）。同上，pages.css 里 .tt-label 也写着 248。 */
const LABEL_W = 248;

/** 列宽自适应区间（px）：数据少时不至于胖成一列上百像素，多时不至于挤成一根线。 */
const COL_MIN = 15;
const COL_MAX = 34;

/** 竖向滚动条的宽度余量。不留的话铺满之后右边会溢出第二条滚动条。 */
const SCROLL_GUTTER = 16;

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

// ─── 日期窗口与列宽 ──────────────────────────────────────────────────────────

/** 列宽 = 可用宽度按天数平分后再夹到区间里 —— 表格因此永远铺满右侧。 */
function columnWidth(days: number, available: number): number {
  const room = Math.max(available - SCROLL_GUTTER - LABEL_W, COL_MIN * days);
  return Math.min(COL_MAX, Math.max(COL_MIN, room / days));
}

/**
 * 把窗口撑到**刚好装下这批任务**。
 *
 * 档位说的是「我想看多长一段时间」，不是「允许悄悄漏掉几条」。以前反过来 ——
 * 先按档位算出窗口，再拿窗口去过滤任务：总览写着「逾期 4」，点进来只看见 3 条，
 * 第 4 条的起止落在窗口外。它没丢，只是没被画出来，而用户只能认为那个数字是假的。
 *
 * 所以顺序调过来：先有筛选结果，再让窗口去迁就它。窗口因此可能比档位宽 ——
 * 表头一直写着真实区间，不会让人误以为自己还在看「本周」。
 */
function fitWindow(base: TimelineWin, tasks: Task[]): TimelineWin {
  if (tasks.length === 0) return base;

  let from = base.start;
  let to = base.start + base.days - 1;
  for (const task of tasks) {
    from = Math.min(from, dayNumber(task.start));
    to = Math.max(to, dayNumber(task.end));
  }
  return { start: from, days: to - from + 1 };
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
      setTaskStatus(task, done ? "todo" : "done");
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
  // 粘了十行再手滑点到遮罩就白干了 —— 对话框关掉不等于放弃，字还在这儿
  const keptNote = el("span", { class: "draft-t", text: "上次未提交的内容已保留" });
  const restored = el("div", { class: "draft-bar", style: "display:none" });
  const keptDrop = el("button", { class: "btn sm", type: "button", text: "丢弃草稿" });
  restored.append(keptNote, el("span", { class: "grow" }), keptDrop);
  const cancelBtn = el("button", { class: "btn", type: "button", text: "取消" });
  const createBtn = el("button", { class: "btn primary", type: "button", text: "创建" });

  const card = el("div", { class: "modal-card" }, [
    el("div", { class: "modal-title", text: "批量新建" }),
    el("div", {
      class: "modal-detail",
      // 原来这里还写着 `+1w`（循环）—— 那个字段早已删除（见 data/markdown.ts
      // 顶部），提示里留着它就是让人照着一个不存在的语法写
      text:
        "一行一条任务，可带 #标签 ⏰截止 :: 进度%；任务下面缩进的行会记进它的活动时间线。" +
        "空行与无法识别的行会跳过。",
    }),
    area,
    restored,
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

  area.addEventListener("input", () => {
    sync();
    saveDraft("batch", area.value);
  });

  keptDrop.addEventListener("click", () => {
    area.value = "";
    restored.style.display = "none";
    void dropDraft("batch");
    sync();
    area.focus();
  });

  // 上次写到一半的批量内容：对话框常被临时拖动窗口误点到遮罩关掉
  void loadDraft("batch").then((text) => {
    if (!text.trim()) return;
    area.value = text;
    keptNote.textContent = `上次没提交的内容还在（${drafts().length} 行）`;
    restored.style.display = "flex";
    sync();
  });
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
    // 已经变成任务了，草稿使命结束
    void dropDraft("batch");
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
/** 优先级筛选。总览的「优先级分布」点某一档时由 focus 请求带过来。 */
let urgencyFilter: UrgencyFilter = "all";
/** 时间轴表格翻到第几页（0 起）。换筛选 / 排序 / 档位都回到第一页。 */
let page = 0;
/** 当前每页几条。分页器上那个下拉改它。 */
let taskPageSize = TASK_PAGE_SIZE;
let query = "";
let sortKey: SortKey = "due";
let selectedId: string | null = null;

// ─── 筛选与排序 ──────────────────────────────────────────────────────────────

/**
 * 除**状态**以外的筛选（优先级 + 搜索）。
 *
 * 单独抽出来是为了 chips 上的数字：那个数必须等于「点这个 chip 之后表里会有几行」，
 * 所以它要带上优先级和搜索词，唯独不带状态本身 —— 否则点「逾期」前后的数字会互相打架。
 */
function poolTasks(): Task[] {
  const needle = query.trim().toLowerCase();

  return activeTasks().filter((task) => {
    if (urgencyFilter !== "all" && task.urgency !== urgencyFilter) return false;
    if (!needle) return true;
    return [task.title, ...task.tags].join(" ").toLowerCase().includes(needle);
  });
}

function visibleTasks(): Task[] {
  const rows = poolTasks().filter(
    (task) => statusFilter === "all" || task.status === statusFilter,
  );

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
      text: `${task.tags.join(" ") || "无标签"} · ${URGENCY_LABEL[task.urgency]}`,
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
      // 标题与截止同行：截止靠右。标签以前和它挤在同一行，三个标签就会被
      // overflow:hidden 静默裁掉 —— 数据在，只是看不见
      el("div", { class: "lt1" }, [
        el("span", { class: "t", text: task.title }),
        el("span", { class: "dlt", text: task.due ? `⏰ ${task.due}` : "无截止" }),
      ]),
      el(
        "div",
        { class: "lt2" },
        task.tags.map((tag) => el("span", { class: "tag", text: tag })),
      ),
    ]),
    // 优先级徽标钉在任务列右端。左边那个圆点是**状态**色，这里才是优先级 ——
    // 两件事分开摆，不用去猜颜色
    urgencyBadge(task.urgency),
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
  // 同一条上再双击一次就收起：双击是唯一的打开手势，没有反手势就只能去够右上角。
  row.addEventListener("dblclick", () => {
    if (isTaskOpen(task.id)) closeTask();
    else openTask(task.id);
  });
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

// ─── 新建任务 ────────────────────────────────────────────────────────────────

/**
 * 新建任务对话框。
 *
 * 为什么不沿用原来那个「快速新建」输入框：它只能填名称和标签，建出来的任务状态
 * 永远是待办、优先级永远是普通、没有起止时间，建完还得再开抽屉补一遍 —— 用户的
 * 原话就是「均需要二次编辑进行才能实现」。这里打开的是一张完整表单
 * （pages/taskForm.ts），和抽屉里编辑同一条任务用的是同一套字段与控件。
 *
 * 提交时才入库：填一半就关掉，不该在列表里留下一条没名字的任务。
 */
function openCreateTask(): void {
  const draft = draftTask();
  // 建在当前分区下 —— 切了分区再建，它出现在别的分区里会像凭空消失
  draft.partition = activePartitionId();

  const form = taskForm({
    task: draft,
    // 对话框里每次改动都不落库：草稿还没进 TASKS，提交时才写
    onEdit: () => {},
  });

  const cancelBtn = el("button", { class: "btn", type: "button", text: "取消" });
  const createBtn = el("button", { class: "btn primary", type: "button", text: "创建" });

  const card = el("div", { class: "modal-card wide" }, [
    el("div", { class: "modal-title", text: "新建任务" }),
    el("div", {
      class: "modal-detail",
      text: "创建后可在维护抽屉中继续修改。",
    }),
    form.root,
    el("div", { class: "modal-actions" }, [cancelBtn, createBtn]),
  ]);
  const mask = el("div", { class: "mask" }, [card]);

  function close(): void {
    mask.classList.remove("show");
    window.removeEventListener("keydown", onKey, true);
    window.setTimeout(() => mask.remove(), 180);
  }

  function onKey(event: KeyboardEvent): void {
    if (event.key !== "Escape") return;
    // 抽屉也用 Esc，别一次关两层
    event.stopPropagation();
    close();
  }

  cancelBtn.addEventListener("click", close);
  mask.addEventListener("click", (event) => {
    if (event.target === mask) close();
  });

  createBtn.addEventListener("click", () => {
    const title = draft.title.trim();

    // 必填三项：任务名 / 标签 / 结束时间。缺任何一个都不落库 —— 尤其是标签：
    // 以前这里有个兜底，没写标签就偷偷塞一个 `#工作`，用户看到的是「我明明写了
    // 好几个标签，怎么变成一个了」。宁可在这一步拦住并说清缺什么。
    const missing: string[] = [];
    if (!title) missing.push("任务名");
    if (draft.tags.length === 0) missing.push("标签");
    if (!draft.due) missing.push("结束时间");

    if (missing.length > 0) {
      toast(`还差：${missing.join(" / ")}`);
      const target = !title
        ? form.root.querySelector<HTMLInputElement>(".dr-title")
        : draft.tags.length === 0
          ? form.root.querySelector<HTMLInputElement>(".dr-tags")
          : form.root.querySelector<HTMLInputElement>(".dt:has(.dt-time) .dt-date");
      target?.focus();
      return;
    }

    const id = `task-${Date.now()}`;
    TASKS.unshift({
      ...draft,
      id,
      title,
      activities: [{ at: nowStamp(), text: "创建任务", kind: "create" }],
    });

    // 新任务可能落在当前筛选 / 搜索词 / 档位之外，先复位再定位，否则建完就消失
    statusFilter = "all";
    query = "";
    selectedId = id;
    dataChanged();
    close();
    toast(`已新建「${title}」`);
  });

  document.body.append(mask);
  requestAnimationFrame(() => {
    mask.classList.add("show");
    form.root.querySelector<HTMLInputElement>(".dr-title")?.focus();
  });
  window.addEventListener("keydown", onKey, true);
}

/** 页头主按钮（registry 里配的 action）—— 任务页唯一的「新建」入口。 */
export const onAction = (): void => openCreateTask();

// ─── 页面 ────────────────────────────────────────────────────────────────────

export function mount(host: HTMLElement): void {
  const search = el("input", { placeholder: "搜索任务名或标签…" });
  search.value = query;
  search.addEventListener("input", () => {
    query = search.value;
    page = 0;
    render();
  });

  // 这里原来是「快速新建」——一个只能填名称和标签的输入框，建出来的任务状态
  // 永远是「待办」、优先级永远是「普通」、没有开始与结束时间，建完必须再开一次
  // 抽屉补齐。用户的原话是「像任务状态、优先级都无法直接维护，均需要二次编辑」，
  // 所以它整个撤掉了：新建走页头的「＋ 新建任务」，打开的是和编辑同一套表单。

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
      page = 0;
      render();
    },
  });

  // 档位放在 data/timeline，总览的焦点时间轴共用同一组档位定义。
  // 这里是唯一能改它的地方（设置里那一份已撤），所以直接改完自己重画，
  // 不用再经一层事件广播把改动绕回来
  const rangePick = seg(
    TIMELINE_RANGES.map((item) => ({ value: item.value, label: item.label })),
    timelineRange(),
    (value) => {
      setTimelineRange(value);
      page = 0;
      render();
    },
  );
  rangePick.root.style.flex = "none";
  rangePick.root.style.width = "auto";

  /**
   * 优先级筛选。总览的「优先级分布」点某一档时由 focus 请求带过来，
   * 这里也能自己换 —— 入口只有这一个，和状态那排 chips 并列。
   */
  type UrgencyKey = "all" | "0" | "1" | "2" | "3";
  const urgencyPick = dropdown<UrgencyKey>({
    items: [
      { value: "all", label: "全部优先级" },
      ...URGENCY_LABEL.map((label, level) => ({
        value: String(level) as UrgencyKey,
        label: `P${level} ${label}`,
      })),
    ],
    value: "all",
    onPick: (value) => {
      urgencyFilter = value === "all" ? "all" : (Number(value) as Urgency);
      page = 0;
      render();
    },
  });

  // .tt-box：工具行之下的那一块（表格 + 分页器）。它吃掉页面剩余高度，
  // 表格再吃掉它的（见 pages.css 的一屏到底一节）—— 换掉原来那个
  // max-height: calc(100vh - 268px) 的写死估算
  const table = el("div", { class: "tt-box" });

  // 工具行和表格包在同一个容器里：直接挂两个子节点给 .page-body，
  // 它的 gap 会和 .tools 自己的 margin-bottom 叠加成 28px。
  host.append(
    el("div", { class: "tt-page" }, [
      el("div", { class: "tools" }, [
        el("span", { class: "searchbox" }, [
          el("span", { class: "ic", html: SEARCH_ICON }),
          search,
        ]),
        batchBtn,
        chips,
        urgencyPick.root,
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

    // 顺序：先筛，再让窗口去迁就筛出来的这批（见 fitWindow）。
    // 反过来「先定窗口、再拿窗口砍任务」的结果就是总览写 4、这里只画 3。
    const matched = visibleTasks();
    const pageCount = Math.max(1, Math.ceil(matched.length / taskPageSize));
    if (page >= pageCount) page = pageCount - 1;

    // 翻到**定位的那条所在的页**：抽屉开了、列表里却没有它，看着就像跳转坏了
    if (selectedId !== null) {
      const at = matched.findIndex((task) => task.id === selectedId);
      if (at >= 0) page = Math.floor(at / taskPageSize);
    }

    const rows = matched.slice(page * taskPageSize, (page + 1) * taskPageSize);
    const win = fitWindow(timelineWindow(timelineRange()), rows);
    const winEnd = win.start + win.days - 1;

    // 页面隐藏时 clientWidth 量不到（display:none 下是 0），给个够用的兜底值，
    // 切回前台会再 render 一次重算（见 mount 末尾的 subscribePages）
    const colW = columnWidth(win.days, table.clientWidth > 0 ? table.clientWidth : 1080);

    // ── chips（数量随数据变）──
    // 数字按 poolTasks 算（含优先级 / 搜索，不含状态），于是「chip 上写几
    // 条」＝「点开后表里几行」。以前按 activeTasks 全量算，点进去对不上。
    const pool = poolTasks();
    chips.replaceChildren();
    for (const filter of FILTERS) {
      const total =
        filter.value === "all"
          ? pool.length
          : pool.filter((task) => task.status === filter.value).length;
      const chip = el("button", {
        class: `chip ${statusFilter === filter.value ? "on" : ""}`,
        type: "button",
      }, [filter.label, el("span", { class: "cn", text: String(total) })]);
      chip.addEventListener("click", () => {
        statusFilter = filter.value;
        page = 0;
        render();
      });
      chips.append(chip);
    }

    // 三个数都摆出来：筛出几条（当前筛选的结果）/ 一共几条（当前分区未归档）。
    // 少写一个，用户就分不清是「被筛掉了」还是「在别的页上」
    count.textContent = `筛出 ${matched.length} · 共 ${activeTasks().length}`;

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
        : [
            el("div", {
              class: "empty",
              text: `${monthDayText(win.start)} – ${monthDayText(winEnd)} 区间内没有任务，可切换档位、调整筛选或清空搜索`,
            }),
          ]),
    );

    if (TODAY >= win.start && TODAY <= winEnd) {
      const todayLine = el("div", { class: "tt-today" });
      todayLine.style.left = `${LABEL_W + (TODAY - win.start) * colW + colW / 2}px`;
      grid.append(todayLine);
    }

    table.replaceChildren(
      el("div", { class: "tt-wrap" }, [el("div", { class: "tt-scroll" }, [grid])]),
      // 窗口按**当前页**的行去撑（fitWindow），所以翻页时表头的区间会跟着变 ——
      // 每页都只装这一页要看的那几天，列宽才不会为了迁就一条远处的任务而挤成线
      pager({
        page,
        pageCount,
        total: matched.length,
        size: taskPageSize,
        onGo: (next) => {
          page = next;
          render();
        },
        onSize: (size) => {
          taskPageSize = size;
          page = 0;
          render();
        },
      }),
    );
  };

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
    if (request.filter === null && request.taskId === null && request.urgency === null) {
      // 页面隐藏时量不到可用宽度（clientWidth 是 0），回到前台重新量一次，
      // 否则列宽会停在挂载时的兜底值上，右侧又空出一条
      render();
      return;
    }

    if (request.filter !== null) statusFilter = request.filter;
    if (request.urgency !== null) urgencyFilter = request.urgency;
    if (request.taskId !== null) {
      selectedId = request.taskId;
      // 搜索词是上一次留下的，不清掉目标任务可能根本不在结果里
      query = "";
      search.value = "";
    }

    // 换了筛选就回第一页。停在上一次翻到的那一页，「点逾期 38 条」进来看到的是
    // 第 21–38 条那半截 —— 数字没算错，但看着就像对不上。
    // 定位某条任务的请求不走这一步：它要翻到那条所在的页（见 render 的 selectedId）
    if (request.taskId === null && (request.filter !== null || request.urgency !== null)) {
      page = 0;
    }

    // 控件是常驻的，别处的跳转改了筛选值，这里得把显示跟上
    urgencyPick.setValue(urgencyFilter === "all" ? "all" : (String(urgencyFilter) as UrgencyKey));

    render();
    if (request.taskId !== null) scrollToSelected();
  });
}


