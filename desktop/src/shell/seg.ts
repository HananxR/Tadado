// ─────────────────────────────────────────────────────────────────────────────
// 分段控件（原型 .seg）：一排互斥按钮。
//
// 无状态 —— 只管画和转发点击，当前选中值由调用方传入、由调用方经 setValue 更新。
// 「谁持有档位」因此永远只有一个答案：调用方。控件自己存一份的话，外部改了值
// （比如设置面板改了时间轴粒度），任务页工具行里那排按钮就会停在旧状态上。
// ─────────────────────────────────────────────────────────────────────────────

import { el } from "./dom";

export interface SegOption<V extends string> {
  value: V;
  label: string;
}

export interface Seg<V extends string> {
  root: HTMLElement;
  setValue: (value: V) => void;
}

export function seg<V extends string>(
  options: readonly SegOption<V>[],
  initial: V,
  onPick: (value: V) => void,
): Seg<V> {
  const buttons = options.map((option) => {
    const button = el("button", { type: "button", text: option.label });
    button.addEventListener("click", () => onPick(option.value));
    return { option, button };
  });

  const root = el("div", { class: "seg" }, buttons.map((item) => item.button));

  const setValue = (value: V): void => {
    for (const { option, button } of buttons) {
      button.classList.toggle("on", option.value === value);
    }
  };

  setValue(initial);
  return { root, setValue };
}
