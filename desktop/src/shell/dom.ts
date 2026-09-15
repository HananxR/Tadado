// ─────────────────────────────────────────────────────────────────────────────
// 极小的 DOM 助手。外壳的节点结构是固定的（写在 index.html / registry.ts 里），
// 所以这里只解决「查得到」和「建得出」两件事，不引入任何框架。
// ─────────────────────────────────────────────────────────────────────────────

export const $ = <T extends Element = HTMLElement>(
  selector: string,
  root: ParentNode = document,
): T | null => root.querySelector<T>(selector);

export const $$ = <T extends Element = HTMLElement>(
  selector: string,
  root: ParentNode = document,
): T[] => Array.from(root.querySelectorAll<T>(selector));

/**
 * 取必需节点。外壳节点缺失属于结构性错误，早失败早发现 ——
 * 返回 null 再到处判空只会把问题拖到运行期某个诡异的交互里。
 */
export function need<T extends Element = HTMLElement>(
  selector: string,
  root: ParentNode = document,
): T {
  const node = $<T>(selector, root);
  if (!node) throw new Error(`外壳缺少必需节点：${selector}`);
  return node;
}

export interface ElAttrs {
  class?: string;
  text?: string;
  html?: string;
  [attr: string]: string | number | boolean | undefined;
}

export function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  attrs: ElAttrs = {},
  children: (Node | string)[] = [],
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);

  for (const [key, value] of Object.entries(attrs)) {
    if (value === undefined || value === false) continue;
    if (key === "class") node.className = String(value);
    else if (key === "text") node.textContent = String(value);
    else if (key === "html") node.innerHTML = String(value);
    else node.setAttribute(key, value === true ? "" : String(value));
  }

  for (const child of children) node.append(child);
  return node;
}
