// ─────────────────────────────────────────────────────────────────────────────
// Markdown 写法：一行一个任务，是这个应用与外界交换数据的格式。
//
//   - [ ] 标题 #标签 ⏰09-21 14:30 :: 40%
//
// 原版就这么定义（DESIGN.md）：md 是规范数据源，状态关键字、日期、进度都写在
// 这一行里。
//
// 现在的用武之地只有两处，都是**单条 / 多行文本的往返**，不再有文件级的导入导出：
//   · 抽屉底部的 md 编辑框（`taskToMarkdown` 出、`parseTasks` 入）
//   · 任务管理页的「数据迁入」（选一个 md 文件 → `parseTasksDetailed`）
// 文件级的「导出 .md / 导入 .md」都撤了：导出改成了给人看的清单（标签 → 任务 →
// 活动三层，见 data/export.ts），导入那条路则被批量新建取代 —— 同样吃这套写法，
// 但当场就能看见解析出几条，不用先存成文件再导回来。
//
// ⚠️ 一处有意的取舍：**抽屉那条写回路径不采纳状态**。以前这里写的是「状态不写回
// md，所以导出再导入会把已完成变成待办」，与代码对不上 —— 下面 `taskToMarkdown`
// 会写出 `[x]`、`parseTasks` 也会读它，批量新建正是靠它带状态。不采纳的只有
// pages/taskDrawer.ts 的 `mdApply`：它只取标题 / 标签 / 进度 / 截止，状态保持原值
// （toast 会说出来）。改状态请在抽屉的表单里改，别指望改 md 那一行。
//
// ⚠️ 但**进度**例外（2026-10-16）：进度写满 100% 会顺带把状态置成已完成 —— 因为进度与
// 状态是同一个口径的两面（见 data/status.ts）。所以 `mdApply` 不采纳的是那个复选框，
// 不是进度的语义；`parseTasks` 这边则把两者一起归一（复选框优先），让导入进来的形态
// 与界面里的形态一致。
//
// 「循环」（`+1w`）这个字段已经删除：它从来没有行为，界面上也没有编辑入口，
// 只是随 md 文本空转。但**老文件里那段标记必须继续吃掉**（见 LEGACY_REPEAT），
// 否则它会粘进标题、变成「写周报 +1w」——删字段不该把用户导出的文件弄脏。
// ─────────────────────────────────────────────────────────────────────────────

import {
  dayNumber,
  dayOfStamp,
  isRangeInverted,
  monthDayOf,
  monthDayText,
  nowStamp,
  parseStampText,
  todayMonthDay,
} from "./time";
// 进度满格那一格（100）的唯一定义，别在这里再写字面量
import { FULL_PROGRESS } from "./status";
import type { MonthDay, Task, TaskStatus } from "./types";

/**
 * 状态 → 复选框记号。
 *
 * ⚠️ 现在**写出去**的只有两种：`~`（进行中）/ `x`（已完成）—— 「待办」那档 2026-09-21
 * 删了（新建即进行中）。`overdue` 与从前的 `todo` 一样写成 `[ ]`：逾期是**系统**标的，
 * 不是用户选的，写法上它仍然只是「没画勾」。
 */
const BOX: Record<TaskStatus, string> = { doing: "~", done: "x", overdue: " " };

/** 一条任务 → 一行 md。 */
export function taskToMarkdown(task: Task): string {
  // 截止日期直接读 end / at，不去反解 due 那段人话文案：文案里会有「今天 / 明天」
  // 这类相对词，靠 includes 猜再倒推日期，加一个新词就会漏（曾经导出过
  // `⏰2026-明天`）。日期本身才是数据，文案只是它的显示形式。
  const due = task.due
    ? ` ⏰${monthDayText(dayNumber(task.end))}${task.at ? ` ${task.at}` : ""}`
    : "";

  const progress = task.progress ? ` :: ${task.progress}%` : "";
  return `- [${BOX[task.status]}] ${task.title} ${task.tags.join(" ")}${due}${progress}`;
}

const LINE = /^\s*[-*]\s+\[([ xX~])\]\s*(.*)$/;
const TAG = /#[^\s#]+/g;
const DUE = /⏰\s*(?:\d{4}-)?(\d{2})-(\d{2})(?:\s+(\d{2}):(\d{2}))?/;
const PROGRESS = /::\s*(\d{1,3})%/;

/**
 * 活动行：**缩进在任务下面**、以 `MM-DD HH:MM` 开头的一行，挂到上一条任务的活动
 * 时间线上。
 *
 *   - [~] 示例任务 #示例标签 ⏰09-29 :: 80%
 *      - 08-25 16:50 记一条进展
 *      - 08-25 16:52 [标记] 带方括号前缀的也认
 *
 * 为什么要有：活动分析导出的清单是这个形状（标签 → 任务 → 活动三层），它是
 * 「迁移旧数据」时唯一带着**活动历史**的载体 —— 不带这一条，导进来的任务就只有
 * 标题，几十上百条流水全丢。时刻直接交给 `parseStampText`：它认 `MM-DD HH:MM`
 * 这个写法，一个字都不用新写。
 *
 * 缩进至少两格：不缩进的 `- MM-DD` 是一行独立的文本，不是谁的活动。`- ` 前缀
 * 可选 —— 两种导出（带与不带这个前缀）都能直接粘进来。
 */
const ACTIVITY = /^\s{2,}(?:[-*]\s+)?(\d{2}-\d{2}\s+\d{2}:\d{2})\s+(.+)$/;

/**
 * 旧写法里的循环标记（`+1w` / `+3d` …）。字段已经删了，但解析时仍要把它吃掉：
 * 用户导出的文件里带着它，不处理的话这段文字会留在标题里，变成
 * 「写周报 +1w」—— 删掉一个没人用的字段，不该顺手改坏别人已有的数据。
 */
const LEGACY_REPEAT = /\+\d+[dwmy]/;

/** 解析结果：认出来的任务 + **认不出的行** + **被修正过起点的草稿**。 */
export interface ParseReport {
  drafts: Omit<Task, "partition">[];
  /**
   * 认不出的行（行号从 1 起，`text` 是原文）。空行不算。
   *
   * 为什么要有：这套解析的原则是「认不出就跳过，不半懂不懂地猜」，但**跳过**在界面上
   * 一直只体现为一个数字 —— 粘了 30 行的人看到「将创建 27 条」，不知道少的那 3 行是
   * 哪些、为什么少。迁移工具那套「先对账」在这里同样成立：少掉的东西必须能看见。
   */
  skipped: { line: number; text: string }[];
  /**
   * 起点晚于截止日、起点与创建日被按截止日修正过的草稿（2026-10-16 加）。
   *
   * 与 `skipped` 同一条理由：**替用户做的决定必须能看见**。这一处是全应用唯一一次
   * 改动用户数据（连源里写着的截止日都没动，动的是这里推断出来的起点），
   * 所以它得在迁入前的那次对账里逐条列出来 —— 否则「导进来的任务时间轴怪怪的」
   * 会变成一个查不出原因的现象。
   */
  adjusted: { title: string; inferred: MonthDay; end: MonthDay }[];
}

/**
 * 一段 md → 任务草稿 + 认不出的行。
 *
 * 只认「一行一条任务」这一种写法，认不出的行直接跳过 —— 半懂不懂地猜出一个
 * 标题，比明确地跳过更糟。返回的是草稿（没有 id 和分区），由调用方补齐：
 * id 要唯一，分区要落在当前分区。
 */
export function parseTasksDetailed(md: string): ParseReport {
  const drafts: Omit<Task, "partition">[] = [];
  const skipped: { line: number; text: string }[] = [];
  const adjusted: { title: string; inferred: MonthDay; end: MonthDay }[] = [];
  const today = todayMonthDay();
  /** 活动行挂到它名下：这套写法里活动就是缩进在任务下面的子行。 */
  let owner: Omit<Task, "partition"> | null = null;

  md.split(/\r?\n/).forEach((raw, index) => {
    const at = index + 1;

    const activity = ACTIVITY.exec(raw);
    if (activity) {
      // 前面没有任何任务的活动行：这行字不属于谁 —— 半懂不懂地挂到上上条任务上
      // 比丢掉它更糟，所以不猜；但它确实**丢了**，得报出来
      if (!owner) {
        skipped.push({ line: at, text: raw.trim() });
        return;
      }
      owner.activities.push({
        at: parseStampText(activity[1], nowStamp()),
        text: activity[2].trim(),
        kind: "log",
      });
      return;
    }

    // 空行是排版，不是「认不出」
    if (raw.trim() === "") return;

    const line = LINE.exec(raw);
    if (!line) {
      skipped.push({ line: at, text: raw.trim() });
      return;
    }

    const box = line[1];
    const body = line[2];

    const tags = [...body.matchAll(TAG)].map((match) => match[0]);
    const due = DUE.exec(body);
    const progress = PROGRESS.exec(body);

    const title = body
      .replace(TAG, "")
      .replace(DUE, "")
      .replace(PROGRESS, "")
      .replace(LEGACY_REPEAT, "")
      .replace(/\s+/g, " ")
      .trim();
    if (!title) {
      // 方括号在、标题却是空的（`- [ ] #工作`）：这行确实想建一条任务但建不出来 ——
      // 报出来，别让它静默消失
      skipped.push({ line: at, text: raw.trim() });
      return;
    }

    // `[ ]` 仍然**收得进来**（它是最通用的「没画勾」记号，老文件和别处导出的清单里都有），
    // 但算「进行中」—— 待办那档 2026-09-21 删了。代价说在明处：**往返会把 `[ ]` 写成 `[~]`**
    // （见上面 BOX 的说明）
    //
    // 2026-10-16 起这里是**复选框优先**的双向归一（与 data/status.ts 同一口径）：`[x]` ⇒
    // 已完成 + 100%；空格子写 `:: 100%` ⇒ 也算完成。不归一的话，`- [~] x :: 100%` 会产出
    // 「进行中 + 100%」—— 自愈扫描下一次就把它改成已完成，于是「导进来又自己变回去」。
    const boxDone = !(box === "~" || box === " " || box === "");
    const written = progress ? Math.min(FULL_PROGRESS, Number(progress[1])) : null;
    const status: TaskStatus = boxDone || written === FULL_PROGRESS ? "done" : "doing";
    // 没有 ⏰ 就是**没有截止**：due 留空（界面显示「无截止」），end 落今天 ——
    // 总览的「今日到期」按 due 判，不会把它算进去（见 overview.ts 的 renderTiles）
    const end: MonthDay = due ? [Number(due[1]), Number(due[2])] : today;

    const draft: Omit<Task, "partition"> = {
      id: "",
      title,
      status,
      tags,
      due: due ? `${due[1]}-${due[2]}${due[3] ? ` ${due[3]}:${due[4]}` : ""}` : null,
      at: due?.[3] ? `${due[3]}:${due[4]}` : null,
      start: today,
      end,
      progress: status === "done" ? FULL_PROGRESS : (written ?? 0),
      urgency: 2,
      created: today,
      archived: false,
      related: [],
      activities: [],
    };

    drafts.push(draft);
    owner = draft;
  });

  for (const draft of drafts) {
    if (draft.activities.length === 0) {
      // 没带活动行（绝大多数情况：手写、批量新建）：留一条「导入任务」，
      // 时间线不至于空着
      draft.activities.push({ at: nowStamp(), text: "导入任务", kind: "create" });
    } else {
      // 活动数组的约定是**新的在前**（见 store 里写活动那几处），
      // 而清单里是时间正序 —— 排一次，省得每个读它的地方自己再排
      draft.activities.sort((a, b) => b.at - a.at);
    }

    // 「创建日 / 起点」取这条任务**最早一条活动**的日期（排完序后就是最后一条），
    // 不是导入日。
    //
    // 为什么：从旧版迁进来的任务，历史全在活动行里 —— 一律落导入日会让整批任务的
    // 「创建于」挤在同一天，而**创建日是这次迁移里唯一会被整个抹平的时间维度**
    // （截止 / 进度 / 状态都能从活动文本里挖出来）。活动行上的时间是源里真实写着的。
    //
    // 精度说清楚：它给的是「**第一次动手**」那天，不是真正的创建时刻 —— 旧版的「创建
    // 任务」记录属于那代人的记账，按设计不转移（见 `tadado-activity-import` skill 的「滤掉系统记录」），
    // 所以对「建了长期搁着」的任务会偏晚。
    //
    // `start` 一起用这个日期：单独留成导入日的话，会出现「创建于 01-05、甘特色条却从
    // 09-20 开始」这种自相矛盾。
    //
    // 手写的行不参与这一步：它们没有活动行，上面刚补的那条「导入任务」就是今天。
    // （但「今天」可能晚于这一行写的截止日 —— 手写的过期任务正是这样，它会在下面那段
    // 里被按截止日修正，见 `adjusted`。）
    const earliest = draft.activities[draft.activities.length - 1]!;
    const monthDay = monthDayOf(dayOfStamp(earliest.at));
    draft.created = monthDay;
    draft.start = monthDay;

    // 推断出来的起点晚于截止日 = 这一行自相矛盾（截止写得比最早那条活动还早）。
    // 挪的是**推断的**那一端：起点连带创建日落到截止日（「它至少在截止日那天就已经
    // 存在」），而截止日是源里写着的、最早那条活动也是源里写着的 —— 两个事实一个都
    // 不动。反过来的做法（把截止顺手推后）等于修改用户写下的截止时间，那是另一件事，
    // 而且没人授权。修正过谁，由 ParseReport.adjusted 带出去给用户看。
    if (isRangeInverted(dayNumber(draft.start), dayNumber(draft.end))) {
      adjusted.push({ title: draft.title, inferred: monthDay, end: draft.end });
      draft.created = draft.end;
      draft.start = draft.end;
    }
  }

  return { drafts, skipped, adjusted };
}

/**
 * 只要草稿时用这个（抽屉的 md 源、批量新建都只关心解析出什么）。
 * 需要知道「哪些行没认出来」就走 `parseTasksDetailed`。
 */
export function parseTasks(md: string): Omit<Task, "partition">[] {
  return parseTasksDetailed(md).drafts;
}
