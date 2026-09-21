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
// 系统记录（创建 / 改状态 / 改进度 / 改优先级）不给编辑入口 —— 它们是既成事实。
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
import {
  STATUS_LABEL,
  URGENCY_COLORS,
  URGENCY_LABEL,
  nowStamp,
  pad2,
  stampText,
  statusVar,
} from "./shared";
import { progressControl, taskForm, type ProgressActivity, type ProgressControl } from "./taskForm";

// ─── 图标 ────────────────────────────────────────────────────────────────────

const ICONS: Record<Activity["kind"], string> = {
  create:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>',
  status:
    '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M8.5 6.5l9 5.5-9 5.5z"/></svg>',
  progress:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M7 17L17 7M9 7h8v8"/></svg>',
  urgency:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5M5 12l7-7 7 7"/></svg>',
  log: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>',
};

const ICON_CLASS: Record<Activity["kind"], string> = {
  create: "cr",
  status: "stdo",
  progress: "pr",
  urgency: "ur",
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
  /** 进度控件（在活动时间线里，不在表单里）。 */
  progress: ProgressControl;
  timeline: HTMLElement;
  timelineCount: HTMLElement;
  composer: HTMLInputElement;
  markdown: HTMLTextAreaElement;
  /** 重画 md 预览。 */
  mdSync: () => void;
  /** 换了一条任务：丢掉进度控件里没提交的草稿（它属于上一条任务）。 */
  resetProgress: () => void;
}

/** 写一条新进展时的输入框提示。 */
const COMPOSE_HINT = "记录一条进展（回车保存）";

let drawer: Drawer | null = null;
let current: Task | null = null;

/** 时间线上人手写的那一类记录。 */
type LogActivity = Extract<Activity, { kind: "log" }>;

// ─── 时间线 ──────────────────────────────────────────────────────────────────

/**
 * 一条记录右侧的操作（编辑 / 删除）。
 *
 * 可改可删的有两类：人手写的 `log`，以及**进度记录**（2026-09-20 用户报的第二个 bug：
 * 「保存好的进度」当时没有编辑入口 —— 带说明的进度记录正是这种情况，它长得像 log，
 * 却是 `kind: "progress"`）。其余的（创建 / 状态 / 优先级）仍不给入口：那是既成事实。
 */
function entryOps(
  task: Task,
  index: number,
  activity: LogActivity | ProgressActivity,
  /** 这一条自己的卡片。就地编辑时直接换它的内容 —— **不再按 DOM 下标找**：
   *  时间线是正序渲染的，下标跟数组下标刚好相反，照着下标找会改错另一条。 */
  card: HTMLElement,
): HTMLElement {
  const edit = el("button", { class: "tl-op", type: "button", text: "编辑" });
  const remove = el("button", { class: "tl-op danger", type: "button", text: "删除" });
  const row = el("div", { class: "tl-ops" }, [edit, remove]);

  edit.addEventListener("click", () => startEdit(task, index, activity, card));
  remove.addEventListener("click", () => {
    // 删掉的是**最新**那条进度记录时，任务的当前进度跟着退回它的起点 ——
    // 否则任务还停在一个已经不存在的记录上（时间线里也没有任何一条能解释这个数）
    const latestProgress = task.activities.findIndex((item) => item.kind === "progress");
    if (activity.kind === "progress" && latestProgress === index) {
      task.progress = activity.from;
    }
    task.activities.splice(index, 1);
    dataChanged();
    toast(activity.kind === "progress" ? "已删除这条进度记录" : "已删除这条记录");
  });

  return row;
}

/**
 * 一条进度记录能改到的上限：**后面那条（更新的）进度记录的 to**；它已经是最新的话到 100。
 *
 * 时间线是**单调**的：进度只往前挪。把一条老记录改到超过后来那条，页面上就会出现
 * 「倒着走」的进度（先 80、后 70），而两条记录都是「真的」—— 于是这条时间线不再能读。
 * 这就是用户说的「再次编辑的进度不能超过后面日志的进度」（2026-09-20）。
 */
function progressEditBound(task: Task, index: number): number {
  // activities 是**最新在前**的，所以「后面（更新的）」都在更小的下标里
  for (let j = index - 1; j >= 0; j -= 1) {
    const item = task.activities[j];
    if (item.kind === "progress") return item.to;
  }
  return 100;
}

/**
 * 就地改一条记录。
 *
 * 不改时间戳：这条记录写的还是当时发生的事，只是措辞（和进度值）改了 —— 把时间刷成
 * 「现在」会让时间线开始说谎。人手写的那类标一个「已编辑」，读者知道它被动过。
 */
function startEdit(
  task: Task,
  index: number,
  activity: LogActivity | ProgressActivity,
  card: HTMLElement,
): void {
  if (!drawer) return;

  const input = el("input", { class: "tl-edit", value: activity.text });
  const save = el("button", { class: "tl-op", type: "button", text: "保存" });
  const cancel = el("button", { class: "tl-op", type: "button", text: "取消" });

  // 进度记录还能改**值**（用户要求「保存好的进度允许被再次编辑」）
  const bound = activity.kind === "progress" ? progressEditBound(task, index) : 0;
  const value =
    activity.kind === "progress"
      ? el("input", {
          class: "pct-input",
          type: "number",
          min: "0",
          max: "100",
          value: String(activity.to),
          title:
            bound < 100
              ? `最多改到 ${bound}%（后面那条记录已经到 ${bound}%）`
              : "它是最新的一条 —— 改完它就是任务的当前进度",
        })
      : null;
  // 上界写在旁边，不用悬停才知道：改过头会被拦，先让人看见范围在哪
  const boundNote =
    activity.kind === "progress" && bound < 100
      ? el("span", { class: "dim", text: `≤ ${bound}%` })
      : null;

  const commit = (): void => {
    const next = input.value.trim();
    if (!next) {
      toast("内容不能为空");
      input.focus();
      return;
    }

    // 进度记录：说明和**值**一起改（用户要求「保存好的进度允许被再次编辑」）。
    // 写成整支 `if` + return 而不是 `&& value`：后面那段是 log 专用的（要标「已编辑」），
    // 而 `&& value` 收窄不掉 union —— 类型上剩下那段仍可能是 progress（TS2339）
    if (activity.kind === "progress") {
      const box = value;
      // 构造时数字框与 progress 记录同生同灭，这里只为类型收窄
      if (!box) return;
      const to = Math.max(0, Math.min(100, Math.round(Number(box.value))));
      if (Number.isNaN(to)) {
        toast("进度要填一个 0–100 的数");
        box.focus();
        return;
      }
      if (to < activity.from) {
        toast(`不能低于这条记录的起点 ${activity.from}%`);
        box.focus();
        return;
      }
      if (to > bound) {
        toast(`最多改到 ${bound}% —— 后面那条记录已经到 ${bound}%`);
        box.focus();
        return;
      }
      const changed = activity.to !== to;
      activity.to = to;
      activity.text = next;
      if (changed) {
        // 链条要接得上：后面那条记录的**起点**跟着挪，否则两条之间会缺一段（或重叠）
        const newer = task.activities.findIndex(
          (item, j) => j < index && item.kind === "progress",
        );
        const nextNewer = newer >= 0 ? task.activities[newer] : null;
        if (nextNewer?.kind === "progress") nextNewer.from = to;
        // 它自己就是最新那条 → 任务的当前进度就是它
        else task.progress = to;
      }
      dataChanged();
      toast("已更新这条进度记录");
      return;
    }

    activity.text = next;
    activity.edited = true;
    dataChanged();
    toast("已更新这条记录");
  };

  const onKey = (event: KeyboardEvent): void => {
    if (event.key === "Enter") {
      event.preventDefault();
      commit();
    }
    if (event.key === "Escape") {
      // 这一层的 Esc 是「取消编辑」，不该顺手把整个抽屉关掉
      event.stopPropagation();
      renderTimeline(task);
    }
  };
  input.addEventListener("keydown", onKey);
  value?.addEventListener("keydown", onKey);
  save.addEventListener("click", commit);
  cancel.addEventListener("click", () => renderTimeline(task));

  // **两行**：第一行整行给「说明」，第二行才是进度值与两个按钮。
  // 以前全挤在一行里，说明输入框只剩一百多像素 —— 用户的原话是「信息编辑区域太小了」
  card.replaceChildren(
    el("div", { class: "tl-edit-row" }, [input]),
    el("div", { class: "tl-edit-row" }, [
      ...(value
        ? [el("span", { class: "dim", text: "进度" }), value, ...(boundNote ? [boundNote] : [])]
        : []),
      el("div", { class: "tl-ops" }, [save, cancel]),
    ]),
  );

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

  // **正序（追加模式）**：最早的在上面，最新的贴着下面的输入框 —— 这本台账是往后写的，
  // 读到最底下正好接着「记录一条进展」（2026-09-20 用户提的：倒序读起来别扭）。
  // **存储顺序不动**：`activities` 仍然最新在前，导出、统计、以及「后面那条记录」
  // （进度编辑的上界）都按那个约定走，这里只是渲染时反着铺
  const ordered = task.activities.map((activity, index) => ({ activity, index })).reverse();

  for (const { activity, index } of ordered) {
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
    } else if (activity.kind === "urgency") {
      detail.append(
        el("span", { class: "tl-note" }, [
          `${URGENCY_LABEL[activity.from]} → `,
          el("b", {
            text: URGENCY_LABEL[activity.to],
            style: `color:${URGENCY_COLORS[activity.to]}`,
          }),
        ]),
      );
    }

    if (detail.childElementCount > 0) card.append(detail);
    // 可改可删的：人手写的 log + 进度记录。创建 / 状态 / 优先级仍不给入口 —— 既成事实
    if (activity.kind === "log" || activity.kind === "progress") {
      card.append(entryOps(task, index, activity, card));
    }

    host.timeline.append(el("div", { class: "tl-entry" }, [rail, card]));
  }
}

// ─── 重画 ────────────────────────────────────────────────────────────────────

function paint(task: Task): void {
  if (!drawer) return;

  drawer.badge.className = `st st-${task.status}`;
  drawer.badge.textContent = STATUS_LABEL[task.status];
  drawer.name.textContent = task.title;
  drawer.created.textContent = `创建于 ${pad2(task.created[0])}-${pad2(task.created[1])}`;

  drawer.form.paint(task);
  drawer.progress.paint(task);
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
    // 进度不在这一区了：它搬到了下面的活动时间线（见 .tl-prog）
    withProgress: false,
    onEdit: () => dataChanged(),
    onStatusChange: (next: TaskStatus) =>
      toast(`状态已改为「${STATUS_LABEL[next]}」· 全局视图已联动`),
  });

  const timeline = el("div", { class: "tl-list" });
  const timelineCount = el("span", { class: "dim mono" });

  // ── 记录新进展 ──
  const composer = el("input", { placeholder: COMPOSE_HINT });
  const send = el("button", { class: "tl-send", title: "保存", html: SEND_ICON });

  // ── 进度（就摆在时间线里）──
  // 左边那条是滑杆本身（填充即「现在到哪了」，拖一下就是改），右边数字框负责精确值。
  // 不另摆一条只读的进度条：两条长得差不多，摆一起只是重复。
  //
  // **草稿式**（`mode: "deferred"`）：拖 / 填只改草稿，**按「发送」才落库** ——
  // 用户报的 bug 是「进度调完、信息还没写完就已经被提交了」（2026-09-20）。
  const progress = progressControl({
    task,
    mode: "deferred",
    onSubmit: () => submit(),
  });

  /**
   * 「发送」= 一次提交：把那句话写进时间线；进度也改过的话，**连同进度记在同一条**记录里
   * （信息与进度不分家，2026-09-20 用户提的）。
   *
   * 只改了进度、一句说明都没写时**不保存**：用户的口径是「进度条修改后需要手动添加进度
   * 信息，点击发送才能保存」。这里给一句提示并聚焦输入框，而不是默默丢掉改动 ——
   * 控件上那句「待保存」也一直在那儿。
   */
  function submit(): void {
    if (!current) return;
    const text = composer.value.trim();
    const pending = progress.pendingText();
    if (pending && !text) {
      toast(`进度 ${pending} 还没保存 · 写一句说明，回车一起记下`);
      composer.focus();
      return;
    }
    if (!text) return;

    const recorded = progress.commit(text);
    if (!recorded) current.activities.unshift({ at: nowStamp(), text, kind: "log" });

    // （这里原来还有一步「写一条进展 → 把待办推到进行中」。**「待办」那档 2026-09-21 删了**
    //   —— 新建任务就是「进行中」，没有可推的起点。留下的只有活动记录里那些 `from: "todo"`
    //   的历史，时间线照旧显示「待办 → 进行中」。）
    dataChanged();

    composer.value = "";
    renderTimeline(current);
    // 「发送」本来就是保存 —— 以前这条已经落库了，只是没有任何反馈，
    // 让人以为还得再点一次什么才算存上
    toast(recorded ? `已记下 ${recorded.from}% → ${recorded.to}%` : "已保存到活动时间线");
  }

  send.addEventListener("click", submit);
  composer.addEventListener("keydown", (event) => {
    if (event.key === "Enter") submit();
  });

  // ── Markdown 源 ──
  const markdown = el("textarea", { class: "md", spellcheck: "false" });
  const mdPreview = el("div", { class: "md-prev" });
  const mdApply = el("button", { class: "btn sm", type: "button", text: "按 md 更新任务" });
  const mdReset = el("button", { class: "btn sm", type: "button", text: "还原" });

  /**
   * 把框里的 md 渲染成一眼能看完的一块。
   *
   * 状态**不**从 md 读：这个框不采纳 md 里的状态（见 data/markdown.ts 表头），
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
    const status = current?.status ?? "doing";
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
    // start 不在写法里（md 只带一个截止日）。一律填今天会把跨天任务的起点抹平，
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
      // 进度就在这一区（2026-09-20 用户提的）：写一句进展、顺手把进度挪到哪 ——
      // 同一行里就能做完，不必再滚回「任务定义」那块找进度，漏维护一处是常态
      el("div", { class: "tl-prog" }, [el("span", { class: "tf-k", text: "进度" }), progress.root]),
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
    progress,
    timeline,
    timelineCount,
    composer,
    markdown,
    mdSync: renderMdPreview,
    resetProgress: () => progress.reset(),
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

  // 换了任务：进度控件里没提交的草稿属于上一条任务，丢掉
  // （否则新任务里会顶着一个来自上一条任务的「待保存 65% → 70%」）
  drawer.resetProgress();
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
