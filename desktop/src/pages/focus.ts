// ─────────────────────────────────────────────────────────────────────────────
// 跨页面「定位到任务所在位置」的请求。
//
// 发起方（总览的时间轴气泡、图谱的详情卡、管理页的表格行）只声明要去哪个任务，
// 不负责知道任务页内部有什么 —— 它有没有筛选、搜索框里有没有残留、表格滚到哪了，
// 都是任务页自己的事。任务页在切到自己时消费请求并自行复位。
//
// 为什么不让发起方直接调任务页的函数：那是 pages → pages 的互相依赖，五个页面
// 很快就会连成一团。这里退化成「单向请求 + 单点消费」，谁都可以安全依赖。
// ─────────────────────────────────────────────────────────────────────────────

import type { TaskStatus, Urgency } from "../data/types";
import { goPage } from "../shell/router";
import { openTask } from "./taskDrawer";

/** `"all"` 表示清掉筛选，回到全部。 */
export type StatusFilter = TaskStatus | "all";
/** 同上，`"all"` = 不按优先级筛。 */
export type UrgencyFilter = Urgency | "all";

export interface TasksRequest {
  taskId: string | null;
  filter: StatusFilter | null;
  urgency: UrgencyFilter | null;
  /** 只看「今天到期」（总览那张指标卡）。与 `filter` 互斥 —— 一次跳转只表达一个意图。 */
  dueToday: boolean;
}

const EMPTY: TasksRequest = { taskId: null, filter: null, urgency: null, dueToday: false };

let pending: TasksRequest = { ...EMPTY };

/** 任务页切到前台时取走请求，取走即清空。 */
export function consumeTasksRequest(): TasksRequest {
  const request = pending;
  pending = { ...EMPTY };
  return request;
}

/**
 * 跳到任务页、清掉筛选、滚动到该行并打开维护抽屉。
 *
 * 两个筛选维度都要清：留着上一次的「只看逾期」，再定位到一个进行中的任务，
 * 结果就是抽屉开了、列表里却没有它 —— 看着像跳转坏了，其实是筛选没复位。
 */
export function jumpToTask(taskId: string): void {
  pending = { taskId, filter: "all", urgency: "all", dueToday: false };
  goPage("tasks");
  openTask(taskId);
}

/**
 * 跳到任务页并按状态筛选。
 *
 * 优先级一并清掉：两个维度同时生效时，「点逾期进来只看到 1 条」这种事说不清
 * 是筛出来的还是漏掉的。一次跳转只表达一个意图。
 */
export function showTasksWithFilter(filter: StatusFilter): void {
  pending = { taskId: pending.taskId, filter, urgency: "all", dueToday: false };
  goPage("tasks");
}

/** 跳到任务页并按优先级筛选（总览的优先级分布用）。同上，状态筛选一并清掉。 */
export function showTasksWithUrgency(urgency: Urgency): void {
  pending = { taskId: pending.taskId, filter: "all", urgency, dueToday: false };
  goPage("tasks");
}

/**
 * 跳到任务页、只看「今天到期」的（总览的「今日到期」指标卡）。
 *
 * 这张卡原先**根本点不动**：`tile()` 只在给了 `onClick` 时才加 `clickable` / 监听，
 * 而它漏传了 —— 卡片上写着 1 条，点上去没有任何反应，也没有任何地方说得出为什么。
 * 判据见 `pages/shared.ts` 的 `isDueToday`：卡片数它、这里筛它，**同一个函数**。
 *
 * 状态筛选与优先级一并清掉，理由同 `showTasksWithFilter`：一次跳转只表达一个意图。
 */
export function showTasksDueToday(): void {
  pending = { taskId: pending.taskId, filter: "all", urgency: "all", dueToday: true };
  goPage("tasks");
}

// ─── 目的地是任务管理页的那一个 ────────────────────────────────────────────────
//
// 与上面同一形状（单向请求 + 单点消费），只是落点不同：**已归档的任务在任务页根本不列**
// （归档的意思就是「从「任务」界面收走」，见 `data/mock.ts` 的 `activeTasks`），所以
// 总览那张「归档」卡的唯一去处是管理页 —— 那页是唯一显示已归档的视图（§4.5）。
// 与其让那张卡点了没反应，不如把它送到**能看见那批东西**的地方。

let pendingArchived = false;

/** 跳到任务管理页、只看已归档的（总览的「归档」指标卡）。 */
export function showArchivedTasks(): void {
  pendingArchived = true;
  goPage("manage");
}

/** 管理页切到前台时取走请求，取走即清空。 */
export function consumeArchivedRequest(): boolean {
  const archived = pendingArchived;
  pendingArchived = false;
  return archived;
}
