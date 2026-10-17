// ─────────────────────────────────────────────────────────────────────────────
// 「进度」与「状态」的唯一口径。
//
// 背景（2026-10-16 用户报的 BUG）：自动归档只认 `status === "done"`（见 store 的
// refreshArchive），而「把进度拖到 100%」从来不参与这个判据 —— 于是一条「结束日已过、
// 进度 100%」的任务被 refreshOverdue 标成「逾期」之后，永远收不进归档；列表上行首还挂着
// 一枚「红色 ✓」（颜色说状态、形状说进度，见 tasks.ts 的 progressDot），用户读到的是
// 「这条已经做完了」。用户实测反证：手动点一下「已完成」就**当场**归档 —— 缺的正是
// 「进度满」到「已完成」这一步连接。
//
// 所以这里把两者定成**一个双向一致的口径**：
//   · 进度满 100%       ⇒ 已完成（写一条 status 活动）；
//   · 进度退回 100% 以下 ⇒ 退回「进行中」（结束日已过则由 store 的 refreshOverdue 标逾期）；
//   · 状态被改回未完成   ⇒ 进度退到「完成前那一格」（rollbackProgressForStatus）。
//
// 为什么放 data/ 而不是 pages/shared.ts：store 的自愈扫描（refreshProgressStatus）要复用
// 同一份规则，而数据层不该反向依赖页面层。pages/shared.ts 原样转出，各页面继续从 shared
// 拿（先例：data/time.ts 与 shared.ts 顶部那排 `export { ... } from "../data/time"`）。
//
// ⚠️ 这一组全是**纯函数**：不广播（不 import store）、不落盘。写盘与广播仍由调用方的
//    dataChanged() 统一收口一次。三个函数**互不调用**（coreSetStatus 不碰进度、回退函数
//    不碰状态），且都以「当前值」为输入、只在矛盾时动手 —— 幂等：连着跑两遍，第二遍一定
//    什么都不做（自愈扫描靠这条收敛）。
// ─────────────────────────────────────────────────────────────────────────────

import { nowStamp } from "./time";
import type { Activity, StatusName, Task, TaskStatus } from "./types";

/**
 * 状态文案（**下标是 `StatusName` 而不是 `TaskStatus`**）。
 *
 * 「待办」作为当前状态已经删了（见 types.ts），但活动记录里还写着它（`from: "todo"`），
 * 时间线上要照原样显示「待办 → 进行中」。所以文案表里保留这一格。
 */
export const STATUS_LABEL: Record<StatusName, string> = {
  overdue: "逾期",
  todo: "待办",
  doing: "进行中",
  done: "已完成",
};

/** 进度满格的那一格。判据只此一处，别在别处再写字面量 100。 */
export const FULL_PROGRESS = 100;

/**
 * 只改**状态**：写 `task.status` 并往活动时间线补一条 `status` 记录。不广播、不落盘。
 *
 * `at` 默认「此刻」；自愈扫描会传别的值（完成日取结束日，理由见 store 的
 * refreshProgressStatus）。`from === to` 直接返回 false —— 幂等的第一道保证。
 *
 * 活动按**时间倒序**插，不是一律 unshift：自愈补的那条时间戳可能早于已有的记录，
 * 无脑 unshift 会让时间线倒着走（先显示 10-15、再显示 10-10）。
 */
export function coreSetStatus(
  task: Task,
  to: TaskStatus,
  at: number = nowStamp(),
  auto = false,
): boolean {
  if (task.status === to) return false;
  const from = task.status;
  task.status = to;
  insertActivity(task, {
    at,
    kind: "status",
    from,
    to,
    text: `${STATUS_LABEL[from]} → ${STATUS_LABEL[to]}`,
    // `auto` 表示这条是进度派生出来的（见 types.ts 的 Activity 注释）。只有真的时候才写，
    // 免得存档里每条状态记录都多一个 `"auto": false`
    ...(auto ? { auto: true as const } : {}),
  });
  return true;
}

/** 按「新的在前」把一条活动放到它该在的位置（时间戳相等时排在已有的那条前面）。 */
function insertActivity(task: Task, activity: Activity): void {
  const index = task.activities.findIndex((item) => item.at < activity.at);
  if (index < 0) task.activities.push(activity);
  else task.activities.splice(index, 0, activity);
}

/**
 * 让**状态**跟上进度：满格 ⇒ 已完成；不满格 ⇒ 不该是已完成（退回「进行中」）。
 *
 * 返回本次是否真的改了状态。注意「退回」之后它不一定停在「进行中」：结束日已过的话，
 * 紧接着的 refreshOverdue 会把它标成「逾期」—— 那是对的，口径是「逾期 = 未完成 + 过了截止」。
 */
export function syncStatusForProgress(task: Task, at: number = nowStamp()): boolean {
  // 两条都是**进度派生**的（拖满 / 退回），标成 auto：时间线里不再单列一条
  // 「已完成 → 进行中」，但完成日与归档档位仍读得到它
  if (task.progress >= FULL_PROGRESS) return coreSetStatus(task, "done", at, true);
  if (task.status === "done") return coreSetStatus(task, "doing", at, true);
  return false;
}

/**
 * 让**进度**跟上状态：状态从「已完成」退回来时，进度得跟着退。
 *
 * 为什么必须有（2026-10-16 一并修的）：双向口径之下，只把状态改回「进行中」而进度仍是
 * 100%，同一次 dataChanged 里的 syncStatusForProgress 会立刻把它改回「已完成」——
 * 于是在右键菜单 / 总览勾选框 / 抽屉状态按钮上点「标记未完成」成了空操作。
 *
 * 退到「**完成前那一格**」：活动时间线里最新的「值 < 100 的进度记录的 `to`」。
 *  · 拖到 100% 那条记录是 `{from: 80, to: 100}`：它的 `to` 是 100（跳过），落在前一条
 *    `{from: 60, to: 80}` 的 `to` = 80 —— 正好是「完成前那一格」；
 *  · 「点完成就把进度静默写成 100」的情况（老 setTaskStatus）**根本没写进度记录**，
 *    所以不能取「最新那条的 `from`」（那会退到更早的一格）；
 *  · 一条进度记录都没有（`[x]` 导入进来的老数据）就归 0。
 *
 * 返回本次是否真的改了进度。**不写活动**：这次动作由那条 `status` 活动记着。
 */
export function rollbackProgressForStatus(task: Task): boolean {
  let next = 0;
  for (const activity of task.activities) {
    if (activity.kind !== "progress") continue;
    if (activity.to >= FULL_PROGRESS) continue;
    next = activity.to;
    break;
  }
  if (task.progress === next) return false;
  task.progress = next;
  return true;
}

/**
 * **进度写入的唯一入口**：改 `task.progress` 并让状态跟着走（100% ⇒ 已完成、退回 ⇒ 进行中）。
 *
 * 返回本次是否真的改了什么（进度或状态任一变了都算）。**不写活动、不广播、不落盘** ——
 * 活动由调用方写（抽屉要把「说明」和进度记在**同一条**记录里，见 taskForm 的
 * progressControl），广播与落盘仍由 dataChanged() 收口。
 *
 * 钳位为什么收在这里：原来 md 导入、编辑历史进度记录、md 应用三条路各自 `Math.min(100, …)`
 * 一次，迟早分叉；`Number.isNaN` 也在这里兜住（数字框被清空时是 NaN）。
 */
export function setProgress(task: Task, value: number, autoStatus = true): boolean {
  const next = Math.max(
    0,
    Math.min(FULL_PROGRESS, Math.round(Number.isNaN(value) ? 0 : value)),
  );
  const moved = task.progress !== next;
  task.progress = next;
  // `autoStatus = false` 只给**显式改状态**用（`setTaskStatus` 置「已完成」时要先把
  // 进度写成 100，再由它自己写一条真实的 status 活动）—— 否则那条会被标成系统记录
  const synced = autoStatus ? syncStatusForProgress(task) : false;
  return moved || synced;
}
