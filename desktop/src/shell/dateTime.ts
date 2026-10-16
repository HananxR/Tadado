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
// 2026-10-16 起它还管**起止区间的边界**：任务的「开始」不能晚于它的「结束」、
// 「结束」不能早于「开始」（同日合法）。越界的那一天在取色盘里灰着，手输与粘贴也
// 进不来，被拒时给一句话说清是被哪一端卡住的（见 `bounds` / `peerLabel`）。
// 校验落在控件里而不是各页面：两栏同源，新建与维护才拦得住同一件事。
//
// 只依赖 data/time.ts（不是 pages/shared.ts）：外壳层不该反向依赖页面层。
// ─────────────────────────────────────────────────────────────────────────────

import { DAY_MS, TODAY, isoDay, monthDayText, weekdayOf } from "../data/time";
import { el } from "./dom";
import { toast } from "./toast";

export interface DateTimeValue {
  /** 天数，与 TODAY / dayNumber 同一坐标；null = 未设置。 */
  day: number | null;
  /** 「HH:MM」；null = 只到日期。 */
  time: string | null;
}

/**
 * 这一栏允许落在哪一段（天数口径，与 TODAY / dayNumber 同一坐标）。
 * 缺省或 `null` = 那一端不设限。
 */
export interface DateTimeBounds {
  min?: number | null;
  max?: number | null;
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
  /**
   * 可选的日期边界，**求值式**：每次提交前重新读一遍。
   *
   * 为什么不一次性传值：任务的「开始」上界就是它的「结束」，而那个数随时会被
   * 对端那一栏改掉（两栏在同一张表单里）。求值式让调用方不必在两栏之间同步一份
   * 状态 —— 少一类「两边对不上」的 bug。
   *
   * 它管的是**日期那一栏**：越界的那一天选不中、填不进，并在被拒时说明原因。
   * 「清除」（day = null）不算越界 —— 它表达的是「没有这个时间」，不是某一天。
   */
  bounds?: () => DateTimeBounds;
  /**
   * 另一端在界面上叫什么（「开始」栏传「结束」）。
   *
   * 越界的那句话必须说出是被谁卡住的：「不能晚于 10-16」读不出哪一端在限制它。
   */
  peerLabel?: string;
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

  /** 当前边界。每次都现读 —— 另一端刚改过的那一天要立刻生效。 */
  const boundNow = (): { min: number | null; max: number | null } => {
    const bound = options.bounds?.() ?? {};
    return { min: bound.min ?? null, max: bound.max ?? null };
  };

  /**
   * 把边界写进原生日期框的 `min` / `max`：**取色盘里越界的那些天直接灰掉**，
   * 而不是让用户挑完了再被退回。
   *
   * 它挡不住手输与粘贴（原生属性只是「选不中」，值照样能落进 `value`），
   * 所以提交前还要再判一次 —— 那一道才是真正的拦。
   */
  const applyBounds = (): void => {
    const { min, max } = boundNow();
    if (min === null) dateInput.removeAttribute("min");
    else dateInput.min = isoDay(min);
    if (max === null) dateInput.removeAttribute("max");
    else dateInput.max = isoDay(max);
  };

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
    applyBounds();
  };

  /**
   * 只在用户操作时走这条：回写显示 + 通知外部。
   *
   * 越界的值**不进模型**：`onChange` 不触发（抽屉那条路是即时落库的，拦在出口之前
   * 才不需要回滚），显示退回改动前的那一个值，并说清是被哪一端卡住的。
   */
  const commit = (next: DateTimeValue): void => {
    // 判据只在**日期真的被改动**时生效。只改时分不算越界：一来它是同一格里的另一列
    // （改 14:30 不可能让区间倒过来），二来库里已有的倒挂任务（历史数据按设计不处理）
    // 还得能把它的时刻改掉 —— 拿一条没碰过的日期去拦人，用户只会觉得控件坏了。
    if (next.day !== null && next.day !== value.day) {
      const { min, max } = boundNow();
      const violation: { kind: "min" | "max"; day: number } | null =
        min !== null && next.day < min
          ? { kind: "min", day: min }
          : max !== null && next.day > max
            ? { kind: "max", day: max }
            : null;
      if (violation) {
        // 只重画：内部 value 没动，画出来就是改动前的那个值
        paint();
        const word = violation.kind === "min" ? "早于" : "晚于";
        toast(`${options.label}不能${word}${options.peerLabel ?? "另一端"}（${monthDayText(violation.day)}）`);
        return;
      }
    }
    value = next;
    paint();
    options.onChange({ ...value });
  };

  dateInput.addEventListener("input", () => {
    // 清空日期框 = 取消时间设置，连时刻一起清掉：留着一个没有日期的时刻，
    // 谁也说不清它指哪一天
    const day = dateInput.value ? dayOf(dateInput.value) : null;
    // 但**不是每一栏都能被清空**（`clearable: false` = 模型里必填，如任务的「开始」）：
    // 那里不摆「清除」按钮，键盘上删空日期框同样不算数 —— 显示退回原值。让它空着而
    // 模型还留着旧值，就是「显示与模型两个口径」，比不给删更让人摸不着头脑
    if (day === null && options.clearable === false) {
      paint();
      return;
    }
    commit(day === null ? { day: null, time: null } : { day, time: value.time });
  });

  // 另一端是在这张表单里改的，所以进日期框之前重算一次边界：
  // 只在 paint 里算的话，用户点开取色盘看到的还是上一次的上下限
  dateInput.addEventListener("focus", applyBounds);

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
