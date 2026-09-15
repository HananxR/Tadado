// ─────────────────────────────────────────────────────────────────────────────
// 任务维护抽屉。
//
// 它是任务的唯一编辑入口（DESIGN.md：单击选中 · 双击 / 右键打开 · 保存后自动
// 收起 · Esc 关闭）。节点结构写在原型里，这里在首次打开时建出来并常驻 ——
// 每次重建成百个节点会让滑出动画掉帧。
//
// 它属于「页面层」而不是「外壳层」：抽屉的内容完全跟着任务域走，
// 外壳不该知道什么是「紧迫度」。
// ─────────────────────────────────────────────────────────────────────────────

import { TASKS, byId } from "../data/mock";
import { dataChanged } from "../data/store";
import type { Activity, Task, TaskStatus } from "../data/types";
import { el } from "../shell/dom";
import { confirmAction } from "../shell/confirm";
import { dropdown } from "../shell/menu";
import { toast } from "../shell/toast";
import { STATUS_LABEL, URGENCY_LABEL, pad2, statusVar } from "./shared";

// ─── 图标 ────────────────────────────────────────────────────────────────────

const ICONS: Record<Activity["kind"], string> = {
  create:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>',
  status:
    '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M8.5 6.5l9 5.5-9 5.5z"/></svg>',
  progress:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M7 17L17 7M9 7h8v8"/></svg>',
  log: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>',
};

const ICON_CLASS: Record<Activity["kind"], string> = {
  create: "cr",
  status: "stdo",
  progress: "pr",
  log: "lg",
};

const CLOSE_ICON =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>';
const SEND_ICON =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M22 2L11 13M22 2l-7 20-4-9-9-4z"/></svg>';

// ─── 打开事件 ────────────────────────────────────────────────────────────────

type OpenListener = (task: Task | null) => void;

const openListeners = new Set<OpenListener>();

/** 订阅「抽屉打开/关闭了哪个任务」，供各页面同步选中态。 */
export function onTaskOpen(listener: OpenListener): () => void {
  openListeners.add(listener);
  return () => {
    openListeners.delete(listener);
  };
}

// ─── 节点 ────────────────────────────────────────────────────────────────────

interface Drawer {
  root: HTMLElement;
  badge: HTMLElement;
  title: HTMLElement;
  tags: HTMLElement;
  due: HTMLElement;
  created: HTMLElement;
  progressText: HTMLElement;
  progressRange: HTMLInputElement;
  statusPick: ReturnType<typeof dropdown<TaskStatus>>;
  urgencyPick: ReturnType<typeof dropdown<string>>;
  repeat: HTMLElement;
  timeline: HTMLElement;
  timelineCount: HTMLElement;
  composer: HTMLInputElement;
  markdown: HTMLTextAreaElement;
}

let drawer: Drawer | null = null;
let current: Task | null = null;

/** Markdown 源。真实实现里它才是规范数据源，其余字段都是解析结果。 */
function toMarkdown(task: Task): string {
  const box = task.status === "done" ? "x" : task.status === "doing" ? "~" : " ";

  let due = "";
  if (task.due) {
    if (task.due.includes("今天")) due = ` ⏰2026-09-12 ${task.at ?? ""}`;
    else if (task.due.includes("昨天")) due = " ⏰2026-09-11";
    else due = ` ⏰2026-${task.due}`;
  }

  const progress = task.progress ? ` :: ${task.progress}%` : "";
  const repeat = task.repeat ? ` ${task.repeat}` : "";
  return `- [${box}] ${task.title} ${task.tags.join(" ")}${due}${progress}${repeat}`;
}

function renderTimeline(task: Task): void {
  if (!drawer) return;

  drawer.timeline.replaceChildren();
  drawer.timelineCount.textContent = `${task.activities.length} 条`;

  if (task.activities.length === 0) {
    drawer.timeline.append(
      el("div", { class: "dim", text: "暂无活动记录 — 在下方输入第一条进展" }),
    );
    return;
  }

  for (const activity of task.activities) {
    const icon = el("div", {
      class: `tl-ico ${ICON_CLASS[activity.kind]}`,
      html: ICONS[activity.kind],
    });
    const rail = el("div", { class: "tl-rail" }, [icon, el("div", { class: "tl-line" })]);
    const card = el("div", { class: "tl-card" }, [
      el("div", { class: "t1" }, [
        el("span", { class: "tt", text: activity.text }),
        el("span", { class: "tm", text: activity.at }),
      ]),
    ]);

    const detail = el("div", { class: "t2" });
    if (activity.kind === "progress") {
      const oldBar = el("i", { class: "o" });
      oldBar.style.width = `${activity.from}%`;
      const newBar = el("i", { class: "n" });
      newBar.style.left = `${activity.from}%`;
      newBar.style.width = `${activity.to - activity.from}%`;

      detail.append(
        el("span", { class: "tl-dbar" }, [oldBar, newBar]),
        el("span", { class: "tl-note" }, [
          `${activity.from}% → `,
          el("b", { text: `${activity.to}%` }),
        ]),
      );
    } else if (activity.kind === "status") {
      detail.append(
        el("span", { class: "tl-note" }, [
          `${STATUS_LABEL[activity.from]} → `,
          el("b", { text: STATUS_LABEL[activity.to], style: `color:${statusVar(activity.to)}` }),
        ]),
      );
    }

    if (detail.childElementCount > 0) card.append(detail);
    drawer.timeline.append(el("div", { class: "tl-entry" }, [rail, card]));
  }
}

function paint(task: Task): void {
  if (!drawer) return;

  drawer.badge.className = `st st-${task.status}`;
  drawer.badge.textContent = STATUS_LABEL[task.status];

  drawer.title.textContent = task.title;

  drawer.tags.replaceChildren(
    ...task.tags.map((tag) => el("span", { class: "tag", text: tag })),
  );

  // 截止展示把相对词落回具体日期：抽屉里是「查证」的地方，不适合再说「今天」
  const due = task.due
    ? `⏰ ${task.due.replace("今天", "09-12").replace("昨天", "09-11")}`
    : "无截止";
  drawer.due.textContent = due;
  drawer.created.textContent = `创建于 ${pad2(task.created[0])}-${pad2(task.created[1])}`;

  drawer.progressText.textContent = `${task.progress}%`;
  drawer.progressRange.value = String(task.progress);

  drawer.statusPick.setValue(task.status);
  drawer.urgencyPick.setValue(String(task.urgency) as "0" | "1" | "2" | "3");
  drawer.repeat.textContent = task.repeat || "无循环";

  drawer.markdown.value = toMarkdown(task);
  renderTimeline(task);
}

function build(): Drawer {
  const badge = el("span", { class: "st" });
  const title = el("span", { class: "t" });
  const tags = el("div", { class: "tags" });
  const due = el("span", { class: "mono" });
  const created = el("span", { class: "mono dim" });

  const close = el("button", { class: "icon-btn", title: "关闭 (Esc)", html: CLOSE_ICON });
  close.addEventListener("click", closeTask);

  const head = el("div", { class: "dr-h" }, [
    badge,
    title,
    close,
    tags,
    el("div", { class: "due-row" }, [due, created]),
  ]);

  // ── 进度 ──
  const progressText = el("span", { class: "pct", text: "0%" });
  const progressRange = el("input", { type: "range", class: "range", min: "0", max: "100" });
  progressRange.addEventListener("input", () => {
    if (!current) return;
    current.progress = Number(progressRange.value);
    progressText.textContent = `${current.progress}%`;
    dataChanged();
  });

  // ── 快捷变更 ──
  const statusPick = dropdown<TaskStatus>({
    items: [
      { value: "todo", label: STATUS_LABEL.todo },
      { value: "doing", label: STATUS_LABEL.doing },
      { value: "done", label: STATUS_LABEL.done },
      { value: "overdue", label: "逾期（仅系统标记）" },
    ],
    value: "todo",
    onPick: (status) => {
      if (!current) return;
      current.status = status;
      if (status === "done") current.progress = 100;
      paint(current);
      dataChanged();
      toast(`状态已改为「${STATUS_LABEL[status]}」· 全局视图已联动`);
    },
  });

  const urgencyPick = dropdown<string>({
    items: URGENCY_LABEL.map((label, index) => ({ value: String(index), label })),
    value: "2",
    onPick: (value) => {
      if (!current) return;
      current.urgency = Number(value) as Task["urgency"];
      dataChanged();
      toast(`优先级已改为「${URGENCY_LABEL[Number(value)]}」`);
    },
  });

  const repeat = el("span", { class: "chip" });

  const quick = el("div", { class: "dr-sec", style: "display:none" });
  const timeline = el("div", { class: "tl-list" });
  const timelineCount = el("span", { class: "dim mono" });

  // ── 记录新进展 ──
  const composer = el("input", { placeholder: "记录新进展…（回车追加）" });
  const send = el("button", { class: "tl-send", title: "发送", html: SEND_ICON });
  const appendActivity = (): void => {
    if (!current) return;
    const text = composer.value.trim();
    if (!text) return;
    current.activities.unshift({ at: "刚刚", text, kind: "log" });
    composer.value = "";
    renderTimeline(current);
    dataChanged();
    toast(`已追加进展「${text}」`);
  };
  send.addEventListener("click", appendActivity);
  composer.addEventListener("keydown", (event) => {
    if (event.key === "Enter") appendActivity();
  });

  // ── Markdown 源 ──
  const markdown = el("textarea", { class: "md", spellcheck: "false" });
  const markdownBlock = el("details", { class: "md-d" }, [
    el("summary", { text: "Markdown 源（规范数据源）" }),
    markdown,
  ]);

  const body = el("div", { class: "dr-b" }, [
    el("div", { class: "dr-sec" }, [
      el("div", { class: "lbl" }, [
        el("span", { text: "进度" }),
        el("span", { class: "grow" }),
        progressText,
      ]),
      progressRange,
    ]),
    el("div", { class: "dr-sec" }, [
      el("div", { class: "lbl", text: "快捷变更" }),
      el("div", { class: "kvrow" }, [
        el("span", { class: "k", text: "状态" }),
        el("span", { class: "v" }, [statusPick.root]),
      ]),
      el("div", { class: "kvrow" }, [
        el("span", { class: "k", text: "优先级" }),
        el("span", { class: "v" }, [urgencyPick.root]),
      ]),
      el("div", { class: "kvrow" }, [
        el("span", { class: "k", text: "循环" }),
        el("span", { class: "v" }, [repeat]),
      ]),
      quick,
    ]),
    el("div", { class: "dr-sec" }, [
      el("div", { class: "lbl" }, [
        el("span", { text: "活动时间线" }),
        el("span", { class: "grow" }),
        timelineCount,
      ]),
      timeline,
      el("div", { class: "tl-compose" }, [composer, send]),
    ]),
    el("div", { class: "dr-sec" }, [markdownBlock]),
  ]);

  const remove = el("button", { class: "btn danger", text: "删除" });
  remove.addEventListener("click", async () => {
    if (!current) return;
    const task = current;
    const ok = await confirmAction({
      title: "删除这个任务？",
      detail: `「${task.title}」和它名下的活动时间线会一并移除，删除后无法恢复。`,
      confirmText: "删除任务",
    });
    if (!ok) return;

    const index = TASKS.findIndex((item) => item.id === task.id);
    if (index >= 0) TASKS.splice(index, 1);
    closeTask();
    dataChanged();
    toast(`已删除「${task.title}」`);
  });

  const save = el("button", { class: "btn primary", text: "保存" });
  save.addEventListener("click", () => {
    if (!current) return;
    const name = current.title;
    closeTask();
    dataChanged();
    toast(`已保存「${name}」· 抽屉已自动收起`);
  });

  const root = el("aside", { class: "drawer", id: "task-drawer" }, [
    head,
    body,
    el("div", { class: "dr-f" }, [remove, save]),
  ]);

  return {
    root,
    badge,
    title,
    tags,
    due,
    created,
    progressText,
    progressRange,
    statusPick,
    urgencyPick,
    repeat,
    timeline,
    timelineCount,
    composer,
    markdown,
  };
}

// ─── 对外接口 ────────────────────────────────────────────────────────────────

export function openTask(taskId: string): void {
  const task = byId(taskId);
  if (!task) {
    toast("任务不存在");
    return;
  }

  if (!drawer) {
    drawer = build();
    document.body.append(drawer.root);
  }

  current = task;
  paint(task);
  drawer.root.classList.add("open");
  // 新任务的活动时间线在下面、MD 源更下面，滚回顶部才看得到标题和进度
  drawer.root.querySelector<HTMLElement>(".dr-b")?.scrollTo({ top: 0 });

  for (const listener of openListeners) listener(task);
}

export function closeTask(): void {
  if (!drawer) return;
  drawer.root.classList.remove("open");
  current = null;
  for (const listener of openListeners) listener(null);
}

export const openedTask = (): Task | null => current;

// Esc 关闭。只在抽屉真的打开时拦，免得抢掉别的 Esc 用途。
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape" || !current) return;
  closeTask();
});
