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
  /**
   * 这张表数的是什么，默认「条」，用在范围那句上。总览的近期活动是按**任务**聚合的，
   * 写「条」就会和它旁边那排「共 N 条活动」串味：卡片头说「共 88 个任务」、分页器说
   * 「共 88 条」，看着像两个对不上的数（2026-09-20 用户报的正是这个）。所以单位由
   * 调用方给。**档位下拉不重复写单位**（只写「50/页」）：同一件事说两遍只会更挤。
   */
  unit?: string;
  /**
   * 要不要报总数，默认要（`第 1–20 条 / 共 201 条`）。
   *
   * 总览的近期活动关掉它（2026-09-20 用户报的）：那一栏的数字带「共」字时会被读成
   * 「这一屏显示了 88 条」——而它其实是聚合之后的任务总数，20/50 才是每屏行数。
   * 关掉之后只报**范围**（`第 1–50 个任务`）：范围本身就是分页器要说的那件事，
   * 想往后翻的人看「1 / 2」和箭头就够了。
   */
  showTotal?: boolean;
  onGo: (page: number) => void;
  /** 给了就显示「每页几条」下拉。 */
  onSize?: (size: number) => void;
}

export function pager(options: PagerOptions): HTMLElement {
  const unit = options.unit ?? "条";
  const showTotal = options.showTotal ?? true;
  const start = options.page * options.size;
  const end = Math.min(start + options.size, options.total);

  // 范围那一句有三种写法：不报总数（只给范围）、空表、以及默认的「范围 / 总数」。
  // 空表时两种都只写「共 0」，不写「第 1–0」—— 那不是一句人话
  const rangeText = (): string => {
    if (options.total === 0) return showTotal ? `共 0 ${unit}` : "暂无";
    if (!showTotal) return `第 ${start + 1}–${end} ${unit}`;
    return `第 ${start + 1}–${end} ${unit} / 共 ${options.total} ${unit}`;
  };

  const navButton = (text: string, delta: number, disabled: boolean): HTMLElement => {
    const button = el("button", { class: "navbtn", type: "button", text });
    button.disabled = disabled;
    button.addEventListener("click", () => options.onGo(options.page + delta));
    return button;
  };

  const nodes: HTMLElement[] = [el("span", { text: rangeText() })];

  // 只有一页时不摆翻页件（2026-09-20 用户嫌繁琐）：`◀ 1 / 1 ▶` 里没有一个能按的，
  // 却和真正要读的那句范围说明一样显眼 —— 没得翻的时候，这句话本来就不必说
  if (options.pageCount > 1) {
    nodes.push(
      navButton("◀", -1, options.page <= 0),
      el("span", { class: "mono dim", text: `${options.page + 1} / ${options.pageCount}` }),
      navButton("▶", 1, options.page >= options.pageCount - 1),
    );
  }

  if (options.onSize) {
    nodes.push(
      dropdown<string>({
        // 档位只写数：紧挨着的那句范围说明已经带了单位（「第 1–50 个任务」），
        // 再写一遍「50 个任务/页」是把同一件事说两遍，右边那截还显得很挤
        items: PAGE_SIZES.map((size) => ({ value: String(size), label: `${size}/页` })),
        value: String(options.size),
        onPick: (value) => options.onSize?.(Number(value)),
      }).root,
    );
  }

  return el("div", { class: "pager" }, nodes);
}
