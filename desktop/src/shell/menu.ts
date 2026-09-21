// ─────────────────────────────────────────────────────────────────────────────
// 下拉菜单（原型 .dd / .menu）。任务页的排序、管理页的状态、维护抽屉的状态与
// 优先级都要用，而原型的 bindMenu 是「先写死两个 id 再注入 items」的风格，
// 一旦有多处就退化成四份几乎一样的绑定代码。
// 这里做成一个返回值可控的控件：自己管开关、自己管互斥。
// ─────────────────────────────────────────────────────────────────────────────

import { el } from "./dom";

const CHEVRON =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 9l6 6 6-6"/></svg>';
const CHECK =
  '<svg class="ck" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M4.5 12.5l4.8 4.8L19.5 7"/></svg>';

export interface MenuItem<V extends string> {
  value: V;
  label: string;
}

export interface Dropdown<V extends string> {
  root: HTMLElement;
  /**
   * 只改显示（勾选标记 + 按钮文案），**不会触发 onPick**。
   *
   * 以前这里顺带调一次 onPick，于是「把当前值显示出来」这种纯展示用法直接变成
   * 无限递归：paint → setValue → onPick → paint。任务抽屉一打开就 RangeError，
   * 抽屉节点建出来了却永远加不上 .open —— 表现就是双击、右键都没反应。
   * 选值只有一条路：菜单行自己的点击回调。setValue 因此是纯展示，和 seg 一致。
   *
   * 它用在**别处改了值**的时候（跨页请求把优先级筛选换掉、外部复位档位这类），
   * 自己的点击不用它 —— 菜单行会顺手把显示同步好（见下面的 row 回调）。
   */
  setValue(value: V): void;
}

/** 同一时刻只允许一个菜单展开。 */
let openMenu: HTMLElement | null = null;

function closeOpenMenu(): void {
  openMenu?.classList.remove("open");
  openMenu = null;
}

let listening = false;
function listenOnce(): void {
  if (listening) return;
  listening = true;
  // 点击别处收起。菜单里的点击自己 stopPropagation，不会走到这里。
  document.addEventListener("click", closeOpenMenu);
}

export function dropdown<V extends string>(options: {
  items: MenuItem<V>[];
  value: V;
  onPick: (value: V) => void;
}): Dropdown<V> {
  listenOnce();

  const caption = el("span");
  const button = el("button", { class: "dd-btn", type: "button" }, [caption]);
  button.insertAdjacentHTML("beforeend", CHEVRON);

  const menu = el("div", { class: "menu" });
  const root = el("div", { class: "dd" }, [button, menu]);

  const rows = options.items.map((item) => {
    const check = el("span", { class: "ck", html: CHECK });
    const row = el("div", { class: "menu-item" }, [el("span", { text: item.label }), check]);
    row.addEventListener("click", () => {
      closeOpenMenu();
      // 点了自己就把显示同步好（按钮文案 + 勾选），再交给调用方。
      // 2026-09-21 修：这一步原来只在 `setValue` 里做，于是**菜单行的点击不改显示** ——
      // 任务页的排序下拉点「按创建时间」，值确实换了、行也重排了，按钮上却还写着
      // 「按截止日期」、勾也还在原来那项上，看着就是「切不过去」。
      // 调用方仍可在**别处改了值**时用 setValue 同步（跨页请求复位筛选那类）。
      apply(item.value);
      options.onPick(item.value);
    });
    menu.append(row);
    return { item, row, check };
  });

  const apply = (value: V): void => {
    for (const { item, row, check } of rows) {
      const on = item.value === value;
      row.classList.toggle("on", on);
      // 勾选标记只给当前项。菜单本身已经用底色标了，再加个勾是双保险：
      // 色盲用户和灰度截图里都还分得出是哪一项。
      check.style.display = on ? "block" : "none";
      if (on) caption.textContent = item.label;
    }
  };

  /**
   * 展开：默认向下，**下方装不下就向上翻**（2026-09-20 用户报的）。
   *
   * 分页器贴在卡片底部，而那几张卡片的正文是 `overflow: hidden`（撑满场景的要求，
   * 见 pages.css 里 `#page-overview .card > .card-b`）—— 菜单向下展开会落在那条
   * 裁切线以下：**看得见一截，点不到任何一项**。翻上去之后菜单落在卡片内部，
   * 既不裁也不挡别人。
   *
   * 判据只看视口：下方放不下整块菜单、且上方比下方宽裕，就翻。先量高度再决定，
   * 所以要先 `open`（display:block 之后 offsetHeight 才是真值）。
   */
  const openPanel = (): void => {
    menu.classList.add("open");
    menu.classList.remove("up");
    const spaceBelow = window.innerHeight - button.getBoundingClientRect().bottom;
    if (spaceBelow < menu.offsetHeight + 8 && button.getBoundingClientRect().top > spaceBelow) {
      menu.classList.add("up");
    }
    openMenu = menu;
  };

  button.addEventListener("click", (event) => {
    event.stopPropagation();
    const willOpen = !menu.classList.contains("open");
    closeOpenMenu();
    if (willOpen) openPanel();
  });

  apply(options.value);

  return {
    root,
    setValue: (value) => apply(value),
  };
}
