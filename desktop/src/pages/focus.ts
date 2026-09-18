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
}

const EMPTY: TasksRequest = { taskId: null, filter: null, urgency: null };

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
  pending = { taskId, filter: "all", urgency: "all" };
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
  pending = { taskId: pending.taskId, filter, urgency: "all" };
  goPage("tasks");
}

/** 跳到任务页并按优先级筛选（总览的优先级分布用）。同上，状态筛选一并清掉。 */
export function showTasksWithUrgency(urgency: Urgency): void {
  pending = { taskId: pending.taskId, filter: "all", urgency };
  goPage("tasks");
}
