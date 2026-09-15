// ─────────────────────────────────────────────────────────────────────────────
// 破坏性操作的二次确认。
//
// 以前抽屉里的「删除」、管理页的「删除选中」「删除标签」都是点了直接改数据，
// 只在事后弹一个 toast。这类操作一旦发生就撤不回来 —— 现在删的是 mock 数组，
// 将来接上真实数据是同一份写法直接删库。所以放在外壳层做成一个通用浮层，
// 让所有破坏性操作走同一条路、同一套措辞，而不是每个页面各自 settle 一遍。
//
// 三个决定是刻意的：
//   1. 默认焦点给「取消」而不是确认 —— 手快连按回车时不该把东西删掉；
//       destructive 操作的默认值必须是不做事。
//   2. 返回 Promise<boolean>：调用方写 `if (!(await confirmAction(...))) return;`，
//      取消时不会顺延执行后面的删除逻辑。回调式写法很容易漏掉 early return。
//   3. Esc / 点遮罩都算取消。取消的方式永远要比确认的方式多。
// ─────────────────────────────────────────────────────────────────────────────

import { el } from "./dom";

export interface ConfirmOptions {
  /** 一句话说清后果，例如「删除选中的 3 个任务？」 */
  title: string;
  /** 补充信息，通常是被操作对象的名字 */
  detail?: string;
  confirmText?: string;
  cancelText?: string;
}

/** 与 .mask 的过渡时长保持一致（见 controls.css） */
const CLOSE_MS = 180;

export function confirmAction(options: ConfirmOptions): Promise<boolean> {
  return new Promise<boolean>((resolve) => {
    // 关掉之后把焦点还给打开它的人，否则键盘用户会丢焦点到 body 上
    const previous = document.activeElement as HTMLElement | null;

    const cancel = el("button", {
      class: "btn",
      type: "button",
      text: options.cancelText ?? "取消",
    });
    const confirm = el("button", {
      class: "btn solid-danger",
      type: "button",
      text: options.confirmText ?? "删除",
    });

    const children: Node[] = [el("div", { class: "modal-title", text: options.title })];
    if (options.detail) {
      children.push(el("div", { class: "modal-detail", text: options.detail }));
    }
    children.push(el("div", { class: "modal-actions" }, [cancel, confirm]));

    const card = el(
      "div",
      { class: "modal-card", role: "dialog", "aria-modal": "true" },
      children,
    );
    const mask = el("div", { class: "mask" }, [card]);

    let settled = false;
    const settle = (result: boolean): void => {
      if (settled) return;
      settled = true;
      mask.classList.remove("show");
      window.removeEventListener("keydown", onKey, true);
      window.setTimeout(() => {
        mask.remove();
        previous?.focus?.();
      }, CLOSE_MS);
      resolve(result);
    };

    function onKey(event: KeyboardEvent): void {
      // 捕获阶段拦下，别让下面的页面（编辑框、热键）也收到这次按键
      if (event.key === "Escape") {
        event.stopPropagation();
        event.preventDefault();
        settle(false);
      }
    }

    cancel.addEventListener("click", () => settle(false));
    confirm.addEventListener("click", () => settle(true));
    // 只有点在遮罩上才算取消，点在卡片里不算
    mask.addEventListener("click", (event) => {
      if (event.target === mask) settle(false);
    });

    document.body.append(mask);
    window.addEventListener("keydown", onKey, true);
    // 下一帧再加 show，让 transition 有起始状态
    requestAnimationFrame(() => {
      mask.classList.add("show");
      cancel.focus();
    });
  });
}
