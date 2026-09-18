// ─────────────────────────────────────────────────────────────────────────────
// 任务维护抽屉。
//
// 它是任务的编辑入口（DESIGN.md：单击选中 · 双击 / 右键打开 · Esc 关闭）。
//
// 这一版按「这个界面是本软件的核心」重排过，改掉的是四件说不通的事：
//
//   1. **任务定义与活动时间线之间没有边界**。两段东西平行铺着，中间只有一点间距，
//      读到一半分不清哪行是「这条任务是什么」、哪行是「它经历过什么」。现在分成
//      两个有标题、有边框的分区。
//   2. **时间只有一半**。列表上写着「⏰ 今天 15:00」，抽屉里却只有一个日期框，
//      时分根本没有地方改。现在开始与结束都用 shell/dateTime.ts 的同一个组件
//      （开始只到日期、结束带时分），排布也一致。
//   3. **进度只能拖**。滑杆适合「大概拖一下」，想让它是 65% 就得来回蹭 ——
//      旁边补一个能直接键入的数字框。
//   4. **底部「删除 / 保存」**。所有字段本来就是即时保存的，「保存」实际只做
//      「收起抽屉」；按钮的名字在骗人。两个都撤掉，关闭交给右上角的 X 与 Esc，
//      删除走列表行的右键菜单与任务管理页（两处都有二次确认）。
//
// 另外：活动时间线上人手写的记录（kind: log）现在可改可删，改过会标「已编辑」；
// 系统记录（创建 / 改状态 / 改进度）不给编辑入口。
//
// 它属于「页面层」而不是「外壳层」：抽屉的内容完全跟着任务域走，
// 外壳不该知道什么是「优先级」。
// ─────────────────────────────────────────────────────────────────────────────

import { parseTasks, taskToMarkdown } from "../data/markdown";
import { byId } from "../data/mock";
import { dataChanged, onDataChange } from "../data/store";
import type { Activity, Task, TaskStatus } from "../data/types";
import { el } from "../shell/dom";
import { panelClosed, panelOpened, registerPanel } from "../shell/panels";
import { subscribePages } from "../shell/router";
import { toast } from "../shell/toast";
import { STATUS_LABEL, nowStamp, pad2, stampText, statusVar } from "./shared";
import { taskForm } from "./taskForm";

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
  /** 头部的任务名（只读展示）。真正可编辑的那个在表单里 —— 一个字段一处输入。 */
  name: HTMLElement;
  created: HTMLElement;
  form: ReturnType<typeof taskForm>;
  timeline: HTMLElement;
  timelineCount: HTMLElement;
  composer: HTMLInputElement;
  markdown: HTMLTextAreaElement;
  /** 重画 md 预览。 */
  mdSync: () => void;
}

let drawer: Drawer | null = null;
let current: Task | null = null;

/** 时间线上人手写的那一类记录。只有它能改能删（见 types.ts）。 */
type LogActivity = Extract<Activity, { kind: "log" }>;

// ─── 时间线 ──────────────────────────────────────────────────────────────────

/** 一条记录右侧的操作（只有人手写的那些才有）。 */
function entryOps(
  task: Task,
  index: number,
  activity: LogActivity,
): HTMLElement {
  const edit = el("button", { class: "tl-op", type: "button", text: "编辑" });
  const remove = el("button", { class: "tl-op danger", type: "button", text: "删除" });
  const row = el("div", { class: "tl-ops" }, [edit, remove]);

  edit.addEventListener("click", () => startEdit(task, index, activity));
  remove.addEventListener("click", () => {
    task.activities.splice(index, 1);
    dataChanged();
    toast("已删除这条记录");
  });

  return row;
}

/**
 * 就地改一条记录。
 *
 * 不改时间戳：这条记录写的还是当时发生的事，只是措辞改了 —— 把时间刷成「现在」
 * 会让时间线开始说谎。改过之后标一个「已编辑」，读者知道它被动过。
 */
function startEdit(task: Task, index: number, activity: LogActivity): void {
  if (!drawer) return;
  const entry = drawer.timeline.children[index];
  const card = entry?.querySelector<HTMLElement>(".tl-card");
  if (!card) return;

  const input = el("input", { class: "tl-edit", value: activity.text });
  const save = el("button", { class: "tl-op", type: "button", text: "保存" });
  const cancel = el("button", { class: "tl-op", type: "button", text: "取消" });

  const commit = (): void => {
    const next = input.value.trim();
    if (!next) {
      toast("内容不能为空");
      input.focus();
      return;
    }
    activity.text = next;
    activity.edited = true;
    dataChanged();
    toast("已更新这条记录");
  };

  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      commit();
    }
    if (event.key === "Escape") {
      // 这一层的 Esc 是「取消编辑」，不该顺手把整个抽屉关掉
      event.stopPropagation();
      renderTimeline(task);
    }
  });
  save.addEventListener("click", commit);
  cancel.addEventListener("click", () => renderTimeline(task));

  card.replaceChildren(el("div", { class: "t1" }, [input, el("div", { class: "tl-ops" }, [save, cancel])]));

  // 光标落在末尾：改错别字时不用再按一次 End
  input.focus();
  input.setSelectionRange(input.value.length, input.value.length);
}

function renderTimeline(task: Task): void {
  if (!drawer) return;
  // 收窄成局部常量：下面在 forEach 回调里用，模块级 let 的收窄传不进闭包
  const host = drawer;

  host.timeline.replaceChildren();
  host.timelineCount.textContent = `${task.activities.length} 条`;

  if (task.activities.length === 0) {
    drawer.timeline.append(
      el("div", { class: "dim", text: "暂无记录，可在下方添加第一条进展" }),
    );
    return;
  }

  task.activities.forEach((activity, index) => {
    const icon = el("div", {
      class: `tl-ico ${ICON_CLASS[activity.kind]}`,
      html: ICONS[activity.kind],
    });
    const rail = el("div", { class: "tl-rail" }, [icon, el("div", { class: "tl-line" })]);
    const card = el("div", { class: "tl-card" }, [
      el("div", { class: "t1" }, [
        el("span", { class: "tt", text: activity.text }),
        el("span", { class: "tm", text: stampText(activity.at) }),
        ...(activity.kind === "log" && activity.edited
          ? [el("span", { class: "tl-edited", text: "已编辑" })]
          : []),
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
    // 可改可删的只有人手写的那一类：系统记录是既成事实
    if (activity.kind === "log") card.append(entryOps(task, index, activity));

    host.timeline.append(el("div", { class: "tl-entry" }, [rail, card]));
  });
}

// ─── 重画 ────────────────────────────────────────────────────────────────────

function paint(task: Task): void {
  if (!drawer) return;

  drawer.badge.className = `st st-${task.status}`;
  drawer.badge.textContent = STATUS_LABEL[task.status];
  drawer.name.textContent = task.title;
  drawer.created.textContent = `创建于 ${pad2(task.created[0])}-${pad2(task.created[1])}`;

  drawer.form.paint(task);
  renderTimeline(task);

  // md 框同理：正在改 md 的人不该被这里的重画把内容和光标一起带走
  if (document.activeElement !== drawer.markdown) {
    drawer.markdown.value = taskToMarkdown(task);
    drawer.mdSync();
  }
}

// ─── 构建 ────────────────────────────────────────────────────────────────────

function build(task: Task): Drawer {
  const badge = el("span", { class: "st" });
  const name = el("div", { class: "dr-name" });
  const created = el("span", { class: "mono dim" });

  const close = el("button", {
    class: "dr-close",
    type: "button",
    title: "关闭 (Esc)",
    html: CLOSE_ICON,
  });
  close.addEventListener("click", closeTask);

  const head = el("div", { class: "dr-h" }, [
    el("div", { class: "dr-h1" }, [badge, name, close]),
    el("div", { class: "dr-sub" }, [created]),
  ]);

  // 任务定义：字段全部由 taskForm 提供，和「新建任务」对话框是同一份实现 ——
  // 两处各写一份的话，新建时能填的东西编辑时未必有，列表与编辑界面就会对不上
  const form = taskForm({
    task,
    onEdit: () => dataChanged(),
    onStatusChange: (next: TaskStatus) =>
      toast(`状态已改为「${STATUS_LABEL[next]}」· 全局视图已联动`),
  });

  const timeline = el("div", { class: "tl-list" });
  const timelineCount = el("span", { class: "dim mono" });

  // ── 记录新进展 ──
  const composer = el("input", { placeholder: "记录一条进展（回车保存）" });
  const send = el("button", { class: "tl-send", title: "保存", html: SEND_ICON });
  const appendActivity = (): void => {
    if (!current) return;
    const text = composer.value.trim();
    if (!text) return;
    current.activities.unshift({ at: nowStamp(), text, kind: "log" });
    composer.value = "";
    renderTimeline(current);
    dataChanged();
    // 「发送」本来就是保存 —— 以前这条已经落库了，只是没有任何反馈，
    // 让人以为还得再点一次什么才算存上
    toast("已保存到活动时间线");
  };
  send.addEventListener("click", appendActivity);
  composer.addEventListener("keydown", (event) => {
    if (event.key === "Enter") appendActivity();
  });

  // ── Markdown 源 ──
  const markdown = el("textarea", { class: "md", spellcheck: "false" });
  const mdPreview = el("div", { class: "md-prev" });
  const mdApply = el("button", { class: "btn sm", type: "button", text: "按 md 更新任务" });
  const mdReset = el("button", { class: "btn sm", type: "button", text: "还原" });

  /**
   * 把框里的 md 渲染成一眼能看完的一块。
   *
   * 状态**不**从 md 读：方言不承载状态（DESIGN.md，见 data/markdown.ts 表头），
   * 于是 `[x]` 在这里不生效，显示的仍是任务自己的状态。
   */
  const renderMdPreview = (): void => {
    const draft = parseTasks(markdown.value)[0];
    mdPreview.replaceChildren();

    if (!draft) {
      mdPreview.classList.add("bad");
      mdPreview.append(
        el("div", {
          class: "dim",
          text: "无法识别任务行，格式示例：- [ ] 标题 #标签 ⏰09-21 14:30 :: 40%",
        }),
      );
      return;
    }

    mdPreview.classList.remove("bad");
    const status = current?.status ?? "todo";
    mdPreview.append(
      el("div", { class: "mdp-1" }, [
        el("span", { class: `st st-${status}`, text: STATUS_LABEL[status] }),
        el("span", { class: "mdp-title", text: draft.title }),
      ]),
    );

    mdPreview.append(
      el("div", { class: "mdp-2" }, [
        ...draft.tags.map((tag) => el("span", { class: "tag", text: tag })),
        el("span", { class: "mdp-fact", text: draft.due ? `⏰ ${draft.due}` : "无截止" }),
        el("span", { class: "mdp-fact", text: `进度 ${draft.progress}%` }),
      ]),
    );
  };

  markdown.addEventListener("input", renderMdPreview);

  mdReset.addEventListener("click", () => {
    if (!current) return;
    markdown.value = taskToMarkdown(current);
    renderMdPreview();
  });

  mdApply.addEventListener("click", () => {
    if (!current) return;
    const draft = parseTasks(markdown.value)[0];
    if (!draft) {
      toast("这一行还认不出任务 —— 先照上面的写法检查一下");
      return;
    }

    current.title = draft.title;
    current.tags = draft.tags;
    current.progress = draft.progress;
    // start 不在方言里（md 只带一个截止日）。一律填今天会把跨天任务的起点抹平，
    // 所以起点、以及没写截止时的终点都照旧不动
    if (draft.due) {
      current.due = draft.due;
      current.at = draft.at;
      current.end = draft.end;
    } else {
      current.due = null;
      current.at = null;
    }

    dataChanged();
    paint(current);
    toast(`已按 md 更新「${draft.title}」· 状态保持「${STATUS_LABEL[current.status]}」`);
  });

  const markdownBlock = el("details", { class: "md-d" }, [
    el("summary", { text: "Markdown 源（规范数据源）" }),
    el("div", {
      class: "md-note dim",
      text: "修改后不会立即写入任务，需点击「按 md 更新任务」；状态不参与 md，写回时保留原值。",
    }),
    mdPreview,
    markdown,
    el("div", { class: "md-actions" }, [mdApply, mdReset]),
  ]);

  // 两个分区：上面「这条任务是什么」，下面「它经历过什么」。以前它们是平铺的
  // 两串字段与记录，中间没有任何边界。
  const body = el("div", { class: "dr-b" }, [
    el("section", { class: "dr-sec dr-def" }, [
      el("div", { class: "sec-h" }, [
        el("span", { class: "sec-t", text: "任务定义" }),
        el("span", { class: "dim", text: "这条任务是什么" }),
      ]),
      form.root,
    ]),
    el("section", { class: "dr-sec dr-tl" }, [
      el("div", { class: "sec-h" }, [
        el("span", { class: "sec-t", text: "活动时间线" }),
        el("span", { class: "dim", text: "这条任务经历过什么" }),
        el("span", { class: "grow" }),
        timelineCount,
      ]),
      timeline,
      el("div", { class: "tl-compose" }, [composer, send]),
    ]),
    el("section", { class: "dr-sec" }, [markdownBlock]),
  ]);

  // 没有页脚：删除与保存都撤了（见文件头注释）
  const root = el("aside", { class: "drawer", id: "task-drawer" }, [head, body]);

  return {
    root,
    badge,
    name,
    created,
    form,
    timeline,
    timelineCount,
    composer,
    markdown,
    mdSync: renderMdPreview,
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
    drawer = build(task);
    document.body.append(drawer.root);
  }

  current = task;
  paint(task);
  drawer.root.classList.add("open");
  panelOpened("task");
  // 新任务的时间线在下面，滚回顶部才看得到标题与进度
  drawer.root.querySelector<HTMLElement>(".dr-b")?.scrollTo({ top: 0 });

  for (const listener of openListeners) listener(task);
}

export function closeTask(): void {
  if (!drawer) return;
  drawer.root.classList.remove("open");
  current = null;
  panelClosed("task");
  for (const listener of openListeners) listener(null);
}

/** 同一个任务再双击一次就收起 —— 见 tasks.ts 的 dblclick。 */
export const isTaskOpen = (taskId: string): boolean =>
  current?.id === taskId && drawer?.root.classList.contains("open") === true;

export const openedTask = (): Task | null => current;

// 别处改了数据（右键菜单里的标记完成、管理页的批量操作、逾期自动标记），
// 抽屉里的徽标、字段、时间线也得跟着变 —— 否则抽屉一打开就是一张过期快照
onDataChange(() => {
  if (current && drawer?.root.classList.contains("open")) paint(current);
});

// Esc 关闭。只在抽屉真的打开时拦，免得抢掉别的 Esc 用途。
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape" || !current) return;
  closeTask();
});

// 与设置抽屉互斥：右侧只有一块地方（shell/panels.ts）
registerPanel("task", closeTask);

/**
 * 切页就收起。
 *
 * 抽屉里的字段与时间线讲的都是「这一页的这条任务」，翻到别的模块还挂着它，
 * 看上去就像是新页面里长出来的一层，也说不清它属于谁。
 *
 * 顺序上安全：从图谱双击节点走的是 focus.jumpToTask，它先 goPage 再 openTask，
 * 于是这里先收掉旧抽屉，随后新页面把新的打开。
 */
subscribePages(() => {
  if (current) closeTask();
});
