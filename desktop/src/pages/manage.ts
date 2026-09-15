// ─────────────────────────────────────────────────────────────────────────────
// 任务管理页：可多选的表格 + 标签管理。
//
// 表格是唯一会显示**已归档**任务的视图（其余视图一律 activeTasks()），
// 所以这里用 TASKS 并给归档单独一列和一个筛选，而不是复用别处的取数。
//
// 「合并」不是一个独立按钮：把 A 改名为一个已经存在的 B，语义上就是合并。
// 单独做一个合并按钮反而要引入「再选第二个标签」的两段式交互，
// 而结果和改名完全一样。所以这里只做改名，并在目标已存在时把话说清楚。
// ─────────────────────────────────────────────────────────────────────────────

import { TASKS } from "../data/mock";
import { dataChanged, onDataChange } from "../data/store";
import type { Task, TaskStatus } from "../data/types";
import { el } from "../shell/dom";
import { confirmAction } from "../shell/confirm";
import { toast } from "../shell/toast";
import { jumpToTask } from "./focus";
import { STATUS_LABEL, dayNumber, pad2 } from "./shared";

const PAGE_SIZE = 12;

const STATUS_OPTIONS: { value: TaskStatus | "all"; label: string }[] = [
  { value: "all", label: "全部状态" },
  { value: "overdue", label: STATUS_LABEL.overdue },
  { value: "todo", label: STATUS_LABEL.todo },
  { value: "doing", label: STATUS_LABEL.doing },
  { value: "done", label: STATUS_LABEL.done },
];

const ARCHIVE_OPTIONS: { value: "active" | "archived" | "all"; label: string }[] = [
  { value: "active", label: "未归档" },
  { value: "archived", label: "已归档" },
  { value: "all", label: "含归档" },
];

// ─── 页面状态 ────────────────────────────────────────────────────────────────

let statusFilter: TaskStatus | "all" = "all";
let archiveFilter: "active" | "archived" | "all" = "active";
let page = 0;
let selected = new Set<string>();
let tagQuery = "";
let selectedTag: string | null = null;

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
  return TASKS.filter((task) => {
    if (statusFilter !== "all" && task.status !== statusFilter) return false;
    if (archiveFilter === "active" && task.archived) return false;
    if (archiveFilter === "archived" && !task.archived) return false;
    return true;
  }).sort((a, b) => dayNumber(b.created) - dayNumber(a.created) || a.id.localeCompare(b.id));
}

function tagRows(): { tag: string; tasks: number; activities: number }[] {
  const counts = new Map<string, { tasks: number; activities: number }>();
  for (const task of TASKS) {
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
  const targets = TASKS.filter((task) => selected.has(task.id));
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
  for (const task of TASKS) {
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

function renderTable(): HTMLElement {
  const rows = tableRows();
  const pageCount = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  if (page >= pageCount) page = pageCount - 1;
  const start = page * PAGE_SIZE;
  const slice = rows.slice(start, start + PAGE_SIZE);

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
        task.archived ? el("span", { class: "arch-tag", text: "已归档" }) : el("span", { class: "dim", text: "—" }),
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

  const pager = el("div", { class: "pager" }, [
    el("span", {
      text: rows.length === 0 ? "共 0 条" : `第 ${start + 1}–${Math.min(start + PAGE_SIZE, rows.length)} 条 / 共 ${rows.length} 条`,
    }),
    (() => {
      const button = el("button", { class: "navbtn", type: "button", text: "◀" });
      button.addEventListener("click", () => {
        if (page === 0) return;
        page -= 1;
        refreshTable?.();
      });
      return button;
    })(),
    el("span", { class: "mono dim", text: `${page + 1} / ${pageCount}` }),
    (() => {
      const button = el("button", { class: "navbtn", type: "button", text: "▶" });
      button.addEventListener("click", () => {
        if (page >= pageCount - 1) return;
        page += 1;
        refreshTable?.();
      });
      return button;
    })(),
  ]);

  return el("div", {}, [wrap, pager]);
}

// ─── 卡片 ────────────────────────────────────────────────────────────────────

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

function renderBatchBar(): HTMLElement | null {
  if (selected.size === 0) return null;

  const action = (button: HTMLElement): HTMLElement => {
    button.classList.add("btn", "sm");
    return button;
  };

  const done = action(el("button", { type: "button", text: "标记完成" }));
  done.addEventListener("click", () =>
    applyToSelected(
      (task) => {
        task.status = "done";
        task.progress = 100;
      },
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

  const list = el("div");
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
      editor.append(el("div", { class: "dim", style: "font-size:11.5px", text: "选中一个标签后可改名；改成已有的名字即为合并。" }));
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
      const affected = TASKS.filter((task) => task.tags.includes(tag)).length;
      const ok = await confirmAction({
        title: `从 ${affected} 个任务上移除「${tag}」？`,
        detail: "标签本身会被删掉，任务不动。这个操作撤销不了。",
        confirmText: "移除标签",
      });
      if (!ok) return;

      let touched = 0;
      for (const task of TASKS) {
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
    refreshList();
    refreshEditor();
  }

  refreshTagList();
  refreshTagCard = refreshTagList;

  return el("div", { class: "card" }, [
    el("div", { class: "card-h" }, [
      el("span", { class: "t", text: "标签管理" }),
      el("span", { class: "d", text: "改成已有的名字即为合并" }),
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

  const render = (): void => {
    const batch = renderBatchBar();
    tableCard.replaceChildren(
      el("div", { class: "card-h" }, [
        el("span", { class: "t", text: "任务表格" }),
        el("span", { class: "d", text: `每页 ${PAGE_SIZE} 条 · 行点击打开维护抽屉` }),
        el("span", { class: "grow" }),
        filterChips(STATUS_OPTIONS, statusFilter, (value) => {
          statusFilter = value;
          page = 0;
          refreshTable?.();
        }),
        filterChips(ARCHIVE_OPTIONS, archiveFilter, (value) => {
          archiveFilter = value;
          page = 0;
          refreshTable?.();
        }),
      ]),
      el("div", { class: "card-b" }, [...(batch ? [batch] : []), renderTable()]),
    );
  };

  const root = el("div", { class: "split-manage" }, [tableCard, renderTagCard()]);
  host.append(root);

  refreshTable = render;
  render();
  onDataChange(render);
}
