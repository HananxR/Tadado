// ─────────────────────────────────────────────────────────────────────────────
// 分页器。管理页表格、任务页时间轴、活动分析报告共用一份。
//
// 为什么抽出来：三张表都要「第几条到第几条 / 一共几条 + 翻页 + 每页几条」，
// 各写一份的话，迟早出现一处翻到最后一页夹不住、一处换了每页条数却没回第一页
// —— 那种 bug 单看每一处都写得没错。
//
// 页面上可调每页条数，不进设置：它只影响眼前这张表，为它去设置里翻一层不值当。
// ─────────────────────────────────────────────────────────────────────────────

import { dropdown } from "../shell/menu";
import { el } from "../shell/dom";
import { PAGE_SIZES } from "./shared";

export interface PagerOptions {
  /** 当前页（0 起）。 */
  page: number;
  /** 一共几页（调用方保证 ≥ 1）。 */
  pageCount: number;
  /** 筛出来的总条数。 */
  total: number;
  /** 每页几条。 */
  size: number;
  onGo: (page: number) => void;
  /** 给了就显示「每页几条」下拉。 */
  onSize?: (size: number) => void;
}

export function pager(options: PagerOptions): HTMLElement {
  const start = options.page * options.size;
  const end = Math.min(start + options.size, options.total);

  const navButton = (text: string, delta: number, disabled: boolean): HTMLElement => {
    const button = el("button", { class: "navbtn", type: "button", text });
    button.disabled = disabled;
    button.addEventListener("click", () => options.onGo(options.page + delta));
    return button;
  };

  const nodes: HTMLElement[] = [
    el("span", {
      text:
        options.total === 0
          ? "共 0 条"
          : `第 ${start + 1}–${end} 条 / 共 ${options.total} 条`,
    }),
    navButton("◀", -1, options.page <= 0),
    el("span", { class: "mono dim", text: `${options.page + 1} / ${options.pageCount}` }),
    navButton("▶", 1, options.page >= options.pageCount - 1),
  ];

  if (options.onSize) {
    nodes.push(
      dropdown<string>({
        items: PAGE_SIZES.map((size) => ({ value: String(size), label: `${size} 条/页` })),
        value: String(options.size),
        onPick: (value) => options.onSize?.(Number(value)),
      }).root,
    );
  }

  return el("div", { class: "pager" }, nodes);
}
