// ─────────────────────────────────────────────────────────────────────────────
// 持久化。
//
// 原版用 SQLite 存数据，桌面端继续用同一个东西 —— 通过 tauri-plugin-sql 在前端
// 直连。不再于 Rust 侧写一遍同样的 SQL：那只是把一份查询逻辑抄成两份，
// 以后改字段要同时改两个地方，迟早对不上。
//
// 纯浏览器预览（`npm run dev`，没有 Tauri 宿主）拿不到插件，降级到 localStorage。
// 两个后端对外行为一致：读出来是 Task[]，写进去是全量覆盖。
//
// 为什么敢全量覆盖：数据量是「一个人的任务」，几十到几千条，一次事务写完是
// 毫秒级；换成按 id 增量更新，就要维护脏标记、处理删除，代码量翻几倍而收益是零。
//
// 表结构与版本在 data/schema.ts：`PRAGMA user_version` + 线性迁移链，
// 以及读入口的字段归位（data 列里那坨 JSON 只有它能管）。
// ─────────────────────────────────────────────────────────────────────────────

import { isTauri } from "@tauri-apps/api/core";
import Database from "@tauri-apps/plugin-sql";
import {
  KV_TABLE,
  TASKS_TABLE,
  normalizeTasks,
  runMigrations,
  type MigrationApi,
  type NormalizeReport,
} from "./schema";
import type { Task } from "./types";

const LS_KEY = "tadado.tasks.v1";
const LS_KV = "tadado.kv.";
/** 浏览器后端的 schema 版本（SQLite 那边写在文件头的 user_version 里）。 */
const LS_VERSION = "tadado.schema.version";

/** 写盘防抖：拖动进度条会连着触发几十次 dataChanged。 */
const DEBOUNCE_MS = 400;

/**
 * `error` 是一个**终态**：宿主在、库却打不开。
 *
 * 以前没有这个状态 —— 连库的 catch 把「库打不开」和「浏览器里没有插件」当成
 * 同一件事，一律降级到 localStorage。后果是：库静静地不被读取，界面上一个字
 * 不说；此后的写入全落到 localStorage，用户的数据库被劈成两半，而表面上一切
 * 正常（详情见 connect 里的注释）。
 */
type Backend = "sqlite" | "local" | "error" | "unknown";
type Row = { data: string };

const describe = (error: unknown): string =>
  error instanceof Error ? error.message : String(error);

let db: Database | null = null;
let backend: Backend = "unknown";
let timer: number | undefined;
/** 浏览器后端是否已经跑过迁移（惰性，第一次读写时做）。 */
let localMigrated = false;
/** 存储读不出来时的说明。非 null 时调用方**不能**把它当空库处理。 */
let readIssue: string | null = null;
/**
 * 读失败之后**禁止写入**。
 *
 * 少了这一条，「原样留着」只是句好话：bootStore 起来之后界面继续跑，用户随手
 * 点一下就会触发 dataChanged → 全量覆盖 → 那份还能人工捞回来的存档当场没了。
 */
let writeBlocked = false;

/** 存储出问题的说明；外壳拿它给用户一句人话提示。 */
export const storageIssue = (): string | null => readIssue;

const md = ([month, day]: [number, number]): string =>
  `${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;

// ─── 迁移 ────────────────────────────────────────────────────────────────────

function sqliteApi(conn: Database): MigrationApi {
  return {
    relational: true,
    /**
     * 版本号就是 SQLite 文件头里那个 `user_version`（规范定义的偏移 60–63 字节）。
     *
     * **曾经误判过一次**：早先读库文件读到 0，于是断定「tauri-plugin-sql 上
     * PRAGMA 写不生效」，还把版本号搬进 kv 表。后来发现那是 **WAL 的陈旧视图** ——
     * 应用当时还开着，最新写入躺在 951KB 的 `-wal` 里没 checkpoint；重启之后
     * （关闭时 checkpoint）主文件里就是 1。所以它是生效的，而且跟着数据库文件走
     * （拷贝一份库，版本也跟着走），与 Py 版同一套机制。
     *
     * 教训记在这里：**外部读到的值可能是陈旧视图，别用它推翻一个还在运行的进程**。
     */
    async version() {
      const rows = await conn.select<{ user_version: number }[]>("PRAGMA user_version");
      return Number(rows[0]?.user_version ?? 0) || 0;
    },
    async setVersion(version) {
      // PRAGMA 用不了绑定参数；这里的值只可能来自 MIGRATIONS 里的常量
      await conn.execute(`PRAGMA user_version = ${version}`);

      // 写完立刻在同一条连接上读回来核对 —— 不靠「没报错」当成功。
      // PRAGMA 万一被忽略是**静默**的，而这套机制一旦静默退化（每次启动都从头
      // 跑一遍迁移），只有等某天加了一条破坏性的迁移才会暴露，那时它已经在用户
      // 的库上跑过好几遍了
      const rows = await conn.select<{ user_version: number }[]>("PRAGMA user_version");
      const back = Number(rows[0]?.user_version ?? -1);
      if (back !== version) {
        throw new Error(`schema 版本号写入未生效：写 ${version}，读回 ${back}`);
      }
    },
    async exec(sql) {
      await conn.execute(sql);
    },
  };
}

/** 浏览器后端：没有「库」这回事，版本号只能自己找个 key 存。 */
function localApi(): MigrationApi {
  return {
    relational: false,
    async version() {
      const raw = localStorage.getItem(LS_VERSION);
      const parsed = raw === null ? 0 : Number.parseInt(raw, 10);
      return Number.isFinite(parsed) ? parsed : 0;
    },
    async setVersion(version) {
      localStorage.setItem(LS_VERSION, String(version));
    },
    async exec() {
      // 没有表，SQL 步骤在这条路上是 no-op —— 迁移链照样走，数据层面的那部分照跑
    },
  };
}

async function ensureLocalMigrated(): Promise<void> {
  if (localMigrated) return;
  localMigrated = true;
  await runMigrations(localApi());
}

// ─── 连接 ────────────────────────────────────────────────────────────────────

/**
 * 取连接。三种结果：拿到连接（SQLite）/ 明确降级（浏览器预览）/ 报错终止（库故障）。
 *
 * 判断顺序很重要：**先看有没有宿主，再看库能不能开**。
 * 「没有宿主」是预期路径，不该产生任何告警；「库打不开」是真故障，绝不能降级 ——
 * 降级之后读写另一个地方，用户既看不到自己的数据、也看不到任何提示，
 * 甚至可能在新地方继续记，回头两份数据还得手工合。
 */
async function connect(): Promise<Database | null> {
  if (backend === "local" || backend === "error") return null;
  if (db) return db;

  if (!isTauri()) {
    backend = "local";
    return null;
  }

  try {
    db = await Database.load("sqlite:tadado.data");
    await runMigrations(sqliteApi(db));
    backend = "sqlite";
    return db;
  } catch (error) {
    backend = "error";
    readIssue = `数据库打不开：${describe(error)}`;
    console.error(`[tadado] ${readIssue}`);
    return null;
  }
}

// ─── 任务 ────────────────────────────────────────────────────────────────────

export interface LoadResult {
  /** 任务数组；null 表示**还没有存档**（首次启动 / 新库），调用方据此播种子。 */
  tasks: Task[] | null;
  /** 存档在、但读不出来（损坏 / 库故障）。非 null 时**不能**当空库处理 —— 那等于拿种子把用户的数据盖掉。 */
  issue: string | null;
  /** 读入口修了几处字段（缺值补默认 / 类型纠正）。 */
  fixed: number;
  /** 读入口丢了几条（连 id 或标题都没有的）。 */
  dropped: number;
}

const EMPTY_LOAD: LoadResult = { tasks: null, issue: null, fixed: 0, dropped: 0 };

/** 把归位报告包成读结果，顺手把「修了 / 丢了」记进控制台 —— 静默修复比不修更坏。 */
function fromReport(report: NormalizeReport): LoadResult {
  if (report.fixed > 0 || report.dropped > 0) {
    console.warn(
      `[tadado] 读入口归位：修了 ${report.fixed} 处字段、丢了 ${report.dropped} 条记录（结构对不上的旧数据）`,
    );
  }
  return { tasks: report.tasks, issue: null, fixed: report.fixed, dropped: report.dropped };
}

function broken(issue: string): LoadResult {
  readIssue = issue;
  writeBlocked = true;
  console.error(`[tadado] ${issue}`);
  return { tasks: null, issue, fixed: 0, dropped: 0 };
}

/** 读全部任务。 */
export async function loadTasks(): Promise<LoadResult> {
  const conn = await connect();

  if (conn) {
    try {
      const rows = await conn.select<Row[]>(`SELECT data FROM ${TASKS_TABLE}`);
      if (rows.length === 0) return EMPTY_LOAD;
      return fromReport(normalizeTasks(rows.map((row) => JSON.parse(row.data) as unknown)));
    } catch (error) {
      // 表在、数据却在：读不出来是真的出事了，不能装作「没有存档」
      return broken(`读取失败：${describe(error)}`);
    }
  }

  if (backend === "error") return broken(readIssue ?? "数据库不可用");

  await ensureLocalMigrated();
  const raw = localStorage.getItem(LS_KEY);
  if (raw === null) return EMPTY_LOAD;

  try {
    return fromReport(normalizeTasks(JSON.parse(raw) as unknown));
  } catch (error) {
    // 存档解析不了：**不动它**（留着，人还能去捞），也不当空库 —— 见 store 的处理
    return broken(`本地存档解析失败：${describe(error)}`);
  }
}

/** 写全部任务（防抖）。 */
export function saveTasks(tasks: Task[]): void {
  // 库故障时什么都不写：写到 localStorage 等于把数据劈成两半（见 connect 的注释）；
  // 读失败之后也什么都不写：那份存档要原样留着，人还能去捞
  if (backend === "error" || writeBlocked) return;

  window.clearTimeout(timer);
  timer = window.setTimeout(() => void write(tasks), DEBOUNCE_MS);
}

async function write(tasks: Task[]): Promise<void> {
  if (backend === "error" || writeBlocked) return;

  const conn = await connect();

  if (conn) {
    await conn.execute(`DELETE FROM ${TASKS_TABLE}`);
    for (const task of tasks) {
      await conn.execute(
        `INSERT INTO ${TASKS_TABLE} (id, partition, archived, status, start, end, data)
         VALUES (?, ?, ?, ?, ?, ?, ?)`,
        [
          task.id,
          task.partition,
          task.archived ? 1 : 0,
          task.status,
          md(task.start),
          md(task.end),
          JSON.stringify(task),
        ],
      );
    }
    return;
  }

  await ensureLocalMigrated();
  localStorage.setItem(LS_KEY, JSON.stringify(tasks));
}

// ─── 设置 ────────────────────────────────────────────────────────────────────

/** 读一项设置。没有返回 null。 */
export async function loadSetting<T>(key: string): Promise<T | null> {
  const conn = await connect();

  if (conn) {
    const rows = await conn.select<{ value: string }[]>(
      `SELECT value FROM ${KV_TABLE} WHERE key = ?`,
      [key],
    );
    return rows.length > 0 ? (JSON.parse(rows[0].value) as T) : null;
  }

  if (backend === "error") return null;

  await ensureLocalMigrated();
  const raw = localStorage.getItem(`${LS_KV}${key}`);
  return raw ? (JSON.parse(raw) as T) : null;
}

/** 写一项设置（立刻写，不防抖：设置不是高频操作，丢了比慢了糟）。 */
export async function saveSetting<T>(key: string, value: T): Promise<void> {
  const payload = JSON.stringify(value);
  const conn = await connect();

  if (conn) {
    await conn.execute(
      `INSERT INTO ${KV_TABLE} (key, value) VALUES (?, ?)
       ON CONFLICT(key) DO UPDATE SET value = excluded.value`,
      [key, payload],
    );
    return;
  }

  if (backend === "error") return;

  await ensureLocalMigrated();
  localStorage.setItem(`${LS_KV}${key}`, payload);
}
