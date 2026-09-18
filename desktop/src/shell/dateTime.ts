// ─────────────────────────────────────────────────────────────────────────────
// 日期时间输入。
//
// 同一个组件给「开始」和「结束」用：前者只要日期，后者要日期 + 时分。两者的差别
// 只有「要不要时刻列」和「标签叫什么」，不允许各自长成另一个样子。
//
// 以前这里是三套互不相干的东西：一个裸的 <input type="date">、一排散在旁边的
// 「今天 / 明天 / 下周 / 清除」chip、以及一个**根本不存在**的时刻输入（列表上却
// 显示着「⏰ 今天 15:00」）。用户的原话是「今天、明天、下周、还有时间组件我理解
// 都是时间的设计组件，需要统一布局」——所以它们现在是一个组件的三段，排布固定。
//
// 只依赖 data/time.ts（不是 pages/shared.ts）：外壳层不该反向依赖页面层。
// ─────────────────────────────────────────────────────────────────────────────

import { DAY_MS, TODAY, isoDay, monthDayText, weekdayOf } from "../data/time";
import { el } from "./dom";

export interface DateTimeValue {
  /** 天数，与 TODAY / dayNumber 同一坐标；null = 未设置。 */
  day: number | null;
  /** 「HH:MM」；null = 只到日期。 */
  time: string | null;
}

export interface DateTimeFieldOptions {
  /** 左侧标签，如「开始」「结束」。 */
  label: string;
  value: DateTimeValue;
  /** 要不要时刻列。开始时间只到日期，结束时间要时分。 */
  withTime?: boolean;
  /**
   * 给不给「清除」。开始时间是任务的起点，模型里必填，清掉它没有意义 ——
   * 所以那里不出现这个按钮，而不是让它点了没反应。
   */
  clearable?: boolean;
  onChange: (value: DateTimeValue) => void;
}

export interface DateTimeField {
  root: HTMLElement;
  /** 只回写显示，不触发 onChange —— 否则外部一改值就回声成环。 */
  setValue: (value: DateTimeValue) => void;
}

/** 快捷档位。三个最常用的偏移，其余交给日期框。 */
const QUICK: { label: string; offset: number }[] = [
  { label: "今天", offset: 0 },
  { label: "明天", offset: 1 },
  { label: "下周", offset: 7 },
];

/** 「YYYY-MM-DD」→ 天数。非法输入返回 null。 */
const dayOf = (iso: string): number | null => {
  const parsed = Date.parse(`${iso}T00:00:00Z`);
  return Number.isNaN(parsed) ? null : Math.floor(parsed / DAY_MS);
};

export function dateTimeField(options: DateTimeFieldOptions): DateTimeField {
  let value: DateTimeValue = { ...options.value };

  const dateInput = el("input", { type: "date", class: "dt-date" });
  const timeInput = options.withTime
    ? el("input", { type: "time", class: "dt-time" })
    : null;
  const hint = el("span", { class: "dt-hint mono" });

  /** 把当前值刷到输入框与右侧说明上。三个入口（外部 setValue / 自己改 / 快捷档）共用。 */
  const paint = (): void => {
    dateInput.value = value.day === null ? "" : isoDay(value.day);
    if (timeInput) timeInput.value = value.time ?? "";
    hint.textContent =
      value.day === null
        ? value.time
          ? `${value.time} · 未定日期`
          : "未设置"
        : `${monthDayText(value.day)} ${weekdayOf(value.day)}${value.time ? ` ${value.time}` : ""}`;
  };

  /** 只在用户操作时走这条：回写显示 + 通知外部。 */
  const commit = (next: DateTimeValue): void => {
    value = next;
    paint();
    options.onChange({ ...value });
  };

  dateInput.addEventListener("input", () => {
    // 清空日期框 = 取消时间设置，连时刻一起清掉：留着一个没有日期的时刻，
    // 谁也说不清它指哪一天
    const day = dateInput.value ? dayOf(dateInput.value) : null;
    commit(day === null ? { day: null, time: null } : { day, time: value.time });
  });

  timeInput?.addEventListener("input", () => {
    commit({ day: value.day, time: timeInput.value || null });
  });

  const quickRow = el("div", { class: "chips dt-quick" });
  for (const item of QUICK) {
    const chip = el("button", { class: "chip", type: "button", text: item.label });
    chip.addEventListener("click", () => {
      // 快捷档只改日期，保留已经填好的时刻 —— 改日期时把 14:30 抹掉是最烦人的
      commit({ day: TODAY + item.offset, time: value.time });
    });
    quickRow.append(chip);
  }

  if (options.clearable !== false) {
    const clear = el("button", { class: "chip", type: "button", text: "清除" });
    clear.addEventListener("click", () => commit({ day: null, time: null }));
    quickRow.append(clear);
  }

  const root = el("div", { class: "dt" }, [
    el("span", { class: "dt-k", text: options.label }),
    dateInput,
    ...(timeInput ? [timeInput] : []),
    quickRow,
    hint,
  ]);

  paint();

  return {
    root,
    setValue: (next) => {
      value = { ...next };
      paint();
    },
  };
}
