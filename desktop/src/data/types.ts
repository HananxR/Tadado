// ─────────────────────────────────────────────────────────────────────────────
// 领域类型。
//
// 字段命名对齐 DESIGN.md 的数据模型（任务 / 状态 / 紧迫度 / 活动 / 任务关联），
// 不是照抄原型的 JS 对象 —— 原型里 `t` `st` `dl` `p` `urg` 这套缩写是为了在
// 一个 HTML 文件里省字符，放进工程只会让每个读代码的人先猜一轮。
//
// 「今天」不是系统的今天：样例数据全部围绕 2026-09-12 排布（见 mock.ts 的
// DEMO_TODAY）。真实数据接入后由后端给出，这里只保证样例自洽。
// ─────────────────────────────────────────────────────────────────────────────

/** 任务状态。`overdue` 由系统标记，不提供手动选择（DESIGN.md 2.x）。 */
export type TaskStatus = "todo" | "doing" | "done" | "overdue";

/** 紧迫度档位，数字越小越紧迫。 */
export type Urgency = 0 | 1 | 2 | 3;

/** [月, 日]。年份由 DEMO_TODAY 决定的演示年内，不单独存。 */
export type MonthDay = [month: number, day: number];

/**
 * 活动发生的时刻：**epoch 毫秒**（与 data/time.ts 的天数同一套换算，
 * 见 `stampOf` / `nowStamp`）。
 *
 * 以前这里存的是展示串（`"刚刚"` / `"今天 09:12"` / `"昨天 17:20"`），那是个
 * 会变的东西：同一条记录今天写「昨天」，明天再看就成了「前天」，而界面和导出
 * 还得靠正则反解这句话才能算出它在哪一天。时间戳只该有一种写法。
 */
export type At = number;

/**
 * 活动记录。用判别联合而不是原型那种 `[时间, 文本, 类型, a, b]` 元组：
 * 元组里第 4、5 位到底是百分比还是状态名，完全取决于第 3 位，读起来要
 * 一直往回数，而且类型系统帮不上任何忙。
 */
export type Activity =
  | { at: At; text: string; kind: "create" }
  | { at: At; text: string; kind: "status"; from: TaskStatus; to: TaskStatus }
  | { at: At; text: string; kind: "progress"; from: number; to: number }
  /** 人手写的一条进展。只有这一类可改可删 —— 另外三类是既成事实，改它等于篡改历史。 */
  | { at: At; text: string; kind: "log"; edited?: boolean };

export interface Task {
  id: string;
  title: string;
  status: TaskStatus;
  tags: string[];
  /** 截止的人话展示（「今天 15:00」/「09-14」/「昨天」），无截止为 null。 */
  due: string | null;
  /**
   * 今日时间轴上的时刻「HH:MM」，只有落在今天且有明确时间点的任务才有。
   * 与 `due` 分开：截止可以是「今天」（只到天），但排不进时间轴。
   */
  at: string | null;
  /** 起止区间，决定甘特条与时间轴表格里的色条跨度。 */
  start: MonthDay;
  end: MonthDay;
  /** 0–100。 */
  progress: number;
  urgency: Urgency;
  created: MonthDay;
  archived: boolean;
  /** 所属分区 id（见 data/partitions.ts）。原版里分区是数据模型的一部分：
   *  切分区不是换个筛选，而是换一批数据。 */
  partition: string;
  activities: Activity[];
  /** 关联任务的 id。关系是有向的「提到」，图谱按无向边渲染并去重。 */
  related: string[];
}
