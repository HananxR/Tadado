// ─────────────────────────────────────────────────────────────────────────────
// Markdown 方言：一行一个任务，是这个应用与外界交换数据的格式。
//
//   - [ ] 标题 #标签 ⏰09-21 14:30 :: 40%
//
// 原版就这么定义（DESIGN.md）：md 是规范数据源，状态关键字、日期、进度都写在
// 这一行里。
//
// 现在的用武之地只有两处，都是**单条 / 多行文本的往返**，不再有文件级的导入导出：
//   · 抽屉底部的 md 编辑框（`taskToMarkdown` 出、`parseTasks` 入）
//   · 任务页的批量新建（粘贴多行 → `parseTasks`）
// 文件级的「导出 .md / 导入 .md」都撤了：导出改成了给人看的清单（标签 → 任务 →
// 活动三层，见 data/export.ts），导入那条路则被批量新建取代 —— 同样吃这套方言，
// 但当场就能看见解析出几条，不用先存成文件再导回来。
//
// ⚠️ 有一处是有意的取舍：状态关键字不写回 md（DESIGN.md 明确规定），所以
// 「导出再导入」会把已完成的任务变成待办。这是既定规范，不是 bug ——
// 状态存数据库列，md 只承载标题 / 标签 / 日期 / 进度。
//
// 「循环」（`+1w`）这个字段已经删除：它从来没有行为，界面上也没有编辑入口，
// 只是随 md 文本空转。但**老文件里那段标记必须继续吃掉**（见 LEGACY_REPEAT），
// 否则它会粘进标题、变成「写周报 +1w」——删字段不该把用户导出的文件弄脏。
// ─────────────────────────────────────────────────────────────────────────────

import { dayNumber, monthDayText, nowStamp, parseStampText, todayMonthDay } from "./time";
import type { MonthDay, Task, TaskStatus } from "./types";

const BOX: Record<TaskStatus, string> = { todo: " ", doing: "~", done: "x", overdue: " " };

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
 * 旧方言里的循环标记（`+1w` / `+3d` …）。字段已经删了，但解析时仍要把它吃掉：
 * 用户导出的文件里带着它，不处理的话这段文字会留在标题里，变成
 * 「写周报 +1w」—— 删掉一个没人用的字段，不该顺手改坏别人已有的数据。
 */
const LEGACY_REPEAT = /\+\d+[dwmy]/;

/**
 * 一段 md → 任务草稿。
 *
 * 只认「一行一条任务」这一种写法，认不出的行直接跳过 —— 半懂不懂地猜出一个
 * 标题，比明确地跳过更糟：用户只会发现「导入了 30 条」而不知道少了一条。
 * 返回的是草稿（没有 id 和分区），由调用方补齐：id 要唯一，分区要落在当前分区。
 */
export function parseTasks(md: string): Omit<Task, "partition">[] {
  const drafts: Omit<Task, "partition">[] = [];
  const today = todayMonthDay();
  /** 活动行挂到它名下：方言里活动就是缩进在任务下面的子行。 */
  let owner: Omit<Task, "partition"> | null = null;

  for (const raw of md.split(/\r?\n/)) {
    const activity = ACTIVITY.exec(raw);
    if (activity) {
      // 前面没有任何任务的活动行：这行字不属于谁，跳过 —— 半懂不懂地挂到
      // 上上条任务上，比丢掉它更糟
      if (owner) {
        owner.activities.push({
          at: parseStampText(activity[1], nowStamp()),
          text: activity[2].trim(),
          kind: "log",
        });
      }
      continue;
    }

    const line = LINE.exec(raw);
    if (!line) continue;

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
    if (!title) continue;

    const status: TaskStatus =
      box === " " || box === "" ? "todo" : box === "~" ? "doing" : "done";
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
      progress: progress ? Math.min(100, Number(progress[1])) : status === "done" ? 100 : 0,
      urgency: 2,
      created: today,
      archived: false,
      related: [],
      activities: [],
    };

    drafts.push(draft);
    owner = draft;
  }

  for (const draft of drafts) {
    if (draft.activities.length === 0) {
      // 没带活动行（绝大多数情况：手写、批量新建）：留一条「导入任务」，
      // 时间线不至于空着
      draft.activities.push({ at: nowStamp(), text: "导入任务", kind: "create" });
      continue;
    }
    // 活动数组的约定是**新的在前**（见 store 里写活动那几处），
    // 而清单里是时间正序 —— 排一次，省得每个读它的地方自己再排
    draft.activities.sort((a, b) => b.at - a.at);
  }

  return drafts;
}
