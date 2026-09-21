// ─────────────────────────────────────────────────────────────────────────────
// 任务页：时间轴表格（甘特）。
//
// **窗口固定 32 天**（`GANTT_DAYS`，2026-09-20 改的口径）：窗口不按任务跨度撑开 ——
// 它只回答「这一屏是哪一个 32 天」，看别的时间段靠**在表格上拖动**（按天吸附）。
// （工具行那排「全部 / 昨天 / 今天 / 上周…」档位 2026-09-21 撤了，理由见 `focusAnchor`。）
// 条形的时间基准是**创建日 → 截止日**；条是**整块实色**（颜色只编码状态），**不画进度** ——
// 进度在行首那枚**进度饼**、悬停小卡与条内那枚白字进度里（理由见 `renderRow` 那一段）。
//
// 左侧任务列吸附（拖动/滚动时留在原地），右侧是按日展开的格子。日期格线不是 DOM
// 节点而是 repeating-linear-gradient —— 32 天 × 28 行会多出近 900 个只用来画线的
// div，而线宽和列宽本来就同源，交给 CSS 更准也更快（列宽经 `--tt-col` 一处下发给
// 表头与格线）。
//
// 工具行（搜索框 / 计数 / 排序）在 mount 里建一次就常驻，只有 chips 里的
// 数字和下面的表格随数据重建 —— 否则每次输入都要把搜索框重新造一遍，
// 光标和输入法组合状态都会断。拖动平移的监听也挂在 mount 里建的那层（`.tt-box`）：
// `.tt-scroll` 每次 render 都被换掉，挂上去活不过第一帧。
// ─────────────────────────────────────────────────────────────────────────────

import { parseTasksDetailed, type ParseReport } from "../data/markdown";
import { TASKS, activeTasks } from "../data/mock";
import { PARTITIONS, activePartitionId } from "../data/partitions";
import { dataChanged, onDataChange } from "../data/store";
import type { Task, Urgency } from "../data/types";
import { el } from "../shell/dom";
import { dropdown } from "../shell/menu";
import { subscribePages } from "../shell/router";
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
  URGENCY_LEVELS,
  dayNumber,
  isDueToday,
  matchesStatus,
  monthDayText,
  nowStamp,
  removeTask,
  setTaskStatus,
  statusVar,
  urgencyBadge,
  urgencyText,
} from "./shared";
import { pager } from "./pager";
import { closeTask, isTaskOpen, onTaskOpen, openTask } from "./taskDrawer";
import { draftTask, taskForm } from "./taskForm";

/** 时间轴的日期窗口：起点天数 + 天数。 */
type TimelineWin = { start: number; days: number };

/**
 * 左侧任务列宽（px）。同上，pages.css 里 `.tt-label` 也写着这个数。
 *
 * 248 → 256（2026-09-20）：行首那枚圆点换成了 16px 的进度饼（原来 8px），
 * 多出来的 8px 补在这里，免得去挤标题（标题本来就在省略号上）。
 */
const LABEL_W = 256;

/** 列宽自适应区间（px）：数据少时不至于胖成一列上百像素，多时不至于挤成一根线。 */
const COL_MIN = 15;
const COL_MAX = 34;

/**
 * 甘特固定窗口：**32 天**（2026-09-20 用户定的：「按 32 天显示最美观」）。
 * 其余时间靠**拖动**看（见 mount 里的拖动平移）。
 *
 * 后续可能搬进设置做成可配（那时把这里换成读设置项）—— 现在不体现。
 */
const GANTT_DAYS = 32;

/**
 * 窗口左端（天数）。默认「**今天前 16 天**」。
 *
 * 32 天没法在「今天」两侧各放 16 天（那要 33 天），取整必然偏一天 —— 偏给**过去**：
 * 已经发生的事实要一直看得见，未来只会往后长。所以窗口 = 前 16 天 + 今天 + 后 15 天。
 */
const defaultAnchor = (): number => TODAY - 16;
let ganttAnchor = defaultAnchor();

/** 当前列宽。拖动平移要按它把位移换算成天数（按天吸附，见 mount）。 */
let currentColW = 0;

/**
 * 甘特窗口：**固定 32 天，不随数据变**。
 *
 * 以前它有两种算法：档位 → 严格等于档位（今天 = 1 天，一根根线挤在一起），「全部」→
 * 撑到装下所有任务的跨度（几百天，于是列宽被压成十几像素）。两头都不好看，而且
 * 「点哪个档位都像没反应」。现在窗口只由 `ganttAnchor` 定 ——「看别的时间段」交给拖动。
 */
function ganttWindow(): TimelineWin {
  return { start: ganttAnchor, days: GANTT_DAYS };
}

/** 跨页请求进来之后，下一次 render 要把窗口对准这批任务（见 focusAnchor）。 */
let focusNextRender = false;

/**
 * 窗口该落在哪儿：以这批任务**条形的跨度**（最早创建日 → 最晚截止日）**居中**，
 * 32 天装不下也照居中；一条任务都没有 → 回到默认的「今天前 16 天」。
 *
 * 2026-09-20 用户报的：从总览点「逾期 40」进来，窗口却停在上次拖动的位置上，目标全在
 * 屏幕外 —— 和「搜索词留在框里」是同一类「把目标挡在视图外」。
 *
 * ⚠️ 它曾经还带一个「档位段」参数：窗口与档位那段没交集时退回「档位首日 - 2」。
 * 工具行那排档位（全部 / 昨天 / 今天 / 上周 / 本周 / 上月 / 本月）2026-09-21 撤掉之后
 * （见 `data/timeline.ts` 顶部那两段说明），这一支就没有来源了。
 */
function focusAnchor(tasks: Task[]): number {
  if (tasks.length === 0) return defaultAnchor();

  let from = Number.POSITIVE_INFINITY;
  let to = Number.NEGATIVE_INFINITY;
  for (const task of tasks) {
    from = Math.min(from, dayNumber(task.created));
    to = Math.max(to, dayNumber(task.end));
  }
  const mid = Math.floor((from + to) / 2);
  return mid - Math.floor((GANTT_DAYS - 1) / 2);
}

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
    item(done ? "标记未完成" : "标记完成", () => {
      setTaskStatus(task, done ? "doing" : "done");
      toast(`「${task.title}」${done ? "已回到进行中" : "已标记完成"}`);
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

// ─── 数据迁入 ────────────────────────────────────────────────────────────────

/** 标题的比较键：首尾空白、连续空格不该把一条任务算成两条。 */
const titleKey = (text: string): string => text.replace(/\s+/g, " ").trim();

/** 当前分区的显示名（对话框要告诉用户这批会落到哪儿）。 */
const partitionName = (): string =>
  PARTITIONS.find((partition) => partition.id === activePartitionId())?.name ?? activePartitionId();

/**
 * 数据迁入：选一个 md 文件，解析成任务加进**当前分区**。
 *
 * 入口在任务管理页 —— 那页已经有「导出 ▾」，迁入是它的对称动作；实现留在这里，
 * 因为要建的是**任务**，任务域的规则（筛选复位、状态）都在这边。
 *
 * **只选文件，没有粘贴框**（2026-09-18 定）：**转换工具**（`tadado-activity-import` skill
 * 里的 `scripts/migrate-activity.mjs`）的
 * 产物本来就是**一个文件**，中间再绕一趟「打开 → 全选 → 复制 → 切窗口 → 粘贴」只是多几步；
 * 而留着粘贴框会让这个对话框同时服务「迁移」和「随手录十条」两件事 —— 「数据迁入」里
 * 粘十行新任务，名字就重新变模糊了。
 *
 * 四条刻意的设计：
 *   1. **解析出几条、哪几行认不出、哪几条与库里同名**，都要在点「导入」之前看见，
 *      而不是导完才发现少了或多了（「先对账，再动手」，与那个迁移工具同一条）；
 *   2. **重复只提示、不替用户决定**：同名不一定同一条，所以给「跳过重复」与
 *      「全部导入」两个按钮由他挑。判重规则只有一条 —— 标题在当前分区里已存在；
 *      旧版里改过标题的就认不出，这一点也写在界面上；
 *   3. 只**告知**当前分区，不猜也不拦 —— 导到哪个分区，由用户切好再进来；
 *   4. 结束时给一句**回执**（导了几条、落在哪个分区、跳过几行认不出的）——
 *      不做回执的话，「好像导了」和「其实一条没进」在界面上长得一样。
 */
export function openImportDialog(): void {
  /** 选中的文件内容。没选之前是空串，两个导入按钮都禁用。 */
  let source = "";

  // 选文件用 <input type="file"> + File.text()：WebView2 与浏览器里都能用，
  // 不需要 plugin-dialog / plugin-fs，也不需要新权限
  const fileInput = el("input", {
    type: "file",
    accept: ".md,.txt,text/markdown,text/plain",
    style: "display:none",
  });
  const fileBtn = el("button", { class: "btn", type: "button", text: "选择文件…" });
  /** 选中的文件名（选之前是空的 —— 能选什么由文件选择器自己筛，不用在这儿解释）。 */
  const fileNote = el("span", { class: "dim" });

  /** 条数：点「导入」前唯一的确认信息 —— 给它一点分量，别做成一行灰小字。 */
  const count = el("div", { class: "batch-n" });
  /**
   * 认不出的行。它们以前是**静默**跳过的（界面上只体现为条数少了）—— 而一份真实清单里
   * 八成以上的行是活动行，静默丢掉等于把历史全丢、还看不出来。现在逐条列出来。
   */
  const skipList = el("div", { class: "batch-skip" });
  /** 与当前分区里已有任务同名的：提示，不拦。 */
  const dupList = el("div", { class: "batch-dup" });

  const cancelBtn = el("button", { class: "btn", type: "button", text: "取消" });
  const skipBtn = el("button", { class: "btn", type: "button" });
  const allBtn = el("button", { class: "btn", type: "button" });

  // 卡片用宽版：要显示的是解析结果（可能十几行），336px 的提示框宽度不够看
  const card = el("div", { class: "modal-card wide batch" }, [
    el("div", { class: "modal-title", text: "数据迁入" }),
    // 这一屏只留**三样**：导到哪儿 / 选文件 / 解析结果。
    // 原来还挂着「一句话 + 代码样例 + 支持 .md/.txt」三行说明 —— 但文件是转换工具产出的，
    // 用户在这里根本不需要再看一遍写法（语法写在 `tadado-activity-import` skill 的 SKILL.md 里）。这一屏的职责是
    // **导入**，不是教 Markdown。
    el("div", { class: "batch-where" }, [
      el("span", { text: "导入到" }),
      el("b", { text: `「${partitionName()}」` }),
    ]),
    el("div", { class: "batch-file" }, [fileBtn, fileNote, fileInput]),
    count,
    skipList,
    dupList,
    el("div", { class: "modal-actions" }, [cancelBtn, skipBtn, allBtn]),
  ]);
  const mask = el("div", { class: "mask" }, [card]);

  const report = (): ParseReport => parseTasksDetailed(source);
  const drafts = (): Omit<Task, "partition">[] => report().drafts;

  /** 当前分区里已有的标题。判重范围就是这一个分区 —— 导入只影响它。 */
  const existingTitles = (): Set<string> =>
    new Set(
      TASKS.filter((task) => task.partition === activePartitionId()).map((task) =>
        titleKey(task.title),
      ),
    );

  /** 与库里同名的那些（同一标题只报一次）。 */
  const duplicates = (parsed: Omit<Task, "partition">[]): Omit<Task, "partition">[] => {
    const mine = existingTitles();
    const seen = new Set<string>();
    const hits: Omit<Task, "partition">[] = [];
    for (const draft of parsed) {
      const key = titleKey(draft.title);
      if (!mine.has(key) || seen.has(key)) continue;
      seen.add(key);
      hits.push(draft);
    }
    return hits;
  };

  const sync = (): void => {
    const { drafts: parsed, skipped } = report();
    const dups = duplicates(parsed);
    const dupKeys = new Set(dups.map((draft) => titleKey(draft.title)));
    const fresh = parsed.filter((draft) => !dupKeys.has(titleKey(draft.title)));

    count.textContent =
      source.trim() === ""
        ? "还没选择文件"
        : parsed.length > 0
          ? `共 ${parsed.length} 条`
          : "没能从文件里解析出任务行";
    count.classList.toggle("ok", parsed.length > 0);

    // 认不出的行逐条列出来。最多显示 5 条、其余折成一句 ——
    // 粘 200 行时不能把卡片撑成一面墙
    skipList.replaceChildren();
    if (skipped.length > 0) {
      skipList.append(el("div", { class: "bs-h", text: `${skipped.length} 行没能识别，会跳过：` }));
      for (const item of skipped.slice(0, 5)) {
        skipList.append(
          el("div", { class: "bs-row" }, [
            el("span", { class: "bs-ln", text: `第 ${item.line} 行` }),
            el("span", { class: "bs-tx", text: item.text }),
          ]),
        );
      }
      if (skipped.length > 5) {
        skipList.append(el("div", { class: "bs-more", text: `…另有 ${skipped.length - 5} 行` }));
      }
    }

    // 重复只报不拦。带上标签与截止 —— 只给标题的话，用户没法判断是不是同一条
    dupList.replaceChildren();
    if (dups.length > 0) {
      dupList.append(
        el("div", { class: "bs-h", text: `${dups.length} 条在当前分区里已有同名任务：` }),
      );
      for (const draft of dups.slice(0, 5)) {
        dupList.append(
          el("div", { class: "bs-row" }, [
            el("span", { class: "bs-ln", text: draft.title }),
            el("span", {
              class: "bs-tx",
              text: `${draft.tags.join(" ") || "无标签"} · ${draft.due ?? "无截止"}`,
            }),
          ]),
        );
      }
      if (dups.length > 5) {
        dupList.append(el("div", { class: "bs-more", text: `…另有 ${dups.length - 5} 条` }));
      }
    }

    // 「跳过重复」只在**真的有得跳**时才出现（整批都是重复时它什么也不做），
    // 并且它是默认动作 —— 造出重复数据的清理成本比少导几条高，想全导的人得自己点第二个
    const canSkip = dups.length > 0 && fresh.length > 0;
    skipBtn.style.display = canSkip ? "" : "none";
    skipBtn.textContent = `跳过重复，导入 ${fresh.length} 条`;
    skipBtn.classList.toggle("primary", canSkip);
    allBtn.textContent =
      parsed.length === 0
        ? "导入"
        : dups.length > 0
          ? `全部导入 ${parsed.length} 条`
          : `导入 ${parsed.length} 条`;
    allBtn.classList.toggle("primary", !canSkip);

    skipBtn.disabled = parsed.length === 0;
    allBtn.disabled = parsed.length === 0;
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

  /** 导入：`skipDup` 为真时丢掉与库里同名的那些。 */
  function runImport(skipDup: boolean): void {
    const parsed = drafts();
    const dupKeys = new Set(duplicates(parsed).map((draft) => titleKey(draft.title)));
    const picked = skipDup ? parsed.filter((draft) => !dupKeys.has(titleKey(draft.title))) : parsed;
    if (picked.length === 0) return;

    TASKS.unshift(
      ...picked.map((draft) => ({
        ...draft,
        id: `batch-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
        partition: activePartitionId(),
      })),
    );
    const { skipped } = report();
    // 导入的这批可能落在当前筛选 / 搜索词之外，先复位，否则切回任务页一条都看不见
    statusFilter = "all";
    query = "";
    dataChanged();
    close();
    // 回执：导了几条、落在哪个分区、跳过几行认不出的 —— 一次说清
    const miss = skipped.length > 0 ? ` · ${skipped.length} 行未能识别` : "";
    toast(`已导入 ${picked.length} 条到「${partitionName()}」${miss}`);
  }

  // 选文件：整份读进来就解析，不经过中间的「框」—— 所以也没有草稿这回事
  fileBtn.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", () => {
    const file = fileInput.files?.[0];
    // 读完就清值，否则连着选同一个文件第二次不触发 change
    fileInput.value = "";
    if (!file) return;
    void file
      .text()
      .then((text) => {
        source = text;
        fileNote.textContent = file.name;
        sync();
      })
      .catch(() => {
        // 读不出来就说出来：静默失败会让人以为「这个文件里没有任务」
        source = "";
        fileNote.textContent = `读不出「${file.name}」`;
        sync();
      });
  });

  cancelBtn.addEventListener("click", close);
  mask.addEventListener("click", (event) => {
    if (event.target === mask) close();
  });
  skipBtn.addEventListener("click", () => runImport(true));
  allBtn.addEventListener("click", () => runImport(false));

  document.body.append(mask);
  window.addEventListener("keydown", onKey, true);
  requestAnimationFrame(() => {
    mask.classList.add("show");
    fileBtn.focus();
  });
  sync();
}

// ─── 页面状态 ────────────────────────────────────────────────────────────────

let statusFilter: StatusFilter = "all";
/** 优先级筛选。总览的「优先级分布」点某一档时由 focus 请求带过来。 */
let urgencyFilter: UrgencyFilter = "all";
/**
 * 只看「今天到期」（总览那张指标卡的落点）。
 *
 * 它和状态筛选**互斥**：两个维度同时生效时，「点进来只看到 1 条」说不清是筛出来的
 * 还是漏掉的（与 focus.ts 里「一次跳转只表达一个意图」同一条理由）。所以点它就把
 * 状态复位成「全部」，点状态那排就把这个开关关掉。
 *
 * 判据用 `isDueToday`（pages/shared.ts）—— 总览那张卡数的是**同一个函数**。
 * 两边各写一份的话，就会退回到「卡片上写 1、点进去 0 条」。
 */
let dueTodayOnly = false;
/** 时间轴表格翻到第几页（0 起）。换筛选 / 排序都回到第一页。 */
let page = 0;
/** 当前每页几条。分页器上那个下拉改它。 */
let taskPageSize = TASK_PAGE_SIZE;
let query = "";
/**
 * 默认排序：**按优先级**（2026-09-21 用户定的，原来默认「按截止日期」）。
 * 优先级相同时按截止日期排（见 comparators），所以它不会把「今天必须交的 P1」
 * 埋在一堆 P0 后面 —— 两档一起看才是这一页想要的顺序。
 */
let sortKey: SortKey = "urgency";
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
    (task) =>
      // 「进行中」是一个**合并口径**（待办 + 进行中），判定在 shared.ts 的
      // `matchesStatus` —— 与总览那张卡、管理页那个筛选是同一个函数
      matchesStatus(task, statusFilter) &&
      // 「今天到期」是另一个维度（截止日，不是状态）。开启时状态那排一定停在
      // 「全部」（见 dueTodayOnly），所以这里最多只是再多一道
      (!dueTodayOnly || isDueToday(task)),
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
      // 与条形的基准一致：**创建 → 截止**（开始日不再决定条形，见 renderRow）
      text: `创建 ${monthDayText(dayNumber(task.created))} → 截止 ${monthDayText(dayNumber(task.end))}`,
    }),
    el("div", {
      class: "mono dim",
      text: `${STATUS_LABEL[task.status]} · 进度 ${task.progress}%`,
    }),
    el("div", {
      class: "mono dim",
      text: `${task.tags.join(" ") || "无标签"} · ${urgencyText(task.urgency)}`,
    }),
    el("div", {
      class: "mono dim",
      style: "margin-top:5px",
      // 右键**不是**打开抽屉（那是右键菜单里的第一项）：右键给的是「不挪视线就能处置」
      // 的那一列动作。这句话原来把两者说成等价，照着做会以为右键坏了（2026-09-21 修）
      text: "双击打开维护抽屉 · 右键处置（标记完成 / 删除）",
    }),
  );
  node.style.display = "block";
  moveTip(x, y);
}

function hideTip(): void {
  if (tip) tip.style.display = "none";
}

// ─── 行 ──────────────────────────────────────────────────────────────────────

// ─── 行首的「进度饼」 ────────────────────────────────────────────────────────
//
// 它取代了原来那枚 8px 的圆点。圆点**只有颜色一个通道**，而它表达的是状态
// （逾期红 / 待办蓝 / 进行中橙 / 已完成绿）—— 一个裸色点挂在任务名前面，谁都会
// 以为那是进度（2026-09-20 就是这么问过来的）。
//
// 现在两个通道各说一件事：
//   · **形状 = 进度**：扇形从 12 点起顺时针长，没满一圈就是没做完；
//   · **颜色 = 状态**：沿用原来那套 statusVar()，所以顺手把那个圆点也替掉了。
//
// 两端各给一个更好认的记号（与用户给的参考图对齐）：
//   · 待办 + 0% → **▶**：还没开始，可以动手；
//   · 100% → **✓**：做完了，不必再让人去数一个满格的扇形。
// 中间那几档就是扇形本身 —— 25% / 50% / 75% 扫一眼就分得开。

const PLAY_MARK =
  '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M8.5 5.2l10.5 6.8-10.5 6.8z"/></svg>';
/**
 * 勾固定白色：底是状态色的**实心圆**（绿 / 橙 / 蓝 / 红都上过色），白勾在四种底上
 * 都看得清；跟着 currentColor 走就会和底同色，等于没画。
 */
const CHECK_MARK =
  '<svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"><path d="M6 12.6l4.2 4.2L18 7.6"/></svg>';

/**
 * 行首那枚进度饼。
 *
 * 扇形交给 CSS 算（`conic-gradient`）：TS 只把百分比写进 `--pct` 一个变量，
 * 不在 JS 里拼样式字符串 —— 进度有多少种值，样式都只有一条。
 *
 * `data-pct` / `data-mark` 不只是给 e2e 用的：进度现在是**画出来的**，DOM 上留一份
 * 可读的值，读屏、调试、以及「和悬停提示对不对得上」这类断言才有个据。
 */
function progressDot(task: Task): HTMLElement {
  const node = el("span", {
    class: `pdot st-${task.status}`,
    "data-pct": String(task.progress),
  });
  node.style.color = statusVar(task.status);
  node.style.setProperty("--pct", `${task.progress}%`);
  node.title = `状态：${STATUS_LABEL[task.status]} · 进度 ${task.progress}%`;

  if (task.progress >= 100) {
    node.dataset.mark = "check";
    node.innerHTML = CHECK_MARK;
  } else if (task.status === "doing" && task.progress === 0) {
    node.dataset.mark = "play";
    node.innerHTML = PLAY_MARK;
  } else {
    node.dataset.mark = "pie";
  }
  return node;
}

function renderRow(
  task: Task,
  win: TimelineWin,
  colW: number,
  /** 窗口里每个「月初」的天数（最多两个）。画一条月分隔线用。 */
  monthStarts: number[],
): HTMLElement {
  const dot = progressDot(task);

  const label = el("div", { class: "tt-label" }, [
    dot,
    el("div", { class: "lt" }, [
      // 第一行**只放标题**：截止与优先级都挪到第二行（和标签同排），标题才吃得满这一列。
      // 它们三个都是短记号，让它们去分标题的宽度是本末倒置 —— 标题是这一行的主语，
      // 被挤成省略号就等于「列表里看不出这是哪条任务」
      el("div", { class: "lt1" }, [
        // title 属性留着：列宽有限，截短了的标题悬浮仍能看全
        el("span", { class: "t", text: task.title, title: task.title }),
      ]),
      el("div", { class: "lt2" }, [
        ...task.tags.map((tag) => el("span", { class: "tag", text: tag })),
        el("span", { class: "dlt", text: task.due ? `⏰ ${task.due}` : "无截止" }),
        // 优先级钉在这一排的右端（任务列的右端）。行首那枚**进度饼**的颜色才是
        // 状态 —— 一左一右两个通道分开摆，不用去猜颜色
        urgencyBadge(task.urgency),
      ]),
    ]),
  ]);

  // 条形按**创建日 → 截止日**画（2026-09-20 用户提的）：这条任务从哪天进入视野、
  // 到哪天必须交 —— 比「开始日 → 截止日」更贴近「我手上这摊活儿」的读法
  // （开始日只是它被排上日程的那天，创建日才是它出现的那天）。
  // 两端跨出窗口时夹到边界：一条跨月的任务在这个 32 天窗口里应该是一条顶住边的长条，
  // 而不是溢出到表格外面的怪物。
  const createdDay = dayNumber(task.created);
  const endDay = dayNumber(task.end);
  const winEnd = win.start + win.days - 1;
  const first = Math.max(createdDay, win.start);
  /**
   * 逾期：条的右端**渲染**延长到「今天」—— 数据里的结束日一个字节都不动（那是事实，
   * 这是解释，与 §4.10 那条「完成日 + N」同一类规矩）。延长之后「拖了多久」一眼看得见。
   */
  const overdue = task.status === "overdue" && endDay < TODAY;
  const last = overdue
    ? Math.max(Math.min(endDay, winEnd), Math.min(TODAY, winEnd))
    : Math.min(endDay, winEnd);
  const span = Math.max(last - first + 1, 1);

  const bar = el("div", { class: `tt-bar st-${task.status}`, "data-task": task.id });
  // 进度：**填到条的百分之几**（2026-09-21 用户提的「不同进度的感觉差异不大」）。
  // 条的长度仍是**时间跨度**、颜色仍是**状态** —— 进度是**第三件事**，所以它只能靠
  // 「填了多少」说（见 pages.css 里 `.tt-bar::before` 那段说明：为什么这次又把它请回来了）
  bar.style.setProperty("--fill", `${task.progress}%`);
  const barWidth = Math.max(span * colW - 4, 10);
  // 左右各留 2px：相邻任务挨在一起时还看得出是两条
  bar.style.left = `${(first - win.start) * colW + 2}px`;
  bar.style.width = `${barWidth}px`;

  /** 条内某一天对应的像素（0 = 条的左端）。条左右各缩 2px，这里按列宽折算 ——
   *  高亮描边最多差这 2px，肉眼看不出来。 */
  const barX = (day: number): number => (day - first) * colW - 2;

  /** 条上的一段：颜色由类名定（见 CSS），几何按 barX 折算；空段返回 null。 */
  const segOf = (from: number, to: number, cls: string): HTMLElement | null => {
    if (to < from) return null;
    const x = Math.max(0, barX(from));
    const right = Math.min(barWidth, barX(to + 1));
    if (right - x < 1) return null;
    const node = el("span", { class: `seg ${cls}` });
    node.style.left = `${x}px`;
    node.style.width = `${Math.max(right - x, 2)}px`;
    return node;
  };

  // ── 标准甘特：一条 = 这一段时间（2026-09-21 用户定的）──
  // 条只回答「这条任务占着哪段时间」：**单色、整块**（颜色 = 状态），不画进度、也不按档位
  // 切段。理由：**进度与持续时间叠在一条上会互相打糊** —— 进度是个标量，画在条上只能靠
  // 「填充长度」，而填充长度与时间长度是两个不同的量；一条上放两个量，读者分不清哪个是
  // 哪个（上一版还叠了「范围内外」这第三层，最该看清的东西反而被盖住）。
  // **进度**因此不在条上：它在行首那枚**进度饼**（本来就是它该待的地方）、悬停小卡，
  // 以及条形够宽时条内那枚白字进度里。
  // 逾期那一条：条右端**渲染**延长到今天（数据里的结束日一个字节都不动 —— 那是事实，
  // 这是解释，与 §4.10 那条同源），并在原结束日处留一道竖记 ——「还在拖、从哪天开始拖」
  // 一眼看得见（不延长的话，逾期与「刚好今天截止」在图上长得一模一样）。
  if (overdue) {
    const late = segOf(Math.max(endDay + 1, first), last, "seg-late");
    if (late) bar.append(late);
    const mark = el("span", { class: "late-mark" });
    mark.style.left = `${barX(endDay + 1)}px`;
    bar.append(mark);
  }

  // 条内白字压在**实色**条上（条本身就是实色），所以只要条够宽就写得下。
  // 只写**进度**：标题在左边任务列里已经占了一整行（2026-09-21 用户提的「没必要再显示
  // 任务名称」），条上再写一遍是同一句话说两遍，而条的宽度本来就紧张 —— 省下的都还给进度。
  // 阈值也跟着降（78 → 40）：文字只剩「80%」这种三四个字符，太高的门槛会让大半条上是空的。
  if (barWidth > 40) {
    const caption = el("b", { text: `${task.progress}%` });
    caption.style.maxWidth = `${barWidth - 12}px`;
    bar.append(caption);
  }

  // 条形顶到最后一列时，收尾圆点会被表格右边界切掉一半。
  // 逾期的条右端已经延到今天、且原结束日另有竖记，这里就不再摆圆点（那会指错地方）
  if (!overdue && last < winEnd) bar.append(el("span", { class: "end" }));

  // 被窗口截掉的两端各打一条竖记：贴边的一条和「它就这么长」长得一模一样，不标出来
  // 就会被读成「这条任务只干了这几天」。
  // 整条都在窗口**外**时（32 天窗口 + 拖动，这是常事）两侧都打上：只打一侧会被读成
  // 「它从窗口外伸进来、在这里就结束了」
  const beforeWin = createdDay < win.start;
  const afterWin = endDay > winEnd;
  if (beforeWin || last < first) bar.append(el("span", { class: "cut cut-l" }));
  if (afterWin || last < first) bar.append(el("span", { class: "cut cut-r" }));

  bar.addEventListener("mouseenter", (event) => showTip(task, event.clientX, event.clientY));
  bar.addEventListener("mousemove", (event) => moveTip(event.clientX, event.clientY));
  bar.addEventListener("mouseleave", hideTip);

  const track = el("div", { class: "tt-track" });
  track.style.width = `${win.days * colW}px`;

  // 月分隔线：一条 1px 的竖线，标出「这里是 1 号」。32 天窗口最多跨两次月首，
  // 所以每个行里最多两条 —— 比给每个日期格画框省得多（那要多出近千个节点）。
  // 摆在最下层（在日期带和条之下）
  for (const day of monthStarts) {
    const line = el("span", { class: "tt-moline" });
    line.style.left = `${(day - win.start) * colW}px`;
    track.append(line);
  }

  // 档位那条日期带（`.tt-band`）与表头那几格高亮（`.tt-date.in-range`）都在 2026-09-21
  // 撤了：条已回到标准甘特（一条 = 一段时间，单色），而「范围内外」是第三个量，压在
  // 19px 的条上只会把最该看清的东西盖住。整排档位按钮也在同一天一起撤（见 data/timeline.ts）
  track.append(bar);

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

    // 新任务可能落在当前筛选 / 搜索词之外，先复位再定位，否则建完就消失
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

/** 页头动作（见 registry 的 actions）：任务页现在只有一个 —— 单条新建。 */
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

  // 「批量新建」原来就在这儿：工具行里、搜索框右边，只写「批量」两个字。
  // 它是个**新建**入口，却夹在搜索与筛选之间，又和任务管理页真正的「批量操作」
  // 撞词 —— 既不像是新建，也看不出是个动词。现在挪到页头、和「＋ 新建任务」
  // 并排（见 registry 的 actions）。

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

  // （工具行那排档位 seg 撤了 —— 2026-09-21。它 2026-09-20 的用途是「点一下，除了筛选，
  //   还把这一段范围内的进度在条上突出来」，而条在那之后就改回了标准甘特（不画进度、
  //   不按档位切段）：用途没了，只剩「只列这段时间**动过**的任务」这一件 ——
  //   而那件事读起来像「看哪段时间」，实际会让任务成批消失，反而不容易理解。）

  /**
   * 优先级筛选。总览的「优先级分布」点某一档时由 focus 请求带过来，
   * 这里也能自己换 —— 入口只有这一个，和状态那排 chips 并列。
   */
  type UrgencyKey = "all" | "0" | "1" | "2" | "3";
  const urgencyPick = dropdown<UrgencyKey>({
    items: [
      { value: "all", label: "全部优先级" },
      // 文案与总览「优先级分布」那五行、以及列表里的 `Px` 徽标三处对齐：
      // 都写成 `紧急(P0)`。以前这里是 `P0 紧急`，总览那边只有「紧急」——
      // 两个说法要用户自己合并，「点总览那一档进来」时也不好确认是不是同一档
      ...URGENCY_LEVELS.map((level) => ({
        value: String(level) as UrgencyKey,
        label: urgencyText(level),
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

  // ── 横向拖动 = 平移窗口 ────────────────────────────────────────────────────
  // 窗口固定 32 天之后，「看别的时间段」就只剩拖动这一条路（用户的口径：
  // 「其他只需要拖动即可」）。按**天**吸附：拖过半格才挪一天，手感像翻日历，
  // 也不会停在「3.7 天」这种位置上。
  //
  // 监听挂在 .tt-box 上而**不是** .tt-scroll：后者每次 render 都被换掉（见 render
  // 末尾的 table.replaceChildren），挂上去第一帧之后就收不到事件了。
  let dragFromX = 0;
  let dragFromAnchor = 0;
  let dragging = false;
  let dragged = false;

  table.addEventListener("pointerdown", (event) => {
    if (event.button !== 0 || currentColW <= 0) return;
    dragging = true;
    dragged = false;
    dragFromX = event.clientX;
    dragFromAnchor = ganttAnchor;
    // ⚠️ 这里**不能**捕获指针：捕获会把后续的 mouseup 重定向到 table，于是 click /
    // dblclick 落到 table 上（它们取 mousedown 与 mouseup 的公共祖先）—— 行上的
    // 「单击选中 / 双击开抽屉」就全没了。真开始拖的那一步再捕获（见 pointermove）
  });

  table.addEventListener("pointermove", (event) => {
    if (!dragging) return;
    const dx = event.clientX - dragFromX;
    // 5px 以内当点击：不然「选中一行」会变成「窗口挪了一格」
    if (!dragged && Math.abs(dx) < 5) return;
    if (!dragged) {
      dragged = true;
      table.classList.add("dragging");
      // 从这一刻起捕获：拖出表格边界（拖到任务列上、拖出窗口）也继续跟手
      table.setPointerCapture(event.pointerId);
    }
    const days = Math.round(dx / currentColW);
    const next = dragFromAnchor - days;
    if (next !== ganttAnchor) {
      ganttAnchor = next;
      render();
    }
  });

  const endDrag = (): void => {
    if (!dragging) return;
    dragging = false;
    table.classList.remove("dragging");
  };
  table.addEventListener("pointerup", endDrag);
  table.addEventListener("pointercancel", endDrag);

  // 刚拖过就别让它顺手变成「点了某一行」或「双击开了抽屉」。捕获阶段拦：
  // 行自己的 click / dblclick 还没轮到（这两个都得拦 —— 拖完松手那一下会同时产生
  // click，双击里的第一下也可能正好落在拖动之后）
  const swallowAfterDrag = (event: Event): void => {
    if (!dragged) return;
    event.stopPropagation();
    event.preventDefault();
  };
  table.addEventListener(
    "click",
    (event) => {
      if (!dragged) return;
      dragged = false; // 这一次算「拖完的余波」，下一次点击才是正常的点击
      swallowAfterDrag(event);
    },
    true,
  );
  table.addEventListener("dblclick", swallowAfterDrag, true);

  // 工具行和表格包在同一个容器里：直接挂两个子节点给 .page-body，
  // 它的 gap 会和 .tools 自己的 margin-bottom 叠加成 28px。
  host.append(
    el("div", { class: "tt-page" }, [
      el("div", { class: "tools" }, [
        el("span", { class: "searchbox" }, [
          el("span", { class: "ic", html: SEARCH_ICON }),
          search,
        ]),
        chips,
        urgencyPick.root,
        el("span", { class: "grow" }),
        count,
        sortPick.root,
      ]),
      table,
    ]),
  );

  const render = (): void => {
    // 输入框里的字可能被别处改过（新建任务会清空 query），搜索框自己不知道
    if (search.value !== query) search.value = query;

    // 顺序：先筛，再让窗口去迁就筛出来的这批（见 focusAnchor）。
    // 反过来「先定窗口、再拿窗口砍任务」的结果就是总览写 4、这里只画 3。
    const matched = visibleTasks();

    // 跨页请求进来的那一帧：把窗口对准这批任务（之后一律尊重用户的拖动）
    if (focusNextRender) {
      focusNextRender = false;
      ganttAnchor = focusAnchor(matched);
    }

    const pageCount = Math.max(1, Math.ceil(matched.length / taskPageSize));
    if (page >= pageCount) page = pageCount - 1;

    // 翻到**定位的那条所在的页**：抽屉开了、列表里却没有它，看着就像跳转坏了
    if (selectedId !== null) {
      const at = matched.findIndex((task) => task.id === selectedId);
      if (at >= 0) page = Math.floor(at / taskPageSize);
    }

    const rows = matched.slice(page * taskPageSize, (page + 1) * taskPageSize);

    // 窗口：**固定 32 天**（2026-09-20 用户定的），不随数据撑开 —— 看别的时间段靠**拖动**。
    // 32 天正好铺满（列宽自适应），所以不再需要「按任务跨度撑窗口」那套（fitWindow 已撤）
    const win = ganttWindow();
    const winEnd = win.start + win.days - 1;

    // 页面隐藏时 clientWidth 量不到（display:none 下是 0），给个够用的兜底值，
    // 切回前台会再 render 一次重算（见 mount 末尾的 subscribePages）
    const colW = columnWidth(win.days, table.clientWidth > 0 ? table.clientWidth : 1080);
    currentColW = colW;

    // ── chips（数量随数据变）──
    // 数字按 poolTasks 算（含优先级 / 搜索，不含状态），于是「chip 上写几
    // 条」＝「点开后表里几行」。以前按 activeTasks 全量算，点进去对不上。
    const pool = poolTasks();
    chips.replaceChildren();
    for (const filter of FILTERS) {
      const total =
        filter.value === "all"
          ? pool.length
          : pool.filter((task) => matchesStatus(task, filter.value)).length;
      // 「今天到期」开着时状态那排**一个都不高亮**：那时列表是「今天到期」那批，
      // 不是「全部」—— 两个 chip 同时亮着，读起来像这次筛选有两层，说不清
      const on = !dueTodayOnly && statusFilter === filter.value;
      const chip = el("button", {
        class: `chip ${on ? "on" : ""}`,
        type: "button",
      }, [filter.label, el("span", { class: "cn", text: String(total) })]);
      chip.addEventListener("click", () => {
        statusFilter = filter.value;
        dueTodayOnly = false;
        page = 0;
        render();
      });
      chips.append(chip);
    }

    // 「今天到期」是**另一个维度**（截止日，不是状态），所以单独一枚、排在最末。
    // 它是总览那张指标卡的落点：没有它，点进来只看到 1 条 —— 页面上没有任何地方
    // 说得出为什么，也没有出口。数字同样按 pool 算，于是「chip 上写几条」＝
    // 「点亮后表里几行」
    const dueChip = el("button", {
      class: `chip ${dueTodayOnly ? "on" : ""}`,
      type: "button",
      title: "只看今天到期的任务（有截止、截止在今天、未完成）",
    }, ["今日到期", el("span", { class: "cn", text: String(pool.filter(isDueToday).length) })]);
    dueChip.addEventListener("click", () => {
      // 再点一次退回全部 —— 它是开关，不是单向跳转
      dueTodayOnly = !dueTodayOnly;
      statusFilter = "all";
      page = 0;
      render();
    });
    chips.append(dueChip);

    // 两个数都摆出来：筛出几条（当前筛选的结果）/ 一共几条（当前分区未归档）。
    // 少写一个，用户就分不清是「被筛掉了」还是「在别的页上」
    count.textContent = `筛出 ${matched.length} · 共 ${activeTasks().length}`;

    const dayCells: HTMLElement[] = [];
    /** 窗口里的「月初」（最多两个）：行里的月分隔线 + 表头那格改写字月份都靠它。 */
    const monthStarts: number[] = [];
    for (let offset = 0; offset < win.days; offset += 1) {
      const day = win.start + offset;
      const date = new Date(day * DAY_MS);
      const weekday = date.getUTCDay();
      const isMonthStart = date.getUTCDate() === 1;
      if (isMonthStart) monthStarts.push(day);
      const cell = el(
        "div",
        {
          // data-day：这一格是哪一天（绝对天数）。表头只写「几号」，跨月就分不出是哪个月，
          // 而拖动/窗口这类断言需要精确比天数
          "data-day": String(day),
          class: `tt-date ${weekday === 0 || weekday === 6 ? "wknd" : ""} ${
            day === TODAY ? "today" : ""
          } ${isMonthStart ? "mo-start" : ""}`,
        },
        [
          el("span", { class: "dn", text: String(date.getUTCDate()) }),
          // 月首那一格把「周几」换成「几月」：跨月的地方，说清是哪个月比说周几有用
          // （行里同一列还画着一条月分隔线，两处指的是同一根线）
          el("span", {
            class: "dw",
            text: isMonthStart ? `${date.getUTCMonth() + 1}月` : WEEKDAY_SHORT[weekday],
          }),
        ],
      );
      dayCells.push(cell);
    }

    const body = rows.map((task) => renderRow(task, win, colW, monthStarts));

    const grid = el("div", { class: "tt-grid" });
    grid.style.width = `${LABEL_W + win.days * colW}px`;
    // 列宽交给 CSS 变量：表头日期格的宽度和 .tt-track 的格线周期都从这里取，
    // 于是「让列宽铺满」这件事只有 tasks.ts 一个地方说了算
    grid.style.setProperty("--tt-col", `${colW}px`);
    // 周末竖带的位置：窗口首日到**第一个周六**的天数。CSS 那边用「7 天一个周期、
    // 宽 2 天」的 repeating 渐变画，靠 `background-position` 把它挪到这个起点上 ——
    // 每格一个节点那种画法在 32 天 × 28 行下要多出近千个只用来铺色的 div
    const satOffset = (6 - new Date(win.start * DAY_MS).getUTCDay() + 7) % 7;
    grid.style.setProperty("--tt-wk", `${satOffset * colW}px`);

    // 表头那句区间：既是「我现在看的是哪 32 天」，也是**回到今天**的入口 ——
    // 拖远了之后没有出口就会迷路（窗口固定之后，昨天那批数据可能在屏幕外好几个星期）。
    // 今天不在窗口里时它变成可点的强调色
    const todayVisible = TODAY >= win.start && TODAY <= winEnd;
    const rangeText = el("span", {
      class: `mono tt-range ${todayVisible ? "dim" : "off"}`,
      text: todayVisible
        ? `${monthDayText(win.start)} – ${monthDayText(winEnd)}`
        : `↺ 回到今天（${monthDayText(win.start)} – ${monthDayText(winEnd)}）`,
      title: "窗口固定 32 天 · 在表格上按住拖动可左右平移 · 点这里回到今天",
    });
    rangeText.addEventListener("click", () => {
      ganttAnchor = defaultAnchor();
      render();
    });

    grid.append(
      el("div", { class: "tt-hrow" }, [
        el("div", { class: "tt-label" }, [
          el("span", { class: "dim mono", text: "任务" }),
          el("span", { class: "grow" }),
          rangeText,
        ]),
        ...dayCells,
      ]),
      ...(body.length > 0
        ? body
        : [
            el("div", {
              class: "empty",
              // 这里原来写「…区间内没有任务」—— 那是窗口还在**筛掉行**的年代留在话里的
              // 后遗症（现在窗口固定 32 天，只画不裁）。空表只可能因为状态筛选或搜索，
              // 所以按这两样说（档位那排同一天撤了）
              text: "当前筛选下没有任务 —— 可切换状态，或清空搜索",
            }),
          ]),
    );

    // 「今天」那条竖线：**只在今天确实落在窗口里时才画**（2026-09-21 用户提的）。
    // 拖到别的月份去之后，一条画在屏幕外、或被夹到边上的线只会误导人 ——
    // 那时候的出口是表头那句「↺ 回到今天」。
    // 复用上面算好的 `todayVisible`：同一件事（今天在不在窗口里）只判一次
    if (todayVisible) {
      const todayLine = el("div", {
        class: `tt-today${TODAY === win.start ? " at-start" : ""}${
          TODAY === winEnd ? " at-end" : ""
        }`,
      });
      todayLine.style.left = `${LABEL_W + (TODAY - win.start) * colW + colW / 2}px`;
      grid.append(todayLine);
    }

    table.replaceChildren(
      el("div", { class: "tt-wrap" }, [el("div", { class: "tt-scroll" }, [grid])]),
      // 窗口固定 32 天，所以翻页时表头的区间不变 —— 换页只是换行，不换时间
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

  // 首页**不**动窗口：默认就是「今天前 16 天」（`defaultAnchor`）—— 那是最中性的起点。
  // 曾经这里也要对准一次（那时默认档位是「本周」，不对准两者就各说各话）；档位撤了
  // 之后没有「对谁」这回事了。跨页请求进来时仍会对准（见 consumeTasksRequest）。
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
    // 这次切回页面是否带着「要看某个东西」的意图。四个维度都算一个都不能漏 ——
    // 漏掉 dueToday 的话，从总览点「今日到期」进来会被当成普通切页：搜索词不复位、
    // 页码不清零，明明写着 1 条却可能一条都看不到
    const jumping =
      request.taskId !== null ||
      request.filter !== null ||
      request.urgency !== null ||
      request.dueToday;

    if (!jumping) {
      // 页面隐藏时量不到可用宽度（clientWidth 是 0），回到前台重新量一次，
      // 否则列宽会停在挂载时的兜底值上，右侧又空出一条
      render();
      return;
    }

    if (request.filter !== null) statusFilter = request.filter;
    if (request.urgency !== null) urgencyFilter = request.urgency;
    if (request.taskId !== null) selectedId = request.taskId;
    // 「今天到期」跟着请求走：点它进来的那次为真，其余的（按状态 / 按优先级 /
    // 定位某条任务）都把它关掉 —— 否则「上一批是今日到期」这个状态会跟到下一批数据上
    dueTodayOnly = request.dueToday;

    // 从总览跳进来的请求，**一律清掉搜索词**。
    // 搜索框里留着上一次的字，目标任务可能根本不在结果里 —— 现象就是「总览上写着
    // 『进行中 2』，点进来只看到 1 条，另一条明明刚建」。以前只有「定位某条任务」
    // 那条路径清了，点数字卡和点优先级分布这两条漏了。
    query = "";
    search.value = "";

    // 换了筛选就回第一页。停在上一次翻到的那一页，「点逾期 38 条」进来看到的是
    // 第 21–38 条那半截 —— 数字没算错，但看着就像对不上。
    // 定位某条任务的请求不走这一步：它要翻到那条所在的页（见 render 的 selectedId）
    if (request.taskId === null) page = 0;

    // 控件是常驻的，别处的跳转改了筛选值，这里得把显示跟上
    urgencyPick.setValue(urgencyFilter === "all" ? "all" : (String(urgencyFilter) as UrgencyKey));

    // 窗口也重新对准这批（点「逾期 40」进来，窗口却停在上次拖动的位置上，目标全在
    // 屏幕外 —— 和「搜索词留在框里」是同一类「把目标挡在视图外」，理由一样）
    focusNextRender = true;
    render();
    if (request.taskId !== null) scrollToSelected();
  });
}


