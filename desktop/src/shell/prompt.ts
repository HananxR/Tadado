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
}

const CLOSE_MS = 180;

export function promptText(options: PromptOptions): Promise<string | null> {
  return new Promise<string | null>((resolve) => {
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

    const children: Node[] = [el("div", { class: "modal-title", text: options.title })];
    if (options.detail) {
      children.push(el("div", { class: "modal-detail", text: options.detail }));
    }
    children.push(input, el("div", { class: "modal-actions" }, [cancel, confirm]));

    const card = el("div", { class: "modal-card" }, children);
    const mask = el("div", { class: "mask" }, [card]);

    let settled = false;
    const settle = (value: string | null): void => {
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
        settle(input.value);
      }
    }

    cancel.addEventListener("click", () => settle(null));
    confirm.addEventListener("click", () => settle(input.value));
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
