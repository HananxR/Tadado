// ─────────────────────────────────────────────────────────────────────────────
// 存储的版本，与读入口的归位。
//
// 为什么要有这一层：业务字段整条塞在 `tasks` 表的 `data` 列里（见 db.ts 的
// 注释），于是「表结构」和「列里的 JSON 结构」是两件会各自演进的东西 ——
//
//   · **表结构** → `PRAGMA user_version` + MIGRATIONS：一套线性链，启动时顺序跑，
//     跑完把版本号写回文件头。这套照搬归档分支上 PySide6 版的
//     `src/models/migrations.py`（那边跑到 8，还有配套文档
//     `docs/database-migration-technique.md` 讲清了为什么这么选）。规矩也照搬：
//     **只能加不能改** —— 只 ADD COLUMN，不删列、不改已有列的类型。
//     `setVersion` 那条写完会立刻读回核对（见 db.ts 里的注释：PRAGMA 万一被忽略
//     是静默的，而机制静默退化要等很久以后才会暴露）。
//
//   · **列里的 JSON** → 读入口的 normalizeTasks：缺字段给默认值、类型不对的
//     救回来，救不回来的丢掉并计数。版本号管不到列里面，这一层必须单独有。
//
// 两条缺一不可：只有版本号，老记录里新加的字段还是 undefined，界面照样炸；
// 只有兜底，就没人知道「这一版的库该长什么样」，久了连要兜什么都不清楚。
// ─────────────────────────────────────────────────────────────────────────────

import { dayNumber, parseStampText, stampOf, todayMonthDay } from "./time";
import type { Activity, MonthDay, Task, TaskStatus, Urgency } from "./types";

/** 当前 schema 版本。**必须与 MIGRATIONS 的链尾一致**（改它就要加一条迁移）。 */
export const SCHEMA_VERSION = 1;

export const TASKS_TABLE = "tasks";
export const KV_TABLE = "kv";

// ─── 迁移链 ──────────────────────────────────────────────────────────────────

/**
 * 迁移能用的最小接口：SQLite 与浏览器（localStorage）各实现一份。
 *
 * 浏览器后端没有表，`relational` 为 false —— SQL 步骤会被跳过，只跑数据层面的
 * 那部分。这样同一条链在两种后端下都成立，e2e 也才能真的验一遍迁移（它跑在
 * 浏览器里，走的正是 localStorage 那条路）。
 */
export interface MigrationApi {
  relational: boolean;
  version(): Promise<number>;
  setVersion(version: number): Promise<void>;
  exec(sql: string): Promise<void>;
}

export interface MigrationStep {
  from: number;
  to: number;
  /** 表结构变更（仅关系型后端执行）。 */
  sql?: string[];
  /** 数据层面的搬运，两种后端都跑。 */
  run?: (api: MigrationApi) => Promise<void>;
}

const CREATE_TASKS = `CREATE TABLE IF NOT EXISTS ${TASKS_TABLE} (
  id TEXT PRIMARY KEY NOT NULL,
  partition TEXT NOT NULL,
  archived INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL,
  start TEXT NOT NULL,
  end TEXT NOT NULL,
  data TEXT NOT NULL
)`;

const CREATE_KV = `CREATE TABLE IF NOT EXISTS ${KV_TABLE} (
  key TEXT PRIMARY KEY NOT NULL,
  value TEXT NOT NULL
)`;

/**
 * 迁移注册表：`from` 必须等于上一条的 `to`，不能跳、不能分支。
 *
 * `0 → 1` 就是「确保这套表在」：**老库（没有版本号，user_version 读出来是 0）
 * 也会走这一步**，于是它一启动就拿到了版本号，而数据一条都没动 —— 这就是存量
 * 库被带上版本的方式。以后加字段就在后面追加 `(1, 2)`，那条里写 ALTER 语句
 * 或读旧格式搬数据的函数。
 */
export const MIGRATIONS: MigrationStep[] = [
  { from: 0, to: 1, sql: [CREATE_TASKS, CREATE_KV] },
];

/** 顺序执行待跑的迁移，返回最终版本。 */
export async function runMigrations(api: MigrationApi): Promise<number> {
  let current = await api.version();

  for (const step of MIGRATIONS) {
    if (step.from !== current) continue;
    if (api.relational && step.sql) {
      for (const sql of step.sql) await api.exec(sql);
    }
    await step.run?.(api);
    await api.setVersion(step.to);
    current = step.to;
  }

  return current;
}

// ─── 读入口归位：data 列里的 JSON ────────────────────────────────────────────

export interface NormalizeReport {
  tasks: Task[];
  /** 被修过的字段个数（缺值补默认、类型纠正）。 */
  fixed: number;
  /** 整条丢掉的任务数 —— 连 id 或标题都没有的，定位不了也认不出。 */
  dropped: number;
}

const STATUSES: TaskStatus[] = ["todo", "doing", "done", "overdue"];
const isStatus = (value: unknown): value is TaskStatus =>
  STATUSES.includes(value as TaskStatus);
const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);
const isStamp = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value);

/**
 * 分区字段缺失 / 不合法时的落点。
 *
 * 不 import `partitions.ts` 取真值：那个模块要 `db.ts` 的读写设置，从这里引进去
 * 就成环了（db → schema → partitions → db）。为一句兜底绕一圈依赖不值当。
 */
const FALLBACK_PARTITION = "work";

function normalizeMonthDay(
  value: unknown,
  fallback: MonthDay,
): { value: MonthDay; fixed: boolean } {
  if (Array.isArray(value) && value.length === 2) {
    const [month, day] = value;
    if (
      typeof month === "number" &&
      typeof day === "number" &&
      month >= 1 &&
      month <= 12 &&
      day >= 1 &&
      day <= 31
    ) {
      return { value: [month, day], fixed: false };
    }
  }
  return { value: fallback, fixed: true };
}

/**
 * 一条活动。
 *
 * `at` 从展示串换成时间戳那次改造（见 types.ts 的 At）之前存下的数据就是走这里：
 * 「昨天 17:20」这类句子换成真实时刻，换不出来的落到任务创建日的上午 —— 有损，
 * 但比留个 NaN 强（那个曾经一路显示成 `NaN-NaN 05:42` 并进了导出文件）。
 */
function normalizeActivity(raw: unknown, fallbackStamp: number): { value: Activity | null; fixed: boolean } {
  if (!isRecord(raw)) return { value: null, fixed: false };

  const body = typeof raw.text === "string" ? raw.text : "";
  const at = isStamp(raw.at) ? raw.at : parseStampText(String(raw.at ?? ""), fallbackStamp);
  const fixed = !isStamp(raw.at) || typeof raw.text !== "string";
  const kind = raw.kind;

  if (kind === "create") return { value: { at, text: body, kind: "create" }, fixed };

  if (kind === "status" && isStatus(raw.from) && isStatus(raw.to)) {
    return { value: { at, text: body, kind: "status", from: raw.from, to: raw.to }, fixed };
  }

  if (kind === "progress" && typeof raw.from === "number" && typeof raw.to === "number") {
    return { value: { at, text: body, kind: "progress", from: raw.from, to: raw.to }, fixed };
  }

  // 认不出的类型退成「手写的一条进展」：内容还在，只是不再声称自己是状态 / 进度
  // 变化 —— 假装它是，会让「本周完成」这类统计算错
  if (raw.edited === true) {
    return { value: { at, text: body, kind: "log", edited: true }, fixed: fixed || kind !== "log" };
  }
  return { value: { at, text: body, kind: "log" }, fixed: fixed || kind !== "log" };
}

function normalizeTask(raw: unknown): { value: Task | null; fixed: number } {
  if (!isRecord(raw)) return { value: null, fixed: 0 };

  const id = typeof raw.id === "string" && raw.id ? raw.id : null;
  const title = typeof raw.title === "string" ? raw.title : null;
  // 没有 id 就定位不了、没有标题就认不出 —— 这两条救不回来，只能整条丢
  if (id === null || title === null) return { value: null, fixed: 0 };

  let fixed = 0;
  const today = todayMonthDay();

  const created = normalizeMonthDay(raw.created, today);
  // 起止缺了就用创建日兜底：一条没有区间的任务在甘特图上没处画，
  // 但它比「丢掉」有价值得多
  const start = normalizeMonthDay(raw.start, created.value);
  const end = normalizeMonthDay(raw.end, created.value);
  fixed += Number(created.fixed) + Number(start.fixed) + Number(end.fixed);

  const status = isStatus(raw.status) ? raw.status : "todo";
  if (!isStatus(raw.status)) fixed += 1;

  const tags = Array.isArray(raw.tags)
    ? raw.tags.filter((tag): tag is string => typeof tag === "string")
    : [];
  if (!Array.isArray(raw.tags)) fixed += 1;

  const related = Array.isArray(raw.related)
    ? raw.related.filter((item): item is string => typeof item === "string")
    : [];
  if (!Array.isArray(raw.related)) fixed += 1;

  const progress = Math.max(
    0,
    Math.min(100, Math.round(typeof raw.progress === "number" && Number.isFinite(raw.progress) ? raw.progress : 0)),
  );
  if (progress !== raw.progress) fixed += 1;

  const rawUrgency = typeof raw.urgency === "number" ? Math.round(raw.urgency) : 3;
  const urgency = (rawUrgency >= 0 && rawUrgency <= 3 ? rawUrgency : 3) as Urgency;
  if (urgency !== raw.urgency) fixed += 1;

  const partition =
    typeof raw.partition === "string" && raw.partition ? raw.partition : FALLBACK_PARTITION;
  if (partition !== raw.partition) fixed += 1;

  const fallbackStamp = stampOf(dayNumber(created.value), 9 * 60);
  const activities: Activity[] = [];
  if (Array.isArray(raw.activities)) {
    for (const item of raw.activities) {
      const done = normalizeActivity(item, fallbackStamp);
      if (done.value) activities.push(done.value);
      if (done.fixed) fixed += 1;
    }
  } else {
    fixed += 1;
  }

  return {
    value: {
      id,
      title,
      status,
      tags,
      due: typeof raw.due === "string" ? raw.due : null,
      at: typeof raw.at === "string" ? raw.at : null,
      start: start.value,
      end: end.value,
      progress,
      urgency,
      created: created.value,
      archived: raw.archived === true,
      partition,
      activities,
      related,
    },
    fixed,
  };
}

/** 一批存下来的任务 → 能直接进内存的那批，附带「修了几处、丢了几条」。 */
export function normalizeTasks(raw: unknown): NormalizeReport {
  if (!Array.isArray(raw)) return { tasks: [], fixed: 0, dropped: 0 };

  const report: NormalizeReport = { tasks: [], fixed: 0, dropped: 0 };
  for (const item of raw) {
    const done = normalizeTask(item);
    if (!done.value) {
      report.dropped += 1;
      continue;
    }
    report.tasks.push(done.value);
    report.fixed += done.fixed;
  }
  return report;
}

// ─── kv 值的取证 ─────────────────────────────────────────────────────────────
// 设置项也存在 kv 里，值同样是 JSON —— 结构变了同样只有读入口这一道防线。
// 以前是「读出来直接用」：存档要是变成了数组，`saved[id]` 全是 undefined，
// 界面上一片空白却不报错。这几个小工具把「形状不对就当没存过」写成一句话。

function pickByType<T extends string | number>(
  value: unknown,
  keep: (item: unknown) => item is T,
): Record<string, T> {
  if (!isRecord(value)) return {};
  const out: Record<string, T> = {};
  for (const [key, item] of Object.entries(value)) {
    if (keep(item)) out[key] = item;
  }
  return out;
}

/** 分区口令：`{ 分区id: 口令 }`。 */
export const asStringRecord = (value: unknown): Record<string, string> =>
  pickByType(value, (item): item is string => typeof item === "string");

/** 空闲锁定 / 自动归档：`{ 分区id: 数字 }`。 */
export const asNumberRecord = (value: unknown): Record<string, number> =>
  pickByType(
    value,
    (item): item is number => typeof item === "number" && Number.isFinite(item) && item >= 0,
  );

/** 分区列表：`[{ id, name }]`。形状不对返回 null，调用方据此保留内置那几个。 */
export function asPartitionList(value: unknown): { id: string; name: string }[] | null {
  if (!Array.isArray(value) || value.length === 0) return null;

  const out: { id: string; name: string }[] = [];
  for (const item of value) {
    if (!isRecord(item)) continue;
    const id = typeof item.id === "string" ? item.id : "";
    const name = typeof item.name === "string" ? item.name : "";
    if (id && name) out.push({ id, name });
  }
  return out.length > 0 ? out : null;
}
