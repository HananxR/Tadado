// ─────────────────────────────────────────────────────────────────────────────
// 页面实现表：PageId → 具体实现。
//
// 和 registry.ts 分开是有意的。registry 是「有哪些页面」（导航要知道的），
// 这里是「页面怎么画」（只有外壳要知道的）。nav.ts 依赖后者，router.ts 依赖
// 前者，于是 router 不必认识任何一个页面模块 —— 页面可以自由地 import
// router 来跳转，不会绕成环。
// ─────────────────────────────────────────────────────────────────────────────

import type { PageId } from "./registry";

import * as activity from "./activity";
import * as graph from "./graph";
import * as manage from "./manage";
import * as overview from "./overview";
import * as tasks from "./tasks";

export interface PageView {
  /** 往宿主容器里画页面。宿主已经被 nav 清空，实现里不需要自己清理。 */
  mount(host: HTMLElement): void;
  /** 页头动作的行为（`id` 来自 registry 的 PageAction）。缺省时 nav 会提示「尚未接入」。 */
  onAction?: (id: string) => void;
}

export const PAGE_VIEWS: Record<PageId, PageView> = {
  overview,
  tasks,
  graph,
  activity,
  manage,
};
