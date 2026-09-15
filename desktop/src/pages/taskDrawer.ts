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

import { taskToMarkdown } from "../data/markdown";
import { byId } from "../data/mock";
import { dataChanged, onDataChange } from "../data/store";
import type { Activity, Task, TaskStatus } from "../data/types";
import { el } from "../shell/dom";
import { dropdown } from "../shell/menu";
import { toast } from "../shell/toast";
import {
  DAY_MS,
  STATUS_LABEL,
  TODAY,
  URGENCY_LABEL,
  dayNumber,
  monthDayText,
  pad2,
  removeTask,
  statusVar,
  todayMonthDay,
} from "./shared";

/** 天数 → [月, 日]，和 dayNumber 互逆。 */
const monthDayOf = (day: number): [number, number] => {
  const date = new Date(day * DAY_MS);
  return [date.getUTCMonth() + 1, date.getUTCDate()];
};

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
  title: HTMLInputElement;
  tags: HTMLInputElement;
  due: HTMLInputElement;
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

  // 正在编辑的那个框不回写：`change` 之前模型还是旧的，
  // 此时若被别处的 dataChanged 带着重画一遍，用户敲到一半的字就没了
  if (document.activeElement !== drawer.title) drawer.title.value = task.title;
  if (document.activeElement !== drawer.tags) drawer.tags.value = task.tags.join(" ");

  // 日期框给的是 yyyy-mm-dd。年份锚在 2026（种子数据就是按 2026 写的），
  // 没有截止时留空 —— 填今天会让人以为这条任务定在今天结束。
  if (document.activeElement !== drawer.due) {
    drawer.due.value = task.due ? `2026-${monthDayText(dayNumber(task.end))}` : "";
  }
  drawer.created.textContent = `创建于 ${pad2(task.created[0])}-${pad2(task.created[1])}`;

  drawer.progressText.textContent = `${task.progress}%`;
  drawer.progressRange.value = String(task.progress);

  drawer.statusPick.setValue(task.status);
  drawer.urgencyPick.setValue(String(task.urgency) as "0" | "1" | "2" | "3");
  drawer.repeat.textContent = task.repeat || "无循环";

  // 序列化只此一份（data/markdown.ts）—— 抽屉里这行和「导出 .md」必须是同一个
  // 方言，否则导出去的东西和这里看到的不一样
  drawer.markdown.value = taskToMarkdown(task);
  renderTimeline(task);
}

function build(): Drawer {
  const badge = el("span", { class: "st" });

  // 标题、标签、截止曾经全是只读节点：改不动的「维护抽屉」不是维护抽屉 ——
  // 建任务时手滑打错一个字，那条任务就永远错着。这里都换成可编辑控件。
  const title = el("input", { class: "dr-title", spellcheck: "false" });
  title.addEventListener("change", () => {
    if (!current) return;
    const next = title.value.trim();
    // 空标题不许存：时间轴上一条没有名字的色条等于不知道它是谁
    if (!next) {
      title.value = current.title;
      toast("标题不能为空");
      return;
    }
    current.title = next;
    dataChanged();
    toast(`标题已改为「${next}」`);
  });

  const tags = el("input", {
    class: "dr-tags",
    spellcheck: "false",
    placeholder: "标签，空格分隔，如 #后端 #紧急",
  });
  tags.addEventListener("change", () => {
    if (!current) return;
    const next = [...tags.value.matchAll(/#[^\s#]+/g)].map((match) => match[0]);
    current.tags = next;
    dataChanged();
    toast(next.length > 0 ? `标签已改为 ${next.join(" ")}` : "已清空标签");
  });

  const due = el("input", { type: "date", class: "dr-due" });
  /** 截止落在哪一天：写 due 文案的同时必须同步 end —— 时间轴是按 end 画的。 */
  const applyDue = (day: number | null): void => {
    if (!current) return;
    if (day === null) {
      current.due = null;
      current.at = null;
      current.end = todayMonthDay();
      dataChanged();
      toast("已清除截止");
      return;
    }
    const monthDay = monthDayOf(day);
    current.due = monthDayText(day);
    current.at = null;
    current.end = monthDay;
    dataChanged();
    toast(`截止已设为 ${monthDayText(day)}`);
  };

  // 监听 input 而不是 change：从日期面板里选一个日期派发的就是 input，
  // change 要等到失焦才来 —— 选完还得点一下别处才生效，看着像坏了
  due.addEventListener("input", () => {
    if (!due.value) return;
    // <input type="date"> 给的是 yyyy-mm-dd，按 UTC 解析后换回「天数」，
    // 与 dayNumber / monthDayText 是同一套换算
    applyDue(Math.floor(Date.parse(`${due.value}T00:00:00Z`) / DAY_MS));
  });

  // 快捷档位。原版是「6 选项弹窗」，这里给三个最常用 + 清除就够了 ——
  // 「下周一」「本周五」这种要先想一下再点的，直接开日期选择器更省事。
  const quickRow = el("div", { class: "due-quick" }, [
    ["今天", 0],
    ["明天", 1],
    ["下周", 7],
  ].map(([label, offset]) => {
    const chip = el("button", { class: "chip", type: "button", text: label as string });
    chip.addEventListener("click", () => applyDue(TODAY + (offset as number)));
    return chip;
  }));
  const clearDue = el("button", { class: "chip", type: "button", text: "清除" });
  clearDue.addEventListener("click", () => applyDue(null));
  quickRow.append(clearDue);

  const created = el("span", { class: "mono dim" });

  const close = el("button", { class: "icon-btn", title: "关闭 (Esc)", html: CLOSE_ICON });
  close.addEventListener("click", closeTask);

  const head = el("div", { class: "dr-h" }, [
    badge,
    title,
    close,
    tags,
    el("div", { class: "due-row" }, [due, quickRow, created]),
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
    // 删除（含二次确认）和任务页右键共用 shared.removeTask ——
    // 同一个动作在两处不该有不同的措辞和确认条件
    if (!(await removeTask(task))) return;
    closeTask();
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

// 别处改了数据（右键菜单里的标记完成、管理页的批量操作、逾期自动标记），
// 抽屉里显示的状态徽标、进度、循环也得跟着变 ——
// 否则抽屉一打开就是一张过期快照，改完还得关掉重开才看得见
onDataChange(() => {
  if (current && drawer?.root.classList.contains("open")) paint(current);
});

// Esc 关闭。只在抽屉真的打开时拦，免得抢掉别的 Esc 用途。
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape" || !current) return;
  closeTask();
});
