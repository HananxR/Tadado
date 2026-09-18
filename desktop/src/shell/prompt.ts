// ─────────────────────────────────────────────────────────────────────────────
// 单行输入浮层（confirm.ts 的兄弟：confirm 问的是「是/否」，这里问的是「填什么」）。
//
// 返回 Promise<string | null>：取消（Esc / 点遮罩 / 点取消）得到 null，
// 确认得到输入框里的内容。空的输入也照常返回 ——
// 「允许留空」该由调用方判断，浮层不该替它决定。
// ─────────────────────────────────────────────────────────────────────────────

import { el } from "./dom";

export interface PromptOptions {
  title: string;
  detail?: string;
  placeholder?: string;
  confirmText?: string;
  /** 密码框：输入不回显。 */
  password?: boolean;
  /**
   * 第三个按钮，排在最左边（「清除」这类）。
   *
   * 加它是为了口令那一个入口：设 / 改 / 清本来是一件事的三种结果，把它们拆成
   * 三个按钮，用户得先猜「我现在该点哪个」。
   */
  extra?: { label: string; danger?: boolean };
}

export interface PromptResult {
  value: string;
  /** 点的是 extra 那个按钮。 */
  extra: boolean;
}

const CLOSE_MS = 180;

/** 只关心输入框内容的用法（大部分场景）。点了 extra 或取消一律当取消。 */
export function promptText(options: PromptOptions): Promise<string | null> {
  return openPrompt(options).then((result) => (result && !result.extra ? result.value : null));
}

/** 需要区分「确认」和「点了 extra」时用这个（口令的设 / 改 / 清）。 */
export const promptWithExtra = (options: PromptOptions): Promise<PromptResult | null> =>
  openPrompt(options);

function openPrompt(options: PromptOptions): Promise<PromptResult | null> {
  return new Promise<PromptResult | null>((resolve) => {
    const previous = document.activeElement as HTMLElement | null;

    const input = el("input", {
      class: "pr-input",
      type: options.password ? "password" : "text",
      placeholder: options.placeholder ?? "",
    });

    const cancel = el("button", { class: "btn", type: "button", text: "取消" });
    const confirm = el("button", {
      class: "btn primary",
      type: "button",
      text: options.confirmText ?? "确定",
    });

    const actions: HTMLElement[] = [];
    if (options.extra) {
      const extra = el("button", {
        class: options.extra.danger ? "btn danger" : "btn",
        type: "button",
        text: options.extra.label,
      });
      extra.style.marginRight = "auto";
      extra.addEventListener("click", () => settle({ value: input.value, extra: true }));
      actions.push(extra);
    }
    actions.push(cancel, confirm);

    const children: Node[] = [el("div", { class: "modal-title", text: options.title })];
    if (options.detail) {
      children.push(el("div", { class: "modal-detail", text: options.detail }));
    }
    children.push(input, el("div", { class: "modal-actions" }, actions));

    const card = el("div", { class: "modal-card" }, children);
    const mask = el("div", { class: "mask" }, [card]);

    let settled = false;
    const settle = (value: PromptResult | null): void => {
      if (settled) return;
      settled = true;
      mask.classList.remove("show");
      window.removeEventListener("keydown", onKey, true);
      window.setTimeout(() => {
        mask.remove();
        previous?.focus?.();
      }, CLOSE_MS);
      resolve(value);
    };

    function onKey(event: KeyboardEvent): void {
      if (event.key === "Escape") {
        event.stopPropagation();
        settle(null);
        return;
      }
      if (event.key === "Enter") {
        event.stopPropagation();
        settle({ value: input.value, extra: false });
      }
    }

    cancel.addEventListener("click", () => settle(null));
    confirm.addEventListener("click", () => settle({ value: input.value, extra: false }));
    mask.addEventListener("click", (event) => {
      if (event.target === mask) settle(null);
    });

    document.body.append(mask);
    window.addEventListener("keydown", onKey, true);
    requestAnimationFrame(() => {
      mask.classList.add("show");
      input.focus();
    });
  });
}
