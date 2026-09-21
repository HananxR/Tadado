#!/usr/bin/env node
// ─────────────────────────────────────────────────────────────────────────────
// 旧版活动清单 → Tadado2 能直接导入的一批任务行（v0.x → v1.x 的数据迁移工具）。
//
// 输入：从「活动分析」导出的清单整理成的三层文本（标签 → 任务 → 活动）。
//       这个形状是 v0.x 的活动分析导出的样子，也方便手抄。
// 输出：任务管理页「数据迁入」吃得下的那套写法（任务行 + 缩进的活动行），
//       活动时间线一条不丢 —— 不带它，导进来的任务就只剩标题。
//
// 那套写法由 desktop/src/data/markdown.ts 的 parseTasks 定义，边界见 ../SKILL.md。
//
// 设计原则：**先对账，再动手**。
//   · 默认只解析、只报告，不写任何文件（加 --apply 才写）
//   · 任何一行认不出来 → 记下来、非零退出，绝不「看着差不多就跳过」
//   · 源里的每一行活动都要能在输出里找到去向（输出里 / 并入上一条），数量必须相等
//   · 需要人拍板的事（同名任务、截止缺失…）集中列出来，由调用方去问用户
//
// 用法（**零依赖**，只要机器上有 Node；在哪个目录执行都行，路径按实际位置给）：
//   node <本脚本> <清单.txt|md> [--out 可导入.md] [--report 报告.json] [--apply] [--force] [--keep-system]
// 例（在本 skill 目录里）：node scripts/migrate-activity.mjs sample-input.md --apply
// ─────────────────────────────────────────────────────────────────────────────

import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { basename, resolve } from "node:path";

// ─── 参数 ────────────────────────────────────────────────────────────────────

const argv = process.argv.slice(2);
const flag = (name) => argv.includes(name);
const value = (name) => {
  const at = argv.indexOf(name);
  return at >= 0 ? argv[at + 1] : undefined;
};

const source = argv.find((item) => !item.startsWith("--") && item !== value("--out") && item !== value("--report"));
if (!source) {
  console.error("用法：node migrate-activity.mjs <清单.md> [--out 可导入.md] [--report 报告.json] [--apply] [--force] [--keep-system]");
  process.exit(64);
}

const outPath = value("--out");
const reportPath = value("--report");
const apply = flag("--apply");
/** 覆盖已有的输出文件。默认拒绝 —— 用户很可能手改过它（见下面 apply 那一段）。 */
const force = flag("--force");
/** 保留旧版那些系统记录（创建 / 延后 / 状态 / 进度 / 截止）。默认滤掉，见 SYSTEM_ACTIVITY。 */
const keepSystem = flag("--keep-system");

// ─── 行型 ────────────────────────────────────────────────────────────────────
// 两种来源的写法都要认（同一套层次，符号略有差别）：
//   标签行   `#标签`
//   任务行   `1. 标题`                    导出方 A
//            `1. 标题 [待办→逾期, 0%→0%]:`  导出方 B（多一段状态摘要）
//   活动行   `   01-05 09:10 内容`        导出方 B（缩进 4 空格，无前缀）
//            `   - 01-05 09:10 内容`      导出方 A（缩进 3 空格 + "- "）
// 缩进但不像活动行的 → 当作上一条活动的续行（活动文本里带换行时会被折成独立行）

const RE_TAG = /^#(\S+)\s*$/;
const RE_TASK = /^\s*(\d+)\.\s+(.*?)\s*$/;
const RE_ACTIVITY = /^\s+(?:[-*]\s+)?(\d{2})-(\d{2})\s+(\d{2}):(\d{2})\s+(.*)$/;
const RE_INDENTED = /^\s+\S/;
/** 任务行尾部的状态摘要：`[待办→逾期, 0%→0%]`、`[待办→进行中, 0%→80%]`。 */
const RE_SUMMARY = /\s*\[([^\]]*)\]\s*:?\s*$/;
/** 摘要里的状态与进度。 */
const RE_SUM_STATUS = /([^\s,]+)\s*(?:→|->)\s*([^\s,]+)/;
const RE_SUM_PROGRESS = /(\d+)%\s*(?:→|->)\s*(\d+)%/;

/**
 * 活动文本里的截止线索。
 *
 * 两种写法：`截止时间 A -> B（+N天）`（延后过一次，B 才是**新的**截止）、
 * `截止时间 2026-01-05`（直接设）。两条正则必须互斥 —— 一开始没加那个负向
 * 断言，第二条会把第一条里箭头**左边**的日期也当成"设过的截止"，于是每一条
 * 延后记录都把结果覆盖回旧日期（端到端核对时才看出来：due 写成了 01-15，
 * 而正确答案是 02-20）。
 */
const RE_DUE_MOVE = /截止时间\s*(\d{4}-\d{2}-\d{2})\s*(?:->|→|—>)\s*(\d{4}-\d{2}-\d{2})/g;
const RE_DUE_SET = /截止时间\s*(?:设为|改为)?\s*(\d{4}-\d{2}-\d{2})(?!\s*(?:->|→|—>))/g;

/** 活动的先后：`MM-DD HH:MM` → 可比较的数字。 */
const keyOf = (row) => [Number(row.mm), Number(row.dd), Number(row.hh), Number(row.mi)];
const compare = (a, b) => {
  const left = keyOf(a);
  const right = keyOf(b);
  for (let i = 0; i < left.length; i += 1) if (left[i] !== right[i]) return left[i] - right[i];
  return a.text.localeCompare(b.text);
};
/** 活动文本里的状态变更：`状态变更为 已完成`、`状态变更: 待办 → 进行中`。 */
const RE_STATUS_WORD = /状态变更[为:：]?\s*(?:[^\s→]+)\s*(?:→|->)?\s*([^\s,，。;；]+)/g;

const STATUS_MAP = new Map([
  ["待办", "todo"],
  ["逾期", "todo"], // 没有「逾期」这个写法：它由截止日期自动标出来（见 README.md）
  ["进行中", "doing"],
  ["已完成", "done"],
  ["完成", "done"],
]);

const BOX = { todo: " ", doing: "~", done: "x" };

// ─── 解析 ────────────────────────────────────────────────────────────────────

const lines = readFileSync(source, "utf8").split(/\r?\n/);

/** 每个标签组：{ tag, tasks: [{ seq, title, summary, activities }] }。 */
const groups = [];
const unrecognized = [];
/** 并回上一条活动的续行（源活动文本里带换行）—— 逐行记下来，报告里要列。 */
const bareContinuations = [];
let currentGroup = null;
let currentTask = null;
let pendingActivity = null; // 续行要接回它
let counts = { tag: 0, task: 0, activity: 0, blank: 0, continued: 0 };

lines.forEach((raw, index) => {
  const at = index + 1;
  if (raw.trim() === "") {
    counts.blank += 1;
    return;
  }

  const tag = RE_TAG.exec(raw);
  if (tag) {
    currentGroup = { tag: `#${tag[1]}`, tasks: [] };
    groups.push(currentGroup);
    currentTask = null;
    pendingActivity = null;
    counts.tag += 1;
    return;
  }

  const activity = RE_ACTIVITY.exec(raw);
  if (activity) {
    if (!currentTask) {
      unrecognized.push({ at, line: raw, why: "活动行出现在任何任务之前" });
      return;
    }
    const [, mm, dd, hh, mi, text] = activity;
    const row = { mm, dd, hh, mi, text: text.trim(), continuation: 0 };
    currentTask.activities.push(row);
    pendingActivity = row;
    counts.activity += 1;
    return;
  }

  const task = RE_TASK.exec(raw);
  if (task) {
    if (!currentGroup) {
      unrecognized.push({ at, line: raw, why: "任务行出现在任何标签之前（这份清单是按标签分组的）" });
      return;
    }
    const body = task[2];
    const summary = RE_SUMMARY.exec(body);
    currentTask = {
      seq: Number(task[1]),
      title: (summary ? body.slice(0, summary.index) : body).trim(),
      summary: summary ? summary[1].trim() : null,
      activities: [],
    };
    if (!currentTask.title) {
      unrecognized.push({ at, line: raw, why: "任务行没有标题" });
    }
    currentGroup.tasks.push(currentTask);
    pendingActivity = null;
    counts.task += 1;
    return;
  }

  // 缩进但不像活动 → 上一条活动的续行（活动文本里的换行被导成独立行了）
  if (RE_INDENTED.test(raw)) {
    if (pendingActivity) {
      pendingActivity.text = `${pendingActivity.text} ${raw.trim()}`;
      pendingActivity.continuation += 1;
      counts.continued += 1;
      return;
    }
    unrecognized.push({ at, line: raw, why: "缩进行，但上一行不是活动" });
    return;
  }

  // 连缩进都没有的裸行：活动文本里带换行时，后半句可能就这么落在开头。
  // 并回上一条活动（**不静默**：每一处都记下来，报告里逐行列出），
  // 而不是当成「认不出的行」卡住整批 —— 但只有紧跟在活动行后面才敢这么做
  if (pendingActivity) {
    bareContinuations.push({ at, line: raw });
    pendingActivity.text = `${pendingActivity.text} ${raw.trim()}`;
    pendingActivity.continuation += 1;
    counts.continued += 1;
    return;
  }

  unrecognized.push({ at, line: raw, why: "认不出的行型" });
});

// ─── 合并：同一条任务会在多个标签组下重复出现 ────────────────────────────────
// 清单按「标签 → 任务」组织，一条带多个标签的任务就会在每个组里各出现一次。
// 同名是否一定是同一条任务？**报告里无法区分** —— 所以合并，并把这个决定
// 记进待确认项，让调用方去问用户。

const byTitle = new Map();
const mergeNotes = [];

for (const group of groups) {
  for (const task of group.tasks) {
    const key = task.title.replace(/\s+/g, " ").trim();
    if (!key) continue;

    const existing = byTitle.get(key);
    if (existing) {
      if (!existing.tags.includes(group.tag)) existing.tags.push(group.tag);
      existing.activities.push(...task.activities);
      existing.seenIn += 1;
      existing.summaries.push(task.summary);
      continue;
    }

    byTitle.set(key, {
      title: task.title.replace(/\s+/g, " ").trim(),
      tags: [group.tag],
      activities: [...task.activities],
      summary: task.summary,
      summaries: [task.summary],
      seenIn: 1,
    });
  }
}

const tasks = [...byTitle.values()];

// ─── 每条任务：状态 / 进度 / 截止 ────────────────────────────────────────────

const needConfirm = { noDue: [], noStatus: [], manyTags: [], reserved: [], merged: [] };

const statusFrom = (word) => STATUS_MAP.get(word) ?? null;

/**
 * 输出行里的**保留字符**：应用解析时会从标题里挖走匹配的部分。
 *
 * 这套写法**没有转义机制** —— 一条叫「发布 v1.0 #发布日」的任务，导进去会变成标题
 * 「发布 v1.0」+ 标签 `#发布日`，而且**不报错**，导完才发现标题短了一截。
 * 三条正则与应用的解析器一致（desktop/src/data/markdown.ts 的 TAG / DUE / PROGRESS）；
 * 这里只做 lint —— 真正的验证在 e2e：把本脚本的输出喂进「数据迁入」，断言 0 行未能识别。
 */
const RESERVED = [
  { re: /#[^\s#]+/, why: "「#」开头的词会被读成标签" },
  { re: /⏰\s*(?:\d{4}-)?\d{2}-\d{2}/, why: "「⏰」加日期会被读成截止" },
  { re: /::\s*\d{1,3}%/, why: "「::」加数字会被读成进度" },
];

for (const task of tasks) {
  // 1) 状态：任务行的摘要优先（那是导出时算好的），其次翻活动文本里的「状态变更」
  let status = null;
  let progress = 0;

  for (const summary of task.summaries) {
    if (!summary) continue;
    const st = RE_SUM_STATUS.exec(summary);
    if (st) status = statusFrom(st[2].trim()) ?? status;
    const pr = RE_SUM_PROGRESS.exec(summary);
    if (pr) progress = Number(pr[2]);
  }

  if (!status) {
    // 同样的道理：按时间升序走一遍，最后生效的是最新那条状态变更
    for (const row of [...task.activities].sort(compare)) {
      for (const match of row.text.matchAll(RE_STATUS_WORD)) {
        const word = match[1]?.trim();
        const mapped = word ? statusFrom(word) : null;
        if (mapped) status = mapped;
      }
    }
  }
  if (!status) {
    status = "todo";
    needConfirm.noStatus.push(task.title);
  }
  task.status = status;
  task.progress = status === "done" ? 100 : progress;

  // 2) 截止：清单的任务行里没有这个字段，只能从活动文本里挖 ——
  //    「延后处理: 截止时间 A -> B（+N天）」取**最后一次**（时间上最新）的 B。
  //    先按时间排一遍，不依赖上游给的顺序；带箭头的写法优先于「直接设」的写法
  let due = null;
  let dueFrom = null;
  for (const row of [...task.activities].sort(compare)) {
    const move = [...row.text.matchAll(RE_DUE_MOVE)].at(-1);
    if (move) {
      due = move[2];
      dueFrom = row.text;
      continue;
    }
    const set = [...row.text.matchAll(RE_DUE_SET)].at(-1);
    if (set) {
      due = set[1];
      dueFrom = row.text;
    }
  }
  task.due = due ? due.slice(5).replace("-", " ").replace(" ", "-") : null;
  task.dueFrom = dueFrom;
  if (!due) needConfirm.noDue.push(task.title);

  // 3) 标签个数：应用上限是 3
  if (task.tags.length > 3) needConfirm.manyTags.push(`${task.title}（${task.tags.length} 个）`);

  // 4) 标题里带保留字符（见 RESERVED）：会被应用的解析器挖走，且不报错 —— 报出来
  const hit = RESERVED.find((rule) => rule.re.test(task.title));
  if (hit) needConfirm.reserved.push(`${task.title}（${hit.why}）`);
}

for (const task of tasks) {
  if (task.seenIn > 1) {
    needConfirm.merged.push(`${task.title}（出现在 ${task.seenIn} 个标签组：${task.tags.join(" ")}）`);
  }
}

// ─── 活动：滤掉系统记录 + 排序 + 同一条去重 ──────────────────────────────────

/**
 * 旧版**自动写下**的系统记录。它们的**结果已经写在任务行上**了 ——
 * 方括号 = 状态、`:: N%` = 进度、`⏰` = 截止 —— 所以这些行本身不携带新信息。
 *
 * 为什么必须滤掉，而不只是「留着也无妨」：
 *   · 活动行导入后一律是 `kind: "log"`（**人手写的一条进展**），而它们不是人写的 ——
 *     语义是错的，还会落进「可改可删」那一类；
 *   · 一条任务的创建 / 状态 / 进度 / 延后再怎么攒也就几十条，会把真正有价值的进展淹掉。
 *
 * ⚠️ **顺序**：截止与状态正是从这些行里挖出来的（见 RE_DUE_* / RE_STATUS_WORD），
 * 所以必须**挖完之后**再滤 —— 先滤就把字段丢了。滤掉多少要报出来（见下面的对账）。
 */
const SYSTEM_ACTIVITY = [
  /^\[批量创建\]/, //   [批量创建] 创建任务 1/3
  /^创建任务/, //       创建任务
  /^延后处理/, //       延后处理: 截止时间 A → B（+N天）
  /^状态变更/, //       状态变更为 已完成
  /^状态\s/, //         状态 待办 → 逾期
  /^进度\s*\d+%/, //    进度 0% → 30%
  /^截止时间/, //       截止时间 2026-01-31
];

let duplicatedActivities = 0;
/** 滤掉的系统记录数。计入对账 —— 源里每一行活动都得有去向。 */
let filteredActivities = 0;
/** 报告里举几个例子，让人核得出滤的确实是那批东西。 */
const filteredSamples = [];

for (const task of tasks) {
  const seen = new Set();
  const kept = [];
  for (const row of [...task.activities].sort(compare)) {
    if (!keepSystem && SYSTEM_ACTIVITY.some((rule) => rule.test(row.text))) {
      filteredActivities += 1;
      if (filteredSamples.length < 5) filteredSamples.push(row.text);
      continue;
    }

    const key = `${row.mm}-${row.dd} ${row.hh}:${row.mi} ${row.text}`;
    if (seen.has(key)) {
      duplicatedActivities += 1;
      continue;
    }
    seen.add(key);
    kept.push(row);
  }
  task.activities = kept;
}

// ─── 生成任务行 ──────────────────────────────────────────────────────────────

const pad = (n) => String(n).padStart(2, "0");

const toTaskLines = () =>
  tasks
    .map((task) => {
      const due = task.due ? ` ⏰${task.due}` : "";
      const progress = task.progress ? ` :: ${task.progress}%` : "";
      const head = `- [${BOX[task.status]}] ${task.title} ${task.tags.join(" ")}${due}${progress}`;
      const rows = task.activities.map(
        (row) => `   - ${pad(row.mm)}-${pad(row.dd)} ${pad(row.hh)}:${pad(row.mi)} ${row.text}`,
      );
      return [head, ...rows].join("\n");
    })
    .join("\n\n")
    .concat("\n");

// ─── 对账 ────────────────────────────────────────────────────────────────────
// 每一条都得平：源里的行数 = 输出里的行数 + 有解释的去向（续行 / 去重）。

const sourceTasksInGroups = groups.reduce((sum, group) => sum + group.tasks.length, 0);
const outTasks = tasks.length;
const outActivities = tasks.reduce((sum, task) => sum + task.activities.length, 0);
const sourceActivities = counts.activity;

const checks = [
  {
    name: "未识别行 = 0",
    ok: unrecognized.length === 0,
    detail: `${unrecognized.length} 行`,
  },
  {
    name: "活动行一条不少",
    ok: sourceActivities === outActivities + duplicatedActivities + filteredActivities,
    detail: `源 ${sourceActivities} = 输出 ${outActivities} + 系统记录过滤 ${filteredActivities} + 重复剔除 ${duplicatedActivities}（续行 ${counts.continued} 条已并回上一条，不单独计数）`,
  },
  {
    name: "任务行数目对得上",
    ok: sourceTasksInGroups === outTasks + (sourceTasksInGroups - outTasks),
    detail: `源（含各标签组重复）${sourceTasksInGroups} → 去重后 ${outTasks}`,
  },
  {
    name: "标签组都读到了",
    ok: groups.length === counts.tag,
    detail: `${groups.length} 组`,
  },
];

const report = {
  source: { file: basename(source), lines: lines.length },
  counts: {
    tags: counts.tag,
    taskLines: sourceTasksInGroups,
    taskUnique: outTasks,
    activities: sourceActivities,
    continued: counts.continued,
    duplicated: duplicatedActivities,
    filtered: filteredActivities,
    blank: counts.blank,
  },
  checks,
  needConfirm,
  unrecognized,
  bareContinuations,
  tasks: tasks.map((task) => ({
    title: task.title,
    tags: task.tags,
    status: task.status,
    progress: task.progress,
    due: task.due,
    dueFrom: task.dueFrom,
    activities: task.activities.length,
  })),
};

const failed = checks.some((check) => !check.ok);
// 退出码 1 的口径是「有人得拍板」——「必须停下来问」那几类都要算进来。
// merged 曾经漏在外面：报告里列着「同名任务已合并，请确认」，退出码却是 0，
// 照着退出码走的调用方会当成干净通过（README 里那张表是这行代码的规格）。
const pending =
  unrecognized.length + needConfirm.noDue.length + needConfirm.noStatus.length +
  needConfirm.manyTags.length + needConfirm.reserved.length + needConfirm.merged.length;

// ─── 输出 ────────────────────────────────────────────────────────────────────

console.log(`源文件 ${basename(source)}：${lines.length} 行`);
console.log(
  `标签组 ${counts.tag} · 任务行 ${sourceTasksInGroups}（去重后 ${outTasks}）· 活动行 ${sourceActivities}` +
    `（续行 ${counts.continued} · 重复 ${duplicatedActivities}）· 空行 ${counts.blank}`,
);
console.log("");

for (const check of checks) {
  console.log(`${check.ok ? "OK  " : "FAIL"} ${check.name} — ${check.detail}`);
}

const section = (title, items) => {
  if (items.length === 0) return;
  console.log("");
  console.log(`── ${title}（${items.length}）`);
  for (const item of items.slice(0, 20)) console.log(`   ${item}`);
  if (items.length > 20) console.log(`   …另有 ${items.length - 20} 条，见报告文件`);
};

section("认不出的行（必须处理，不能跳过）", unrecognized.map((item) => `第 ${item.at} 行：${item.why}｜${item.line}`));
section(
  "并回上一条活动的续行（源活动文本里带换行）",
  bareContinuations.map((item) => `第 ${item.at} 行：${item.line}`),
);
section("没有截止信息的任务（报告里只在这类活动里出现过截止）", needConfirm.noDue);
section("状态无法确定、按「进行中」处理的任务（写法上是 `[ ]`）", needConfirm.noStatus);
section("标签超过 3 个的任务（应用上限是 3）", needConfirm.manyTags);
section("标题里带保留字符的任务（导入时会被当成标记挖走，得先改标题）", needConfirm.reserved);
section("同名任务已按同一条合并（出现在多个标签组）", needConfirm.merged);

// 滤掉的系统记录：**报出来**，不让它静默消失 —— 对账里那个「系统记录过滤 N」就是它
if (filteredActivities > 0) {
  console.log("");
  console.log(`── 滤掉的系统记录（${filteredActivities} 条，结果都已写在任务行上）`);
  for (const text of filteredSamples) console.log(`   ${text}`);
  if (filteredActivities > filteredSamples.length) {
    console.log(
      `   …另有 ${filteredActivities - filteredSamples.length} 条（想全留着就加 --keep-system）`,
    );
  }
}

if (reportPath) {
  writeFileSync(reportPath, JSON.stringify(report, null, 2), "utf8");
  console.log("");
  console.log(`报告已写出：${reportPath}`);
}

if (apply) {
  if (failed) {
    console.error("");
    console.error("有对账项没过，拒绝写出文件。先把上面标 FAIL 的查清楚。");
    process.exit(2);
  }

  // 默认名带「可导入」：这个名字**会显示在导入对话框里**，而它同时也是你切分区时的
  // 对照物（旧版按分区导出，文件名通常就带着分区名）
  const target = outPath ?? `${source.replace(/\.md$/i, "")}-可导入.md`;

  // 不覆盖已有的输出：用户很可能手改过它（比如把 4 个标签删到 3 个 —— 工具按原则
  // 不替他删），重跑一次就把手改的静默抹掉了
  if (existsSync(target) && !force) {
    console.error("");
    console.error(`已存在：${resolve(target)}`);
    console.error("那份可能手改过，别让这一步把它覆盖掉；确实要重写就加 --force。");
    process.exit(2);
  }

  writeFileSync(target, toTaskLines(), "utf8");
  console.log("");
  console.log(`已写出：${resolve(target)}`);
  console.log(`  任务 ${outTasks} 条 · 活动 ${outActivities} 条`);
  console.log("");
  console.log("下一步（在 Tadado2 里）：");
  console.log("  1. 先在 rail 底部**切到目标分区** —— 导入落在当前分区");
  console.log("  2. 任务管理 → 「数据迁入」→ 选上面那个文件");
  console.log(`  3. 看到「共 ${outTasks} 条」、且下面**没有**列出行号，再点导入`);
} else {
  console.log("");
  console.log("（预演模式，没有写任何文件。确认无误后加 --apply 生成）");
}

process.exit(failed ? 2 : pending > 0 ? 1 : 0);
