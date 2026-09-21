// ─────────────────────────────────────────────────────────────────────────────
// 任务定义表单。
//
// 「这条任务是什么」的全部字段都在这里：标题、标签、开始、结束、状态、优先级、
// 进度。抽屉和「新建任务」对话框共用同一个实现 —— 两处各写一份的话，字段会慢慢
// 长歪（新建时能填状态、编辑时没有；列表上有优先级、编辑界面里只有一行文字），
// 用户看到的「编辑界面和列表对不上」就是这么来的。
//
// 表单直接改传进来的 task 对象，改完调 onEdit，由调用方决定怎么落库：
// 抽屉是 dataChanged()，对话框是「先攒着，点创建再入库」。
// ─────────────────────────────────────────────────────────────────────────────

import { MAX_TAGS, normalizeTags } from "../data/tags";
import {
  dueTextOf,
  dayNumber,
  monthDayOf,
  nowMinutes,
  nowStamp,
  TODAY,
  todayMonthDay,
} from "../data/time";
import type { Activity, Task, TaskStatus, Urgency } from "../data/types";
import { dateTimeField } from "../shell/dateTime";
import { el } from "../shell/dom";
import { toast } from "../shell/toast";
import { STATUS_LABEL, URGENCY_LABEL, pad2, setTaskStatus, urgencyBadge } from "./shared";

export interface TaskFormOptions {
  task: Task;
  /** 任一字段改完调用。调用方负责落库与刷新（时间线、列表、图谱）。 */
  onEdit: (field: "title" | "tags" | "start" | "end" | "status" | "urgency" | "progress") => void;
  /** 抽屉里给状态变更额外提示用；对话框里不需要。 */
  onStatusChange?: (next: TaskStatus) => void;
  /**
   * 要不要带上「进度」这一行，默认带。
   *
   * 抽屉传 `false`：进度控件已经搬到**活动时间线**里（见 taskDrawer 的 .tl-prog）——
   * 写一句进展和把进度挪到哪，本来就是同一次动作的两半，分在两个区就会漏维护一处
   * （2026-09-20 用户提的）。对话框仍带：新任务还没有时间线，字段得先在表单里填完。
   */
  withProgress?: boolean;
}

export interface TaskForm {
  root: HTMLElement;
  /** 外部数据变了（别处改了这条、逾期自动标记）时回写显示。不触发 onEdit。 */
  paint: (task: Task) => void;
}

export interface ProgressControl {
  /** 「滑杆 + 数字框 + %」一行，标签由调用方加（两处的字段名不一样）。 */
  root: HTMLElement;
  paint: (task: Task) => void;
  /** 还没提交的改动（`50% → 65%`）；没有改动时为 null。 */
  pendingText: () => string | null;
  /**
   * 提交一次：改掉 `task.progress` 并往时间线写一条记录，返回那条记录（没有改动则 null）。
   * `text` 是随它一起记下的那句话 —— 抽屉里就是「记录一条进展」那一行写的内容。
   */
  commit: (text?: string) => ProgressActivity | null;
  /** 丢掉未提交的改动，显示拉回任务当前值（换任务时用）。 */
  reset: () => void;
}

/** 时间线上的一条**进度**记录（`from → to`）。 */
export type ProgressActivity = Extract<Activity, { kind: "progress" }>;

/**
 * 进度维护控件：滑杆（大概拖一下）+ 数字框（就要 65%）。
 *
 * 两个消费方：**新建任务对话框**放在「任务定义」里（immediate）；**任务抽屉**放在
 * 活动时间线里（deferred，见 taskDrawer 的 .tl-prog）。抽成一份是因为 from 的抓取
 * 时机、钳位、以及「拖回原值不留记录」这几条规则一旦各写一份，迟早会分叉。
 *
 * ⚠️ **进度一律手动维护**（用户用了很多次之后明确定的）：这里没有任何「按活动内容
 * 推导进度」的自动逻辑 —— 拖到哪、填多少就是多少。
 */
export function progressControl(options: {
  task: Task;
  /**
   * `"immediate"`（默认，对话框用）：松手 / 回车即提交 —— 那边没有「发送」按钮，
   * 表单本来就是即时保存的。
   *
   * `"deferred"`（抽屉用）：**只改草稿**，由调用方在「发送」时提交。用户的口径是
   * 「进度条修改后需要手动添加进度信息，点击发送才能保存」—— 拖着放着就被记下来，
   * 那是 bug（2026-09-20 报的：信息还没写完就已经提交了）。
   */
  mode?: "immediate" | "deferred";
  /** 提交后把那条记录交出去（调用方落库 / 刷新）。 */
  onCommit?: (activity: ProgressActivity) => void;
  /** deferred 模式下「数字框里按回车」：交给调用方当一次提交（抽屉走的就是「发送」那条路）。 */
  onSubmit?: () => void;
}): ProgressControl {
  let task = options.task;
  const deferred = options.mode === "deferred";

  const range = el("input", { type: "range", class: "range", min: "0", max: "100" });
  const input = el("input", { type: "number", class: "pct-input", min: "0", max: "100" });
  /**
   * 「待保存 65% → 70%」。deferred 模式必须把「还没保存」写在脸上：改动不落库，
   * 用户拖完就走的话，改动静默消失 —— 那和「拖着就被提交」是同一类毛病的两面。
   */
  const pendingNote = el("span", { class: "prog-pending" });
  const root = el("div", { class: "prog-ctl" }, [
    range,
    input,
    el("span", { class: "dim", text: "%" }),
    pendingNote,
  ]);

  /** 草稿的起点（改动前的值）。null = 当前没有未提交的改动。 */
  let base: number | null = null;
  /** 草稿值。 */
  let draft = task.progress;

  const clamp = (raw: number): number =>
    Math.max(0, Math.min(100, Math.round(Number.isNaN(raw) ? 0 : raw)));

  const dirty = (): boolean => base !== null && draft !== base;

  /** 滑杆的填充就是「一眼看出进度到哪了」——只有滑杆头没有填充时，它读起来像个开关。 */
  const paintRange = (value: number): void => {
    range.value = String(value);
    range.style.background = `linear-gradient(to right, var(--accent) ${value}%, var(--border) ${value}%)`;
  };

  const paintPending = (): void => {
    const on = dirty();
    root.classList.toggle("dirty", on);
    pendingNote.textContent = on ? `待保存 ${base}% → ${draft}%` : "";
  };

  /**
   * 记一笔草稿。
   *
   * `base` 在**开始改之前**抓一次：滑杆的 `input` 每动一下都发一次，拿「上一次的值」
   * 当起点的话，时间线会刷出「50→51、51→52……」一串噪声。on`syncInput` 让数字框跟着
   * 拖动走（一边拖一边能看到具体到多少）。
   */
  const setDraft = (raw: number, syncInput: boolean): void => {
    if (base === null) base = task.progress;
    draft = clamp(raw);
    paintRange(draft);
    if (syncInput) input.value = String(draft);
    paintPending();
  };

  const commit = (text?: string): ProgressActivity | null => {
    // 没有改动就不提交：时间线上不留「30% → 30%」这种记录
    if (!dirty()) return null;
    const start = base as number;
    const next = draft;
    task.progress = next;
    const activity: ProgressActivity = {
      at: nowStamp(),
      kind: "progress",
      from: start,
      to: next,
      // 一句说明由调用方给（抽屉里就是输入框里那句话）；没给就退回数字落差
      text: text?.trim() || `${start}% → ${next}%`,
    };
    // **存储**仍然最新在前（unshift）：导出、统计与「后面那条记录」的判定都按这个约定
    // 走。抽屉里的**显示**是正序（最早的在上），渲染时反着铺 —— 见 renderTimeline
    task.activities.unshift(activity);
    base = null;
    paintRange(next);
    input.value = String(next);
    paintPending();
    options.onCommit?.(activity);
    return activity;
  };

  range.addEventListener("input", () => setDraft(Number(range.value), true));
  range.addEventListener("change", () => {
    if (!deferred) commit();
  });
  input.addEventListener("change", () => {
    // deferred：只把草稿收下来，保存交给「发送」
    if (deferred) {
      setDraft(Number(input.value), false);
      return;
    }
    commit();
  });
  input.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    if (deferred) {
      // 先把框里的数收进草稿，再交出去 —— 回车和点「发送」是同一条路
      setDraft(Number(input.value), false);
      options.onSubmit?.();
      return;
    }
    commit();
    input.blur();
  });

  return {
    root,
    paint: (next) => {
      task = next;
      // 有未提交的草稿就不回写：拖/填到一半被别处的重画冲掉，等于白改
      if (dirty()) return;
      base = null;
      draft = task.progress;
      paintRange(draft);
      // 正在改数字框的人不该被外面的重画把字带走
      if (document.activeElement !== input) input.value = String(draft);
      paintPending();
    },
    pendingText: () => (dirty() ? `${base}% → ${draft}%` : null),
    commit,
    reset: () => {
      base = null;
      draft = task.progress;
      paintRange(draft);
      input.value = String(draft);
      paintPending();
    },
  };
}

export function taskForm(options: TaskFormOptions): TaskForm {
  let task = options.task;

  // ── 标题 ──
  const title = el("input", { class: "dr-title", spellcheck: "false" });
  title.addEventListener("change", () => {
    const next = title.value.trim();
    // 空标题不许存：时间轴上一条没有名字的色条等于不知道它是谁
    if (!next) {
      title.value = task.title;
      toast("标题不能为空");
      return;
    }
    if (next === task.title) return;
    task.title = next;
    options.onEdit("title");
  });

  // ── 标签 ──
  // 带不带 `#` 都认（见 data/tags 的 normalizeTags）：以前只认带 `#` 的写法，
  // 「学习 工作」会被解析成空数组 —— 新建时被兜底成单个 #工作，编辑时静默清空
  const tags = el("input", {
    class: "dr-tags",
    spellcheck: "false",
    placeholder: `标签，空格分隔，最多 ${MAX_TAGS} 个（# 可省略）`,
  });
  tags.addEventListener("change", () => {
    const { tags: next, dropped } = normalizeTags(tags.value);

    if (next.length === 0) {
      // 标签决定任务在图谱里挂到哪个节点下，空标签等于没有归属
      if (task.tags.length > 0) {
        tags.value = task.tags.join(" ");
        toast("至少要有一个标签 —— 标签决定任务在图谱里挂在哪个节点下");
      } else {
        // 新建草稿：允许先空着，提交时的必填校验会说话
        tags.value = "";
        task.tags = [];
      }
      return;
    }

    task.tags = next;
    options.onEdit("tags");
    // 超上限的部分明说，不静默丢
    if (dropped.length > 0) toast(`最多 ${MAX_TAGS} 个标签，已忽略 ${dropped.join(" ")}`);
    else toast(`标签已改为 ${next.join(" ")}`);
  });

  // ── 开始 / 结束 ──
  // 开始只到日期（它决定甘特条的起点）；结束带时分（它才是要提醒的那个点）。
  // 两个字段用同一个组件、同一套排布，所以这两行在抽屉里是齐的。
  const startField = dateTimeField({
    label: "开始",
    withTime: false,
    clearable: false,
    value: { day: dayNumber(task.start), time: null },
    onChange: ({ day }) => {
      if (day === null) return;
      task.start = monthDayOf(day);
      options.onEdit("start");
    },
  });

  const endField = dateTimeField({
    label: "结束",
    withTime: true,
    value: { day: dayNumber(task.end), time: task.at },
    onChange: ({ day, time }) => {
      if (day === null) {
        // 清除截止：due 是「有没有截止」的唯一开关，at 跟着一起清。
        // end 必须落回今天 —— 它是甘特条跨度的终点，模型里必填；留在过去那一天
        // 会让任务继续按「逾期」算（overdue 是按 end < 今天 判的）
        task.due = null;
        task.at = null;
        task.end = todayMonthDay();
        options.onEdit("end");
        toast("已清除截止");
        return;
      }
      task.end = monthDayOf(day);
      task.at = time;
      // 文案由 data/time 统一生成，不再各处自己拼
      task.due = dueTextOf(day, time);
      options.onEdit("end");
    },
  });

  // ── 状态 ──
  const statusRow = el("div", { class: "chips" });
  const statusButtons = (["doing", "done"] as const).map((status) => {
    const button = el("button", {
      class: "chip",
      type: "button",
      text: STATUS_LABEL[status],
    });
    button.addEventListener("click", () => {
      // 走 setTaskStatus：状态改动要留一条活动，否则「什么时候完成的」没有任何记录
      setTaskStatus(task, status);
      paint(task);
      options.onEdit("status");
      options.onStatusChange?.(status);
    });
    statusRow.append(button);
    return { status, button };
  });
  // 逾期由系统标记，不给按钮，但要让人看见它现在是逾期
  const overdueNote = el("span", { class: "chip st-overdue-note", text: "逾期（系统标记）" });

  // ── 优先级 ──
  // 用和列表徽标同一个小组件：列表上那个 P0–P3 长什么样，这里就长什么样
  const urgencyRow = el("div", { class: "chips" });
  const urgencyButtons = URGENCY_LABEL.map((label, level) => {
    const button = el("button", { class: "chip urg-pick", type: "button" }, [
      urgencyBadge(level as Urgency),
      el("span", { text: label }),
    ]);
    button.addEventListener("click", () => {
      const from = task.urgency;
      const to = level as Urgency;
      // 点当前那一档 = 没改，不留记录（否则时间线会被「关注 → 关注」刷屏）
      if (from === to) return;
      task.urgency = to;
      // 与状态同一套处理：改优先级也是一次决定，时间线要记得住。
      // 「关于」面板里那句「改优先级也会写进活动时间线」就是对这条的承诺
      task.activities.unshift({
        at: nowStamp(),
        kind: "urgency",
        from,
        to,
        text: `${URGENCY_LABEL[from]} → ${URGENCY_LABEL[to]}`,
      });
      paint(task);
      options.onEdit("urgency");
    });
    urgencyRow.append(button);
    return { level, button };
  });

  // ── 进度 ──
  // 控件本身在 progressControl 里（对话框与抽屉共用一份）。这里只负责「改完落库」：
  // 那条进度记录由控件写进 task.activities，表单不重复实现一遍。
  const progress = progressControl({
    task,
    onCommit: () => options.onEdit("progress"),
  });

  const root = el("div", { class: "tform" }, [
    el("div", { class: "tf-row" }, [el("span", { class: "tf-k", text: "任务" }), title]),
    el("div", { class: "tf-row" }, [el("span", { class: "tf-k", text: "标签" }), tags]),
    startField.root,
    endField.root,
    el("div", { class: "tf-row" }, [el("span", { class: "tf-k", text: "状态" }), statusRow, overdueNote]),
    el("div", { class: "tf-row" }, [el("span", { class: "tf-k", text: "优先级" }), urgencyRow]),
    ...(options.withProgress === false
      ? []
      : [el("div", { class: "tf-row" }, [el("span", { class: "tf-k", text: "进度" }), progress.root])]),
  ]);

  const paint = (next: Task): void => {
    task = next;
    // 正在编辑的框不回写：change 之前模型还是旧的，此时被别处的 dataChanged
    // 带着重画一遍，用户敲到一半的字就没了
    if (document.activeElement !== title) title.value = task.title;
    if (document.activeElement !== tags) tags.value = task.tags.join(" ");

    startField.setValue({ day: dayNumber(task.start), time: null });
    endField.setValue({ day: task.due ? dayNumber(task.end) : null, time: task.at });

    for (const { status, button } of statusButtons) {
      button.classList.toggle("on", task.status === status);
    }
    overdueNote.style.display = task.status === "overdue" ? "" : "none";

    for (const { level, button } of urgencyButtons) {
      button.classList.toggle("on", task.urgency === level);
    }

    progress.paint(task);
  };

  // 对话框里直接调 paint 初始化；抽屉里由 openTask 传入真实任务后再调
  paint(task);

  return { root, paint };
}

/** 「现在」的 `HH:MM`。新建任务的「结束」时刻默认用它。 */
const nowTime = (): string => {
  const minutes = nowMinutes();
  return `${pad2(Math.floor(minutes / 60))}:${pad2(minutes % 60)}`;
};

/**
 * 新建任务用的空白草稿：字段齐全但没有 id / 分区，入库前由调用方补齐。
 *
 * 「结束」默认 **今天 + 当前时刻**（2026-09-21 用户提的：「时分默认是当前时间，目前是空，
 * 需要手动选择」）。两件事一起修：
 *  · 时刻原本是空的 —— 点完「今天」还得再挑一次时分，而绝大多数新建就是「从现在起」；
 *  · 日期框本来就显示着今天（`value: { day: dayNumber(task.end) }`），但 `due` 是 null，
 *    于是字段**看着填好了**、点「创建」却说「还差：结束时间」—— 显示与模型两个口径。
 *    现在 `due` / `at` / `end` 一次给齐，字段显示的就是模型里的那件事。
 *
 * 「结束时间是必填」这条规矩仍然成立：点「清除」之后 `due` 就是 null，创建时照样拦下来。
 */
export const draftTask = (): Task => {
  const at = nowTime();
  return {
    id: "",
    title: "",
    status: "doing",
    tags: [],
    due: dueTextOf(TODAY, at),
    at,
    start: todayMonthDay(),
    end: todayMonthDay(),
    progress: 0,
    urgency: 2,
    created: todayMonthDay(),
    archived: false,
    partition: "",
    related: [],
    activities: [],
  };
};

/** 今天（面板上「开始」的默认值）。单独导出是因为对话框要用它做初始值。 */
export const TODAY_DAY = TODAY;
