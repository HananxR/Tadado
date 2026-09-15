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

import type { TaskStatus } from "../data/types";
import { goPage } from "../shell/router";
import { openTask } from "./taskDrawer";

/** `"all"` 表示清掉筛选，回到全部。 */
export type StatusFilter = TaskStatus | "all";

export interface TasksRequest {
  taskId: string | null;
  filter: StatusFilter | null;
}

let pending: TasksRequest = { taskId: null, filter: null };

/** 只定位任务，不动筛选。 */
export function requestTaskFocus(taskId: string): void {
  pending = { taskId, filter: pending.filter };
}

/** 只换筛选，不定位任务。 */
export function requestTaskFilter(filter: StatusFilter): void {
  pending = { taskId: pending.taskId, filter };
}

/** 任务页切到前台时取走请求，取走即清空。 */
export function consumeTasksRequest(): TasksRequest {
  const request = pending;
  pending = { taskId: null, filter: null };
  return request;
}

/** 跳到任务页、复位筛选、滚动到该行并打开维护抽屉。 */
export function jumpToTask(taskId: string): void {
  requestTaskFocus(taskId);
  requestTaskFilter("all");
  goPage("tasks");
  openTask(taskId);
}

/** 跳到任务页并按状态筛选。 */
export function showTasksWithFilter(filter: StatusFilter): void {
  requestTaskFilter(filter);
  goPage("tasks");
}
