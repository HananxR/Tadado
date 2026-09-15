// ─────────────────────────────────────────────────────────────────────────────
// 页面路由。
//
// 为什么单独一层：页面之间要能互相跳（热力图点某天 → 切到任务页并定位时段），
// 如果 `goPage` 留在 nav.ts，就变成「nav → 页面 → nav」的循环依赖。
// 这里只存状态和切换，不认识任何具体页面，谁都可以安全地依赖它。
// ─────────────────────────────────────────────────────────────────────────────

import type { PageId } from "../pages/registry";
import { $ } from "./dom";

type PageListener = (id: PageId) => void;

const pages = new Map<PageId, HTMLElement>();
const listeners = new Set<PageListener>();

let active: PageId | null = null;

/** 由 nav.ts 在渲染完页面骨架后登记。 */
export function registerPage(id: PageId, node: HTMLElement): void {
  pages.set(id, node);
}

/** 订阅「切到了哪一页」。返回退订函数。 */
export function subscribePages(listener: PageListener): () => void {
  listeners.add(listener);
  if (active) listener(active);
  return () => {
    listeners.delete(listener);
  };
}

export const currentPage = (): PageId | null => active;

export function goPage(id: PageId): void {
  const node = pages.get(id);
  if (!node) return;

  active = id;
  for (const [pageId, pageNode] of pages) {
    pageNode.classList.toggle("active", pageId === id);
  }

  // 切页后主区滚动位置归零，否则从长页面切到短页面会停在半空
  const main = $(".main");
  if (main) main.scrollTop = 0;

  for (const listener of listeners) listener(id);
}
