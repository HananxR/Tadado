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
import { dueTextOf, dayNumber, monthDayOf, TODAY, todayMonthDay } from "../data/time";
import type { Task, TaskStatus, Urgency } from "../data/types";
import { dateTimeField } from "../shell/dateTime";
import { el } from "../shell/dom";
import { toast } from "../shell/toast";
import { STATUS_LABEL, URGENCY_LABEL, setTaskStatus, urgencyBadge } from "./shared";

export interface TaskFormOptions {
  task: Task;
  /** 任一字段改完调用。调用方负责落库与刷新（时间线、列表、图谱）。 */
  onEdit: (field: "title" | "tags" | "start" | "end" | "status" | "urgency" | "progress") => void;
  /** 抽屉里给状态变更额外提示用；对话框里不需要。 */
  onStatusChange?: (next: TaskStatus) => void;
}

export interface TaskForm {
  root: HTMLElement;
  /** 外部数据变了（别处改了这条、逾期自动标记）时回写显示。不触发 onEdit。 */
  paint: (task: Task) => void;
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
  const statusButtons = (["todo", "doing", "done"] as const).map((status) => {
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
      task.urgency = level as Urgency;
      paint(task);
      options.onEdit("urgency");
    });
    urgencyRow.append(button);
    return { level, button };
  });

  // ── 进度 ──
  // 滑杆负责「大概拖一下」，数字框负责「就要 65%」。只能拖的时候，
  // 想精确到某个数就得来回蹭 —— 用户直接说了「无法直接指定」。
  const progressRange = el("input", { type: "range", class: "range", min: "0", max: "100" });
  // 数字框就是读数，不再另起一个「65%」的文字 —— 输入框 + 单位已经说完了
  const progressInput = el("input", {
    type: "number",
    class: "pct-input",
    min: "0",
    max: "100",
  });

  const setProgress = (raw: number, commit: boolean): void => {
    const next = Math.max(0, Math.min(100, Math.round(Number.isNaN(raw) ? 0 : raw)));
    task.progress = next;
    paint(task);
    if (commit) options.onEdit("progress");
  };

  progressRange.addEventListener("input", () => setProgress(Number(progressRange.value), false));
  progressRange.addEventListener("change", () => setProgress(Number(progressRange.value), true));
  progressInput.addEventListener("change", () => setProgress(Number(progressInput.value), true));
  progressInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      setProgress(Number(progressInput.value), true);
      progressInput.blur();
    }
  });

  const root = el("div", { class: "tform" }, [
    el("div", { class: "tf-row" }, [el("span", { class: "tf-k", text: "任务" }), title]),
    el("div", { class: "tf-row" }, [el("span", { class: "tf-k", text: "标签" }), tags]),
    startField.root,
    endField.root,
    el("div", { class: "tf-row" }, [el("span", { class: "tf-k", text: "状态" }), statusRow, overdueNote]),
    el("div", { class: "tf-row" }, [el("span", { class: "tf-k", text: "优先级" }), urgencyRow]),
    el("div", { class: "tf-row" }, [
      el("span", { class: "tf-k", text: "进度" }),
      progressRange,
      progressInput,
      el("span", { class: "dim", text: "%" }),
    ]),
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

    progressRange.value = String(task.progress);
    if (document.activeElement !== progressInput) progressInput.value = String(task.progress);
  };

  // 对话框里直接调 paint 初始化；抽屉里由 openTask 传入真实任务后再调
  paint(task);

  return { root, paint };
}

/** 新建任务用的空白草稿：字段齐全但没有 id / 分区，入库前由调用方补齐。 */
export const draftTask = (): Task => ({
  id: "",
  title: "",
  status: "todo",
  tags: [],
  due: null,
  at: null,
  start: todayMonthDay(),
  end: todayMonthDay(),
  progress: 0,
  urgency: 2,
  created: todayMonthDay(),
  archived: false,
  partition: "",
  related: [],
  activities: [],
});

/** 今天（面板上「开始」的默认值）。单独导出是因为对话框要用它做初始值。 */
export const TODAY_DAY = TODAY;
