// 底部提示条。原型 #toast：显示 2.2s 后淡出。

import { need } from "./dom";

const VISIBLE_MS = 2200;

let timer: number | undefined;

export function toast(message: string): void {
  const node = need("#toast");
  node.textContent = message;
  node.classList.add("show");

  window.clearTimeout(timer);
  timer = window.setTimeout(() => node.classList.remove("show"), VISIBLE_MS);
}
