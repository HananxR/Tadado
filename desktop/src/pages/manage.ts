// ─────────────────────────────────────────────────────────────────────────────
// 任务管理页：可多选的表格 + 标签管理。
//
// 表格是唯一会显示**已归档**任务的视图（其余视图一律 activeTasks()），所以取数走
// `partitionTasks()` —— 它是「本分区的全部任务（含归档）」。
//
// ⚠️ 这里曾经直接读 `TASKS`：当初只想放开「不看归档」这一个条件，却把**分区过滤也
// 一起放开了** —— 于是切到空分区时总览 / 任务 / 图谱都空了，管理页还列着别的分区的
// 任务，连分区口令那道屏风也一起绕过去了。要放开归档就只放开归档：`partitionTasks()`
// 与 `activeTasks()` 只差这一个条件。
//
// 「合并」不是一个独立按钮：把 A 改名为一个已经存在的 B，语义上就是合并。
// 单独做一个合并按钮反而要引入「再选第二个标签」的两段式交互，
// 而结果和改名完全一样。所以这里只做改名，并在目标已存在时把话说清楚。
// ─────────────────────────────────────────────────────────────────────────────

import { groupedText, type ExportGroup } from "../data/export";
import { TASKS, partitionTasks } from "../data/mock";
import { activePartitionId } from "../data/partitions";
import { dataChanged, keepActive, onDataChange } from "../data/store";
import { UNTAGGED } from "../data/tags";
import type { Task, TaskStatus } from "../data/types";
import { el } from "../shell/dom";
import { confirmAction } from "../shell/confirm";
import { exportButton } from "../shell/exportMenu";
import { subscribePages } from "../shell/router";
import { toast } from "../shell/toast";
import { consumeArchivedRequest, jumpToTask } from "./focus";
import { pager } from "./pager";
import {
  PAGE_SIZE,
  STATUS_LABEL,
  TODAY,
  dayNumber,
  isoDay,
  matchesStatus,
  monthDayText,
  pad2,
  setTaskStatus,
} from "./shared";
import { openImportDialog } from "./tasks";

/** 当前每页几条。分页器上那个下拉改它（默认 PAGE_SIZE）。 */
let pageSize = PAGE_SIZE;

/**
 * 一条单选：**每一枚 = 一个视图**（2026-09-21 用户定的）。
 *
 * 以前这里是**两组** chip ——「状态」一排（全部状态 / 逾期 / 待办 / 进行中 / 已完成）+
 * 「归档」一排（未归档 / 已归档），各自单选。两组都「只亮一枚」、又挨在一起，看起来就是
 * **一条**单选行里亮了两枚 —— 于是被当成坏了（用户问「默认怎么不是全部状态」）。
 *
 * 现在合成一条：「全部状态 / 逾期 / 待办 / 进行中 / 已完成」不筛归档（两侧都算，归档列那
 * 一列会告诉你哪条是哪条），「未归档 / 已归档」不筛状态。点一枚 = 同时定下这两件事 ——
 * 所以永远只有一枚亮着，默认就是**全部状态**。
 *
 * 代价（说清楚，不是没代价）：**组合筛选没了** —— 「已完成 × 已归档」这种问法在这条行里
 * 表达不出来。换来的是这一页的筛选一眼就懂。
 */
type ManageView = TaskStatus | "all" | "active" | "archived";

const VIEW_OPTIONS: { value: ManageView; label: string }[] = [
  { value: "all", label: "全部状态" },
  // 顺序写死：「逾期」排在最前（它最急），后面两个按进展排 —— 不写成遍历
  // `STATUS_LABEL`，那样顺序取决于对象的键序，改个定义就悄悄变了。
  // （「待办」那枚 2026-09-21 撤了：它和「进行中」是同一件事的两面，见 types.ts）
  { value: "overdue", label: STATUS_LABEL.overdue },
  { value: "doing", label: STATUS_LABEL.doing },
  { value: "done", label: STATUS_LABEL.done },
  { value: "active", label: "未归档" },
  { value: "archived", label: "已归档" },
];

// ─── 页面状态 ────────────────────────────────────────────────────────────────

let statusFilter: TaskStatus | "all" = "all";
/**
 * 归档那一维。只有两枚 chip（未归档 / 已归档），但这里要有**第三态** `"all"` ——
 * 它是状态那几枚在用的：点了「已完成」就意味着「不筛归档（两侧都算）」。
 * 两维默认都清空 = 亮着那枚「全部状态」。
 */
let archiveFilter: "active" | "archived" | "all" = "all";
let page = 0;
let selected = new Set<string>();
let tagQuery = "";
let selectedTag: string | null = null;

/** 这一页当前是哪一个视图（哪一枚 chip 亮着）。 */
const viewOf = (): ManageView =>
  statusFilter !== "all" ? statusFilter : archiveFilter === "all" ? "all" : archiveFilter;

/**
 * 点某一枚 chip：它**同时**定下状态与归档两件事 —— 状态那几枚不筛归档、归档那两枚不筛状态。
 * 所以永远只有一枚亮着（真·单选），不会出现「一行里亮了两枚」那种读起来像坏了的画面。
 */
const applyView = (view: ManageView): void => {
  statusFilter = view === "active" || view === "archived" || view === "all" ? "all" : view;
  archiveFilter = view === "active" || view === "archived" ? view : "all";
  page = 0;
};

/**
 * 只影响本页表格的渲染（翻页、勾选、换筛选），不广播给别的页面。
 *
 * 和 dataChanged() 分开是有必要的：翻一页表格没必要让图谱页重建 ——
 * 那会把用户在图上调好的缩放和节点位置一起清掉。
 */
let refreshTable: (() => void) | null = null;
/** 表格里点标签胶囊时要同步标签管理卡的选中态。 */
let refreshTagCard: (() => void) | null = null;

// ─── 取数 ────────────────────────────────────────────────────────────────────

function tableRows(): Task[] {
  return partitionTasks().filter((task) => {
    // 「进行中」是**合并口径**（待办 + 进行中），判定在 shared.ts 的 `matchesStatus`
    // —— 与总览那张卡、任务页那排 chip 是同一个函数。三处各写一份，管理页就会是
    // 「点同一件事，这边 17 条、那边 41 条」
    if (!matchesStatus(task, statusFilter)) return false;
    if (archiveFilter === "active" && task.archived) return false;
    if (archiveFilter === "archived" && !task.archived) return false;
    return true;
  }).sort((a, b) => dayNumber(b.created) - dayNumber(a.created) || a.id.localeCompare(b.id));
}

function tagRows(): { tag: string; tasks: number; activities: number }[] {
  const counts = new Map<string, { tasks: number; activities: number }>();
  for (const task of partitionTasks()) {
    for (const tag of task.tags) {
      const entry = counts.get(tag) ?? { tasks: 0, activities: 0 };
      entry.tasks += 1;
      entry.activities += task.activities.length;
      counts.set(tag, entry);
    }
  }
  return [...counts]
    .map(([tag, entry]) => ({ tag, ...entry }))
    .sort((a, b) => b.tasks - a.tasks || a.tag.localeCompare(b.tag));
}

// ─── 批量处置 ────────────────────────────────────────────────────────────────

function applyToSelected(action: (task: Task) => void, message: (count: number) => string): void {
  const targets = partitionTasks().filter((task) => selected.has(task.id));
  if (targets.length === 0) return;
  for (const task of targets) action(task);
  selected.clear();
  dataChanged();
  toast(message(targets.length));
}

// ─── 标签改名 / 合并 ─────────────────────────────────────────────────────────

function renameTag(from: string, raw: string): void {
  const to = raw.trim().startsWith("#") ? raw.trim() : `#${raw.trim()}`;
  if (to === "#" || to === from) {
    toast("标签名没有变化");
    return;
  }

  let absorbed = 0;
  for (const task of partitionTasks()) {
    if (!task.tags.includes(from)) continue;
    task.tags = task.tags.filter((tag) => tag !== from);
    if (task.tags.includes(to)) absorbed += 1;
    else task.tags.push(to);
  }

  selectedTag = to;
  dataChanged();
  toast(
    absorbed > 0
      ? `已把「${from}」并入「${to}」· 其中 ${absorbed} 个任务本来就有该标签，已去重`
      : `已重命名「${from}」→「${to}」`,
  );
}

// ─── 表格 ────────────────────────────────────────────────────────────────────

function checkbox(on: boolean, onToggle: () => void): HTMLElement {
  const box = el("span", { class: `ckb ${on ? "on" : ""}` });
  box.addEventListener("click", (event) => {
    event.stopPropagation();
    onToggle();
  });
  return box;
}

/**
 * 导出用的三层结构：标签 → 任务 → 它的活动。
 *
 * 一条任务只归到它的**第一个**标签下：这是任务清单，同一条在文件里出现两遍会
 * 让人以为有两件事。（活动分析那边是按标签查活动，同一条进展天然会被多个标签
 * 命中，所以那边做了去重。）
 */
function exportGroups(list: Task[]): ExportGroup[] {
  const byTag = new Map<string, ExportGroup["tasks"]>();

  for (const task of list) {
    const tag = task.tags[0] ?? UNTAGGED;
    const bucket = byTag.get(tag) ?? [];
    bucket.push({
      title: task.title,
      status: STATUS_LABEL[task.status],
      // 活动时间倒序：最新的一条在最上面，和人看时间线的顺序一致
      rows: [...task.activities].sort((a, b) => b.at - a.at),
    });
    byTag.set(tag, bucket);
  }

  return [...byTag.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([tag, tasks]) => ({ tag, tasks }));
}

/**
 * 导出里的「截止」：必须是**绝对日期**。
 *
 * 表格上写「今天 15:00 / 昨天」是对的（界面上更好读），但那是**会变**的 ——
 * 今天导出的「今天」，明天打开就指错了日子，而文件是要存档、要发给别人的。
 * 日期本身在 `end`（数据），时刻只写在 `due`（文案）里：模型没有单独的截止时刻
 * 字段，所以 `HH:MM` 只在那里取，日期一律按 `end` 算。
 * 与 `data/markdown.ts` 的 `taskToMarkdown` 同一条规矩（见 time.ts 的
 * 「md 导出直接读 end + at」）—— 反过来按 `due.includes("今天")` 倒推日期的那种
 * 写法已经炸过一次（导出过 `⏰2026-明天`）。
 */
const exportDue = (task: Task): string => {
  if (!task.due) return "";
  const time = /\d{2}:\d{2}/.exec(task.due)?.[0] ?? task.at ?? "";
  return `${monthDayText(dayNumber(task.end))}${time ? ` ${time}` : ""}`;
};

function renderTable(): HTMLElement {
  const rows = tableRows();
  const pageCount = Math.max(1, Math.ceil(rows.length / pageSize));
  if (page >= pageCount) page = pageCount - 1;
  const start = page * pageSize;
  const slice = rows.slice(start, start + pageSize);

  const allOn = slice.length > 0 && slice.every((task) => selected.has(task.id));
  const headBox = checkbox(allOn, () => {
    if (allOn) for (const task of slice) selected.delete(task.id);
    else for (const task of slice) selected.add(task.id);
    // 勾选的只有这一页的行，重建表格最省事
    refreshTable?.();
  });

  const head = el("tr", {}, [
    el("th", {}, [headBox]),
    el("th", { text: "创建" }),
    el("th", { text: "任务内容" }),
    el("th", { text: "截止" }),
    el("th", { text: "进度" }),
    el("th", { text: "状态" }),
    el("th", { text: "标签" }),
    el("th", { text: "归档" }),
  ]);

  const body = el("tbody");
  for (const task of slice) {
    const row = el("tr", { class: "mrow" });

    const progress = el("div", { class: "mbar" }, [(() => {
      const fill = el("i");
      fill.style.width = `${task.progress}%`;
      return fill;
    })()]);

    const badge = el("span", { class: `st st-${task.status}`, text: STATUS_LABEL[task.status] });

    const tags = el("span", {}, task.tags.map((tag) => {
      const chip = el("span", { class: "tag", text: tag });
      chip.style.cssText += "cursor:pointer;margin-right:3px";
      chip.title = "在标签管理里选中";
      chip.addEventListener("click", (event) => {
        event.stopPropagation();
        selectedTag = tag;
        refreshTagCard?.();
      });
      return chip;
    }));

    row.append(
      el("td", {}, [
        checkbox(selected.has(task.id), () => {
          if (selected.has(task.id)) selected.delete(task.id);
          else selected.add(task.id);
          refreshTable?.();
        }),
      ]),
      el("td", { class: "mono dim", text: `${pad2(task.created[0])}-${pad2(task.created[1])}` }),
      el("td", {}, [el("div", { class: "tt", text: task.title })]),
      el("td", { class: "mono dim", text: task.due ?? "—" }),
      el("td", {}, [progress, el("span", { class: "mono dim", style: "margin-left:7px", text: `${task.progress}%` })]),
      el("td", {}, [badge]),
      el("td", {}, [tags]),
      el("td", {}, [
        task.archived
          ? el("span", { class: "arch-tag", text: "已归档" })
          : // 破折号就是「未归档」，但一个孤零零的符号没人看得懂 —— 补一句悬浮提示
            el("span", { class: "dim", text: "—", title: "未归档" }),
      ]),
    );

    row.title = "点击打开维护抽屉";
    row.addEventListener("click", () => jumpToTask(task.id));
    body.append(row);
  }

  if (slice.length === 0) {
    body.append(el("tr", {}, [el("td", { colspan: 8 }, [el("div", { class: "empty", text: "当前筛选下没有任务" })])]));
  }

  const table = el("table", {}, [el("thead", {}, [head]), body]);
  const wrap = el("div", { class: "tabwrap" }, [table]);

  const bar = pager({
    page,
    pageCount,
    total: rows.length,
    size: pageSize,
    onGo: (next) => {
      page = next;
      refreshTable?.();
    },
    // 每页几条：这是「一屏看多少」的**入口**，不是设置项 —— 它只影响眼前这张表
    onSize: (size) => {
      pageSize = size;
      page = 0;
      refreshTable?.();
    },
  });

  // .tablefill：表格吃剩余高度、分页器钉在卡内底部（见 pages.css 的一屏到底一节）
  return el("div", { class: "tablefill" }, [wrap, bar]);
}

// ─── 卡片 ────────────────────────────────────────────────────────────────────

/** 一组单选 chip：调用方给「当前值」，这里只负责高亮与回调（值本身由页面的状态持有）。 */
function filterChips<T extends string>(
  options: { value: T; label: string }[],
  current: T,
  onPick: (value: T) => void,
): HTMLElement {
  const root = el("div", { class: "chips" });
  for (const option of options) {
    const chip = el("button", {
      class: `chip ${option.value === current ? "on" : ""}`,
      type: "button",
      text: option.label,
    });
    chip.addEventListener("click", () => onPick(option.value));
    root.append(chip);
  }
  return root;
}

/**
 * 页头那枚**批量归档 / 取消归档**（2026-09-21 用户提的「在导出之后增加一个归档按钮即可」）。
 *
 * 为什么不放进批量条：批量条回答的是「我勾了这几条，要对它们做什么」；这一枚回答的是
 * 「**当前筛选下这一批，整体收走 / 放回来**」—— 两者的输入不同（勾选 vs 筛选条件），
 * 混在同一条里会让人以为必须先勾选。既然筛选已经把「哪一批」讲清楚了（状态 × 归档），
 * 这里只负责执行，**标签里不再重复写条数**。
 *
 * 动作与标签都跟着**归档档位**走：在看「未归档」时是「归档」，在看「已归档」时是
 * 「取消归档」—— 一次只可能做对该做的那件事（不会出现在已归档的一批上再按归档）。
 * 一条也筛不出来时给一句提示，不静默无反应。
 */
function archiveBatchButton(): HTMLElement {
  // 判据是「**不全是已归档**」而不是「正好是未归档」：点状态那几枚 chip 时
  // `archiveFilter` 会回到 `"all"`（两侧都算），而那一批的主体正是未归档的那批 ——
  // 写成 `=== "active"` 的话，**默认**进这一页（"all"）按钮上就挂着「取消归档」，
  // 与眼前这批对不上（也与上面那条说明相悖）
  const archiving = archiveFilter !== "archived";
  const button = el("button", {
    // 带个明确的类名：页头里还有「未归档 / 已归档」两枚 chip，按文字找会撞上它们
    class: "btn sm archive-batch",
    type: "button",
    text: archiving ? "归档" : "取消归档",
    title: archiving
      ? "把当前筛选下的任务收进归档（跨页）· 任务页不再列它们"
      : "把当前筛选下的任务放回未归档（跨页）",
  });
  button.addEventListener("click", async () => {
    const targets = tableRows();
    if (targets.length === 0) {
      toast("当前筛选下没有任务");
      return;
    }
    const ok = await confirmAction({
      title: `${archiving ? "归档" : "取消归档"}当前筛出的 ${targets.length} 条？`,
      detail: archiving
        ? "任务页不再列它们；这一页仍留着记录，切到「已归档」就能看见、也能放回来。"
        : "它们会重新出现在其余视图里；本次会话内不会再被自动归档收走。",
      confirmText: archiving ? `归档 ${targets.length} 条` : `恢复 ${targets.length} 条`,
    });
    if (!ok) return;
    for (const task of targets) {
      task.archived = archiving;
      // 恢复的走 keepActive：否则「完成后归档＝立即」下一次数据变更又把它们收走
      if (!archiving) keepActive(task.id);
    }
    // 勾选可能落在这批之外，清掉免得让人以为还选着
    selected.clear();
    dataChanged();
    toast(
      archiving
        ? `已归档 ${targets.length} 个任务 · 任务页不再列它们`
        : `已恢复 ${targets.length} 个任务`,
    );
  });
  return button;
}

function renderBatchBar(): HTMLElement | null {
  // 勾选了才出现。**批量归档**不在这里（见页头「导出」后面那枚）—— 它是「按筛选执行」的
  // 动作，与「你已经勾了哪几条」是两件事，混在同一条里会让人以为必须先勾选
  if (selected.size === 0) return null;

  const action = (button: HTMLElement): HTMLElement => {
    button.classList.add("btn", "sm");
    return button;
  };

  const done = action(el("button", { type: "button", text: "标记完成" }));
  done.addEventListener("click", () =>
    applyToSelected(
      (task) => setTaskStatus(task, "done"),
      (count) => `已把 ${count} 个任务标记为完成`,
    ),
  );

  const archive = action(el("button", { type: "button", text: "归档" }));
  archive.addEventListener("click", () =>
    applyToSelected((task) => {
      task.archived = true;
    }, (count) => `已归档 ${count} 个任务 · 其余视图不再显示`),
  );

  const restore = action(el("button", { type: "button", text: "取消归档" }));
  restore.addEventListener("click", () =>
    applyToSelected((task) => {
      task.archived = false;
      // 手动恢复的，本次会话里自动归档不再碰 —— 否则下次数据一变更它就又消失了
      keepActive(task.id);
    }, (count) => `已恢复 ${count} 个任务`),
  );

  const remove = action(el("button", { class: "btn sm danger", type: "button", text: "删除" }));
  remove.addEventListener("click", async () => {
    const count = selected.size;
    const ids = new Set(selected);
    const ok = await confirmAction({
      title: `删除选中的 ${count} 个任务？`,
      detail: "任务和它们名下的活动时间线会一并移除，删除后无法恢复。这里也能勾到已归档任务。",
      confirmText: `删除 ${count} 个`,
    });
    if (!ok) return;

    // 这一处是**写**：按 id 从真数组里删，所以用的是 `TASKS` 而不是 `partitionTasks()`。
    // 选中的 id 全来自本页表格（表格已经分区过滤过），不需要再筛一遍；
    // 反过来拿 `partitionTasks()` 的结果去 splice 会删错下标。
    for (let index = TASKS.length - 1; index >= 0; index -= 1) {
      if (ids.has(TASKS[index].id)) TASKS.splice(index, 1);
    }
    selected.clear();
    dataChanged();
    toast(`已删除 ${count} 个任务`);
  });

  const clear = action(el("button", { type: "button", text: "取消选择" }));
  clear.addEventListener("click", () => {
    selected.clear();
    refreshTable?.();
  });

  return el("div", { class: "batchbar" }, [
    `已选 ${selected.size} 项`,
    el("span", { class: "grow" }),
    done,
    archive,
    restore,
    remove,
    clear,
  ]);
}

function renderTagCard(): HTMLElement {
  const search = el("input", { placeholder: "搜索标签…" });
  search.value = tagQuery;
  search.addEventListener("input", () => {
    tagQuery = search.value;
    refreshTagList();
  });

  // .taglist：标签多到装不下时在中间这一块滚，上面的搜索框与下面的编辑区留在原地
  const list = el("div", { class: "taglist" });
  const editor = el("div");

  function refreshList(): void {
    const needle = tagQuery.trim().toLowerCase();
    const rows = tagRows().filter((row) => !needle || row.tag.toLowerCase().includes(needle));
    list.replaceChildren();

    if (rows.length === 0) {
      list.append(el("div", { class: "empty", text: "没有匹配的标签" }));
      return;
    }

    for (const row of rows) {
      const item = el("div", { class: `tagrow ${row.tag === selectedTag ? "on" : ""}` }, [
        el("span", { class: "tag", text: row.tag }),
        el("span", { class: "cnt", text: `${row.tasks} 任务 / ${row.activities} 活动` }),
      ]);
      item.addEventListener("click", () => {
        selectedTag = selectedTag === row.tag ? null : row.tag;
        refreshTagList();
      });
      list.append(item);
    }
  }

  function refreshEditor(): void {
    editor.replaceChildren();
    if (!selectedTag) {
      editor.append(el("div", { class: "dim", style: "font-size:11.5px", text: "选中标签后可重命名；改为已有名称即为合并。" }));
      return;
    }

    const input = el("input", { placeholder: "新标签名" });
    input.value = selectedTag;

    const submit = (): void => renameTag(selectedTag as string, input.value);
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") submit();
    });

    const apply = el("button", { class: "btn primary sm", type: "button", text: "改名" });
    apply.addEventListener("click", submit);

    const remove = el("button", { class: "btn danger sm", type: "button", text: "删除标签" });
    remove.addEventListener("click", async () => {
      const tag = selectedTag as string;
      const affected = partitionTasks().filter((task) => task.tags.includes(tag)).length;
      const ok = await confirmAction({
        title: `从 ${affected} 个任务上移除「${tag}」？`,
        detail: "标签本身会被删掉，任务不动。这个操作撤销不了。",
        confirmText: "移除标签",
      });
      if (!ok) return;

      let touched = 0;
      for (const task of partitionTasks()) {
        if (!task.tags.includes(tag)) continue;
        task.tags = task.tags.filter((item) => item !== tag);
        touched += 1;
      }
      selectedTag = null;
      dataChanged();
      toast(`已从 ${touched} 个任务上移除「${tag}」`);
    });

    editor.append(
      el("div", { class: "kvrow" }, [
        el("span", { class: "k", text: "当前" }),
        el("span", { class: "v" }, [el("span", { class: "tag", text: selectedTag })]),
      ]),
      el("div", { class: "tl-compose", style: "margin-top:6px" }, [input, apply]),
      el("div", { style: "margin-top:8px" }, [remove]),
    );
  }

  function refreshTagList(): void {
    // 选中的标签可能已经不在这一批里了（换了分区，或最后一条带它的任务改了）——
    // 那种情况下编辑区还开着，就是在「改一个这里根本没有的标签」
    if (selectedTag && !tagRows().some((row) => row.tag === selectedTag)) selectedTag = null;
    refreshList();
    refreshEditor();
  }

  refreshTagList();
  refreshTagCard = refreshTagList;

  return el("div", { class: "card" }, [
    el("div", { class: "card-h" }, [
      el("span", { class: "t", text: "标签管理" }),
      // 操作说明（改名 / 合并）在下面的编辑区里写一次就够，卡头这句是重复的
      el("span", { class: "d", text: "重命名与合并" }),
    ]),
    el("div", { class: "card-b" }, [
      el("div", { class: "searchbox", style: "margin-bottom:8px" }, [search]),
      list,
      el("div", { style: "margin-top:10px" }, [editor]),
    ]),
  ]);
}

// ─── 挂载 ────────────────────────────────────────────────────────────────────

export function mount(host: HTMLElement): void {
  const tableCard = el("div", { class: "card" });

  // ── 迁入 / 导出 ───────────────────────────────────────────────────────────
  // 「导入 .md」曾在 2026-09-17 撤掉：那时导出改成了给人看的清单（标签 → 任务 →
  // 活动三层），本来就回不来。现在「数据迁入」回来了，但导的**不是**那种清单，而是
  // **任务行写法**的文件 —— 也就是 `tadado-activity-import` skill 里那支转换工具产出的东西，
  // 是迁移旧数据的通道。
  //
  // 放在这一页而不是任务页页头：一进一出是同一类动作（这页本来就有「导出 ▾」），
  // 而页头的位置该留给每天都用的「＋ 新建任务」。
  const importBtn = el("button", { class: "btn", type: "button", text: "数据迁入" });
  importBtn.addEventListener("click", openImportDialog);

  // 导出跟着**当前筛选**走：表格上摆着状态与归档两个筛选，导出的就该是眼前这批，
  // 而不是「这个分区全部」—— 后者会让人以为筛选压根没生效。
  const exportBtn = exportButton({
    table: () => {
      const list = tableRows();
      return {
        // 与活动分析的导出**同一套三层结构**（标签 → 任务 → 活动），生成逻辑也共用
        // data/export.ts 的 groupedText。以前这里是 md 任务行（`- [ ] 标题 #标签`），
        // 那是为了让文件能导回来；导入在 2026-09-17 撤了，这个约束也就没了 ——
        // 两份导出统一之后，用户不用再记「哪个页面给的是哪种格式」
        text: {
          md: groupedText(exportGroups(list), "md"),
          txt: groupedText(exportGroups(list), "txt"),
        },
        head: ["#", "创建", "任务内容", "截止", "进度", "状态", "标签", "归档"],
        rows: list.map((task, index) => [
          String(index + 1),
          `${pad2(task.created[0])}-${pad2(task.created[1])}`,
          task.title,
          exportDue(task),
          `${task.progress}%`,
          STATUS_LABEL[task.status],
          task.tags.join(" "),
          task.archived ? "已归档" : "",
        ]),
      };
    },
    baseName: () => `tadado2-${activePartitionId()}-${isoDay(TODAY)}`,
    countText: () => `${tableRows().length} 条任务`,
    blocked: () => (tableRows().length === 0 ? "当前筛选下没有任务可导出" : ""),
  });

  const render = (): void => {
    const batch = renderBatchBar();
    tableCard.replaceChildren(
      el("div", { class: "card-h" }, [
        el("span", { class: "t", text: "任务表格" }),
        el("span", { class: "d", text: `${pageSize} 条/页 · 行点击打开维护抽屉` }),
        el("span", { class: "grow" }),
        // **一条**单选：全部状态 / 逾期 / 待办 / 进行中 / 已完成 / 未归档 / 已归档
        // （每一枚 = 一个视图，见 VIEW_OPTIONS 的说明）
        filterChips(VIEW_OPTIONS, viewOf(), (value) => {
          applyView(value);
          refreshTable?.();
        }),
        importBtn,
        exportBtn,
        // 「导出」之后的批量归档按钮（见 archiveBatchButton 的说明）。放在 render 里现建：
        // 它的标签跟着**归档档位**走，档位一换就得跟着换
        archiveBatchButton(),
      ]),
      el("div", { class: "card-b" }, [...(batch ? [batch] : []), renderTable()]),
    );

    // 标签卡跟着一起重建。它和表格是**同一份数据（本分区）的两种看法**，但它的取数
    // 原来只在 mount 时算过一次 —— 于是换了分区之后，表格空了、标签卡还列着上个分区的
    // 标签（同一个「分区没隔离干净」的坑，只是换了个入口）。
    refreshTagCard?.();
  };

  const root = el("div", { class: "split-manage" }, [tableCard, renderTagCard()]);
  host.append(root);

  refreshTable = render;
  render();
  onDataChange(render);

  // 从总览的「归档」卡切进来时，把筛选复位成「已归档」。页面是**常驻**的、切回来不会
  // 自己重画，所以得在这儿看一眼有没有请求（与任务页消费请求同一形状）。
  // 一次跳转只表达一个意图：状态与页码复位、勾选清掉。标签卡那套（搜索词 / 选中项）是
  // **标签管理**的口子，不影响表格列哪些行，不动它。
  subscribePages((id) => {
    if (id !== "manage") return;
    if (!consumeArchivedRequest()) {
      // 普通切页：重画一遍 —— 别的页面改过数据、或这一页上次是隐藏着画的
      render();
      return;
    }
    archiveFilter = "archived";
    statusFilter = "all";
    selected.clear();
    page = 0;
    render();
  });
}
