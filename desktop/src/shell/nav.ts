// ─────────────────────────────────────────────────────────────────────────────
// 导航：rail 渲染 + 页面容器 + 页面挂载 + Ctrl+1..5。
//
// rail 的静态部分（分区 / 设置）写在 index.html 里，页面按钮按 PAGES 注册表
// 插到 .rail-grow 之前 —— 顺序即注册表顺序，也是快捷键序号。
//
// 切页状态由 router.ts 持有，这里只负责渲染并订阅它。曾经这里自己维护了一份
// activePage 和一套 class 切换，和 router 里的那份重复；两处并存的结果是
// 「谁先跑谁赢」，从页面里调 goPage 时 rail 高亮会漏掉。
// ─────────────────────────────────────────────────────────────────────────────

import { PAGE_VIEWS } from "../pages/index";
import { PAGES, type PageId, type PageSpec } from "../pages/registry";
import { $$, el, need } from "./dom";
import { goPage, registerPage, subscribePages } from "./router";
import { toast } from "./toast";

// ─── 页面容器 ────────────────────────────────────────────────────────────────

function renderPage(spec: PageSpec): HTMLElement {
  const head = el("div", { class: "ph" }, [
    el("div", {}, [
      el("div", { class: "ph-t", text: spec.title }),
      el("div", { class: "ph-d", text: spec.desc }),
    ]),
    el("div", { class: "ph-grow" }),
  ]);

  if (spec.action) {
    const view = PAGE_VIEWS[spec.id];
    const action = el("button", { class: "btn primary", text: spec.action });
    action.addEventListener("click", () => {
      if (view.onAction) view.onAction();
      else toast(`「${spec.action}」尚未接入`);
    });
    head.append(action);
  }

  const body = el("div", { class: "page-body" });

  // 某一页挂载失败不该让整个外壳变白屏 —— 把错误留在这一页里，
  // 其余页面照常可用，控制台里还有完整堆栈。
  try {
    PAGE_VIEWS[spec.id].mount(body);
  } catch (error) {
    console.error(`页面 ${spec.id} 渲染失败`, error);
    body.append(
      el("div", { class: "empty", text: `页面渲染失败：${error instanceof Error ? error.message : String(error)}` }),
    );
  }

  return el("section", { class: "page", id: `page-${spec.id}` }, [
    el("div", { class: "inner" }, [head, body]),
  ]);
}

// ─── rail ────────────────────────────────────────────────────────────────────

/**
 * 页面入口按注册表顺序插到 .rail-grow 之前 —— 顺序即快捷键序号（Ctrl+1..5）。
 *
 * 不画「工作 / 洞察 / 管理」分组标题：一整列按钮里只有前几个顶着文字，底部的
 * 分区 / 设置没有，看上去像是漏写了。要么每个都写，要么都不写 —— 都不写更安静，
 * 语义由图标 + hover 提示（title）承担。
 */
function renderRail(rail: HTMLElement): void {
  const anchor = rail.querySelector(".rail-grow");

  PAGES.forEach((spec, index) => {
    const button = el("button", {
      class: "rail-btn",
      "data-page": spec.id,
      title: `${spec.label} (Ctrl+${index + 1})`,
      html: spec.icon,
    });
    button.addEventListener("click", () => goPage(spec.id));

    if (anchor?.parentNode) anchor.parentNode.insertBefore(button, anchor);
    else rail.append(button);
  });
}

// ─── 快捷键 ──────────────────────────────────────────────────────────────────

/** Ctrl+1..5 切页；在输入控件里按键时不劫持。 */
function bindHotkeys(): void {
  document.addEventListener("keydown", (event) => {
    const tag = (event.target as HTMLElement | null)?.tagName.toLowerCase() ?? "";
    if (tag === "input" || tag === "textarea") return;
    if (!event.ctrlKey || event.altKey || event.metaKey) return;

    const slot = Number.parseInt(event.key, 10);
    if (!Number.isInteger(slot) || slot < 1 || slot > PAGES.length) return;

    event.preventDefault();
    goPage(PAGES[slot - 1].id);
  });
}

// ─── 挂载 ────────────────────────────────────────────────────────────────────

export function mountNav(): void {
  const rail = need("#rail");
  const main = need("#main");

  renderRail(rail);

  for (const spec of PAGES) {
    const section = renderPage(spec);
    registerPage(spec.id, section);
    main.append(section);
  }

  subscribePages((id: PageId) => {
    for (const button of $$(".rail-btn[data-page]")) {
      button.classList.toggle("active", button.dataset.page === id);
    }
  });

  bindHotkeys();
  goPage(PAGES[0].id);
}
