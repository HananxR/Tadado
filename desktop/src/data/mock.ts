// ─────────────────────────────────────────────────────────────────────────────
// 样例数据：**演示空间的 100 条任务**（28 条原型手写 + 72 条压测生成）。
//
// 前 28 条取自 resources/ui-mockup/tadado-2.0.html，逐字一致 —— 界面一改就能
// 和原型并排比对，看出是「搬歪了」还是「原型本来就这样」。后 72 条由
// stressTasks 按序号确定性地生成，把规模顶到 100（见 STRESS_EXTRA）：它们是
// 窗口自适应 / 分页 / 力导向布局这些上限的真实输入，也是交付时演示数据的全部。
//
// 全部落在**演示空间**，其他分区交付时为空（见 SEED_TASKS 的备注）。
//
// ⚠️ 这是**种子数据**，不是运行时数据。首次启动时 store 会把它写进库，之后
// 以库为准 —— 用户改过的东西不该被下一次启动覆盖掉。
//
// 时间基准：DEMO_TODAY = 2026-09-12 只是**这批样例**的排布锚点（活动里的
// 「今天 / 昨天」、任务的起止日期都相对它写）；界面的「今天」读真实时钟，
// 见 pages/shared.ts 的 TODAY。
// ─────────────────────────────────────────────────────────────────────────────

import { DEMO_PARTITION_ID, activePartitionId } from "./partitions";
import {
  DAY_MS,
  TODAY,
  monthDayText,
  nowMinutes,
  nowStamp,
  pad2,
  parseStampText,
} from "./time";
import type { Activity, MonthDay, Task, TaskStatus, Urgency } from "./types";

/** 演示用的「今天」。真实数据接入后由后端给出。 */
export const DEMO_TODAY: MonthDay = [9, 12];

// 种子里的活动时刻仍写**人话**（「刚刚」/「今天 09:30」/「09-11 09:30」），
// 好让这 28 条能和原型逐字对照；构建 SEED_TASKS 时统一换算成时间戳。
// 也就是说：人话只活在种子里，模型和库里都是时间戳（见 types.ts 的 At）。
// 注意用**分布式**条件类型：`Omit<Activity, "at">` 会把判别联合塌缩成
// 「所有成员的公共属性」，`from` / `to` 这些字段就全丢了
type SeedActivity = Activity extends infer A
  ? A extends { at: number }
    ? Omit<A, "at"> & { at: string }
    : never
  : never;
type SeedTask = Omit<Task, "partition" | "activities"> & { activities: SeedActivity[] };

/**
 * 人话时刻 → 时间戳。**只给种子用**（同一套换算也在读入口迁移旧数据，见
 * data/time.ts 的 parseStampText），新代码一律直接写 `nowStamp()`。
 */
const seedStamp = (text: string): number => parseStampText(text, nowStamp());

// 「现在」不再是演示常量：总览时间轴上的「现在」标记读真实时钟（data/time.ts
// 的 nowMinutes）。原来这里写死 09:30，是为了让标记和排在演示日期上的样例任务
// 「说得通」，代价是这块界面永远在说错时间。

// 分区不再是一个写死的常量：它是数据模型的隔离边界，见 data/partitions.ts。
// 需要「当前分区名」的地方请用 activePartition().name。

/**
 * 演示数据，分区字段由下面统一补（见 TASKS）——
 * 这里写 `Omit<Task, "partition">` 是为了不必在 28 条字面量里逐条手填分区。
 */
const SEED: SeedTask[] = [
  {
    id: "auth",
    title: "重构认证模块",
    status: "doing",
    tags: ["#后端"],
    due: "09-14 14:30",
    at: null,
    start: [9, 8],
    end: [9, 14],
    progress: 80,
    urgency: 1,
    created: [9, 8],
    archived: false,
    related: ["api", "login", "perf"],
    activities: [
      { at: "09-11 09:30", text: "完成接口联调", kind: "progress", from: 60, to: 80 },
      { at: "09-10 14:00", text: "梳理认证流程", kind: "status", from: "todo", to: "doing" },
      { at: "09-08 10:12", text: "创建任务", kind: "create" },
    ],
  },
  {
    id: "api",
    title: "完成接口联调",
    status: "doing",
    tags: ["#后端", "#前端"],
    due: "09-13 18:00",
    at: null,
    start: [9, 6],
    end: [9, 13],
    progress: 60,
    urgency: 2,
    created: [9, 6],
    archived: false,
    related: ["pr", "deploy", "ci"],
    activities: [
      { at: "09-11 16:40", text: "联调网关与鉴权", kind: "progress", from: 40, to: 60 },
      { at: "09-06 09:20", text: "创建任务", kind: "create" },
    ],
  },
  {
    id: "deploy",
    title: "部署预发布环境",
    status: "doing",
    tags: ["#后端"],
    due: "09-13 12:00",
    at: null,
    start: [9, 11],
    end: [9, 13],
    progress: 50,
    urgency: 1,
    created: [9, 11],
    archived: false,
    related: ["data"],
    // 第二条落在下午那段里：与 perf 的 15:03、mentor 的 14:58 一起，让「同一时段
    // 三个任务都动过」这件事在种子里就有（轴上要合成一簇，不能靠加道把轴撑高）
    activities: [
      { at: "今天 08:40", text: "完成镜像构建", kind: "progress", from: 20, to: 50 },
      { at: "今天 14:55", text: "灰度放到 20%", kind: "log" },
    ],
  },
  {
    id: "login",
    title: "修复登录页样式",
    status: "doing",
    tags: ["#前端"],
    due: "09-16",
    at: null,
    start: [9, 10],
    end: [9, 16],
    progress: 30,
    urgency: 2,
    created: [9, 10],
    archived: false,
    related: [],
    activities: [{ at: "09-10 11:24", text: "进度 0% → 30%", kind: "progress", from: 0, to: 30 }],
  },
  {
    id: "pr",
    title: "评审团队 PR",
    status: "doing",
    tags: ["#后端", "#前端"],
    due: "今天 15:00",
    at: "15:00",
    start: [9, 11],
    end: [9, 12],
    progress: 0,
    urgency: 1,
    created: [9, 11],
    archived: false,
    related: ["mtg", "hr"],
    activities: [{ at: "昨天 17:20", text: "收集 PR 清单", kind: "log" }],
  },
  {
    id: "mtg",
    title: "准备周会材料",
    status: "doing",
    tags: ["#后端"],
    due: "09-15",
    at: null,
    start: [9, 11],
    end: [9, 15],
    progress: 0,
    urgency: 2,
    created: [9, 11],
    archived: false,
    related: ["week", "hr"],
    activities: [],
  },
  {
    id: "week",
    title: "写周报",
    status: "doing",
    tags: ["#工作"],
    due: "今天 17:00",
    at: "17:00",
    start: [9, 5],
    end: [9, 12],
    progress: 0,
    urgency: 3,
    created: [9, 5],
    archived: false,
    related: ["mentor"],
    activities: [],
  },
  {
    id: "budget",
    title: "核对家庭预算",
    status: "doing",
    tags: ["#生活"],
    due: "今天 20:00",
    at: "20:00",
    start: [9, 10],
    end: [9, 12],
    progress: 0,
    urgency: 2,
    created: [9, 10],
    archived: false,
    related: [],
    activities: [],
  },
  {
    id: "gym",
    title: "健身房训练",
    status: "doing",
    tags: ["#健康"],
    due: "今天 19:30",
    at: "19:30",
    start: [9, 12],
    end: [9, 12],
    progress: 0,
    urgency: 3,
    created: [9, 12],
    archived: false,
    related: [],
    activities: [],
  },
  {
    id: "meet",
    title: "晨会记录",
    status: "done",
    tags: ["#工作"],
    due: "今天 08:30",
    at: "08:30",
    start: [9, 12],
    end: [9, 12],
    progress: 100,
    urgency: 3,
    created: [9, 12],
    archived: false,
    related: [],
    activities: [{ at: "今天 08:30", text: "状态 → 已完成", kind: "status", from: "doing", to: "done" }],
  },
  {
    id: "bill",
    title: "整理本月开支",
    status: "overdue",
    tags: ["#生活"],
    due: "09-10",
    at: null,
    start: [9, 2],
    end: [9, 10],
    progress: 0,
    urgency: 0,
    created: [9, 2],
    archived: false,
    related: ["budget", "ins"],
    activities: [{ at: "昨天 21:30", text: "状态 待办 → 逾期", kind: "status", from: "todo", to: "overdue" }],
  },
  {
    id: "ins",
    title: "整理报销单据",
    status: "doing",
    tags: ["#生活"],
    due: "09-13",
    at: null,
    start: [9, 8],
    end: [9, 13],
    progress: 70,
    urgency: 2,
    created: [9, 8],
    archived: false,
    related: [],
    activities: [{ at: "昨天 15:12", text: "进度 50% → 70%", kind: "progress", from: 50, to: 70 }],
  },
  {
    id: "perf",
    title: "优化列表页性能",
    status: "doing",
    tags: ["#前端"],
    due: "09-16",
    at: null,
    start: [9, 9],
    end: [9, 16],
    progress: 45,
    urgency: 1,
    created: [9, 9],
    archived: false,
    related: ["ui", "login"],
    // 下午这一串是刻意造的密集数据：一个任务 7 条挤在 14:02–15:03（→ 轴上只占
    // 一个位置，写着「更新了 8 条记录」）。「挨太近」的另一种样子在下面 deploy /
    // mentor 那里：同一段里**三个任务**都动过 —— 那才是轴上合成一簇的情形
    // （轴是一个任务一个位置，簇说的是「几个任务挨太近」，不是「一个任务记了好几笔」）
    activities: [
      { at: "今天 09:12", text: "虚拟滚动方案评审", kind: "log" },
      { at: "今天 14:02", text: "对齐分页阈值", kind: "log" },
      { at: "今天 14:15", text: "改了三版滚动容器高度", kind: "log" },
      { at: "今天 14:28", text: "和后端确认游标字段", kind: "log" },
      { at: "今天 14:36", text: "补了 3 个边界用例", kind: "log" },
      { at: "今天 14:47", text: "首屏 1.2s → 0.6s", kind: "log" },
      { at: "今天 14:55", text: "提了 MR", kind: "log" },
      { at: "今天 15:03", text: "自测通过，等评审", kind: "log" },
    ],
  },
  {
    id: "doc",
    title: "更新使用手册",
    status: "doing",
    tags: ["#学习"],
    due: "09-17",
    at: null,
    start: [9, 10],
    end: [9, 17],
    progress: 40,
    urgency: 2,
    created: [9, 10],
    archived: false,
    related: [],
    activities: [{ at: "昨天 20:05", text: "补全 CLI 章节", kind: "progress", from: 20, to: 40 }],
  },
  {
    id: "mentor",
    title: "新员工 onboarding",
    status: "doing",
    tags: ["#工作"],
    due: "09-18",
    at: null,
    start: [9, 12],
    end: [9, 18],
    progress: 30,
    urgency: 2,
    created: [9, 12],
    archived: false,
    related: ["hr", "week"],
    // 同上：下午那段里的第三个任务（14:55 / 14:58 / 15:03 三个任务挤在一起）
    activities: [
      { at: "今天 07:50", text: "准备环境清单", kind: "progress", from: 0, to: 30 },
      { at: "今天 14:58", text: "带了一遍提测流程", kind: "log" },
    ],
  },
  {
    id: "book",
    title: "阅读《系统设计》第 5 章",
    status: "doing",
    tags: ["#学习"],
    due: "09-15",
    at: null,
    start: [9, 10],
    end: [9, 15],
    progress: 0,
    urgency: 3,
    created: [9, 10],
    archived: false,
    related: [],
    activities: [],
  },
  {
    id: "ui",
    title: "图标统一",
    status: "doing",
    tags: ["#前端"],
    due: "09-18",
    at: null,
    start: [9, 12],
    end: [9, 18],
    progress: 0,
    urgency: 2,
    created: [9, 12],
    archived: false,
    related: ["perf"],
    activities: [{ at: "09-09 16:40", text: "绘制 12 枚图标", kind: "log" }],
  },
  {
    id: "blog",
    title: "撰写技术博客",
    status: "doing",
    tags: ["#学习"],
    due: "09-19",
    at: null,
    start: [9, 12],
    end: [9, 19],
    progress: 20,
    urgency: 3,
    created: [9, 12],
    archived: false,
    related: ["doc", "book"],
    activities: [],
  },
  {
    id: "hr",
    title: "面试前端候选人",
    status: "doing",
    tags: ["#工作"],
    due: "09-14 10:30",
    at: null,
    start: [9, 12],
    end: [9, 14],
    progress: 0,
    urgency: 1,
    created: [9, 12],
    archived: false,
    related: [],
    activities: [],
  },
  {
    id: "med",
    title: "预约年度体检",
    status: "doing",
    tags: ["#健康"],
    due: "09-20",
    at: null,
    start: [9, 12],
    end: [9, 20],
    progress: 0,
    urgency: 2,
    created: [9, 12],
    archived: false,
    related: [],
    activities: [],
  },
  {
    id: "travel",
    title: "订国庆车票",
    status: "doing",
    tags: ["#生活"],
    due: "09-15",
    at: null,
    start: [9, 12],
    end: [9, 15],
    progress: 0,
    urgency: 2,
    created: [9, 12],
    archived: false,
    related: [],
    activities: [],
  },
  {
    id: "data",
    title: "数据备份演练",
    status: "doing",
    tags: ["#后端"],
    due: "09-21",
    at: null,
    start: [9, 15],
    end: [9, 21],
    progress: 0,
    urgency: 2,
    created: [9, 15],
    archived: false,
    related: ["ci", "deploy"],
    activities: [],
  },
  {
    id: "rev",
    title: "季度总结 PPT",
    status: "doing",
    tags: ["#工作"],
    due: "09-25",
    at: null,
    start: [9, 18],
    end: [9, 25],
    progress: 0,
    urgency: 3,
    created: [9, 18],
    archived: false,
    related: [],
    activities: [],
  },
  {
    id: "run",
    title: "晨跑 5 公里",
    status: "done",
    tags: ["#健康"],
    due: "昨天",
    at: null,
    start: [9, 11],
    end: [9, 11],
    progress: 100,
    urgency: 3,
    created: [9, 11],
    archived: false,
    related: [],
    activities: [{ at: "昨天 07:30", text: "状态 → 已完成", kind: "status", from: "doing", to: "done" }],
  },
  {
    id: "ci",
    title: "修复 CI 流水线",
    status: "done",
    tags: ["#后端"],
    due: "昨天",
    at: null,
    start: [9, 10],
    end: [9, 11],
    progress: 100,
    urgency: 1,
    created: [9, 10],
    archived: false,
    related: [],
    activities: [{ at: "昨天 18:44", text: "状态 → 已完成", kind: "status", from: "doing", to: "done" }],
  },
  {
    id: "cs",
    title: "回访客户反馈",
    status: "done",
    tags: ["#工作"],
    due: "09-10",
    at: null,
    start: [9, 9],
    end: [9, 10],
    progress: 100,
    urgency: 2,
    created: [9, 9],
    archived: false,
    related: [],
    activities: [{ at: "09-10 17:00", text: "状态 → 已完成", kind: "status", from: "doing", to: "done" }],
  },
  {
    id: "ebook",
    title: "整理电子书清单",
    status: "done",
    tags: ["#学习"],
    due: "09-09",
    at: null,
    start: [9, 7],
    end: [9, 9],
    progress: 100,
    urgency: 3,
    created: [9, 7],
    archived: false,
    related: [],
    activities: [{ at: "09-09 22:10", text: "状态 → 已完成", kind: "status", from: "doing", to: "done" }],
  },
  {
    id: "ref",
    title: "旧版重构收尾",
    status: "done",
    tags: ["#工作"],
    due: "08-30",
    at: null,
    start: [8, 30],
    end: [9, 8],
    progress: 100,
    urgency: 1,
    created: [8, 30],
    archived: true,
    related: [],
    activities: [{ at: "09-08 12:00", text: "状态 → 已完成", kind: "status", from: "doing", to: "done" }],
  },
];



// ─── 压测数据 ────────────────────────────────────────────────────────────────

/**
 * 在 28 条原型任务之外**再生成多少条**。
 *
 * 用来看「一屏画多少条」这类上限（`pages/shared.ts` 的 ROW_LIMIT / GANTT_LIMIT /
 * FEED_LIMIT）在大批量数据下的样子，也是交付时演示空间那 100 条的来源。
 *
 * **28（原型手写）+ 72（这里生成）= 100** —— 这个总数是验收口径（见 e2e 的
 * 「演示空间 100 条」），改动前先想清楚要验证的是什么。
 *
 * 生成而不是手写：100 条字面量没人维护得动，而这里要的只是「足够多、分布够乱」。
 * 取值是**确定性**的（全部由序号推出来），所以每次启动看到的是同一批 —— 随机
 * 生成会让「刚才那条去哪了」变成没法回答的问题。
 */
const STRESS_EXTRA = 72;

/**
 * 演示空间应有的任务总数：手写的原型任务 + 上面生成的压测任务。
 *
 * 注意这 100 条里**有 1 条是已归档的**（原型里那条例行样例，管理页的归档列要
 * 有东西可看），所以任务页只列得出 99 条 —— e2e 的交付口径断言两边一起数。
 */
export const DEMO_TASK_COUNT = 28 + STRESS_EXTRA;

const STRESS_VERBS = ["优化", "重构", "补齐", "排查", "整理", "评审", "联调", "上线"];
const STRESS_NOUNS = [
  "列表页性能",
  "接口响应",
  "单元测试",
  "权限校验",
  "构建流程",
  "埋点上报",
  "缓存策略",
  "异常日志",
  "文档站",
  "灰度开关",
];
const STRESS_TAGS = ["#工作", "#后端", "#前端", "#学习", "#生活", "#健康"];

/** 天数 → [月, 日]，与 TASKS 里手写的 `[9, 8]` 同一种格式。 */
function monthDayOf(day: number): MonthDay {
  const date = new Date(day * DAY_MS);
  return [(date.getUTCMonth() + 1) as MonthDay[0], date.getUTCDate() as MonthDay[1]];
}

function stressTasks(count: number): SeedTask[] {
  const out: SeedTask[] = [];

  for (let index = 0; index < count; index += 1) {
    // 结束日在今天前后 ±24 天里轮转：既有落在当前档位窗口里的，也有窗口外的 ——
    // 后者正好看得出任务页的「窗口自适应」把它们捞了回来
    const end = TODAY + ((index * 7) % 49) - 24;
    const start = end - ((index % 5) + 1);
    // 创建日必须在**过去**、而且要早于开始日：未来截止的任务，也是过去某天建的。
    // 以前这里图省事让「创建任务」这条活动落在 `min(截止日, 昨天…)` 上，于是
    // 截止日已过的任务，那条活动的时间**恰好等于它的截止日**（连钟点都一样，
    // 因为 due 和它共用 hour）—— 导出去看着就像「创建于截止日」
    const created = Math.min(start, TODAY - 1 - (index % 5));
    // 状态跟日期对得上：过去的要么做完了、要么逾期（逾期由 store 标），
    // 过去的里挑三分之一标成已完成，其余都是进行中 —— 不然会造出一批「截止已过却还在进行中」
    // （「待办」删掉之后这里只剩两档，见 types.ts 的 TaskStatus）
    const status: TaskStatus = end < TODAY && index % 3 === 0 ? "done" : "doing";
    const hour = 8 + ((index * 3) % 13);

    out.push({
      id: `bulk-${index + 1}`,
      title: `${STRESS_VERBS[index % STRESS_VERBS.length]}${
        STRESS_NOUNS[(index * 3) % STRESS_NOUNS.length]
      } ${pad2(index + 1)}`,
      status,
      tags:
        index % 3 === 0
          ? [STRESS_TAGS[index % STRESS_TAGS.length], STRESS_TAGS[(index + 2) % STRESS_TAGS.length]]
          : [STRESS_TAGS[index % STRESS_TAGS.length]],
      due: index % 2 === 0 ? `${monthDayText(end)} ${pad2(hour)}:00` : null,
      at: null,
      start: monthDayOf(start),
      end: monthDayOf(end),
      progress: status === "done" ? 100 : (index * 17) % 90,
      urgency: (index % 4) as Urgency,
      created: monthDayOf(created),
      archived: false,
      related: [],
      // 创建活动落在创建日（而不是截止日）：活动记的是**已经发生的事**，
      // 最自然的一条就是「哪天把这件任务建出来的」
      activities: [
        {
          at: `${monthDayText(created)} ${pad2(hour)}:${pad2((index * 7) % 60)}`,
          text: "创建任务",
          kind: "create",
        },
      ],
    });
  }

  return out;
}

// 先压时钟（那时还是人话），再换算成时间戳 —— 顺序反了就没得压
const SEEDS: SeedTask[] = [...SEED, ...stressTasks(STRESS_EXTRA)];
clampSeedClock(SEEDS);

/**
 * 种子的**唯一**实例：TASKS 会被库里的数据整个替换掉，补齐时得从这里取。
 *
 * 分区一律是演示空间（2026-09-17）。以前按标签匀到四个区，理由是「每个区都得
 * 有东西可看」—— 但那样一来每个区都只有几条，看不出规模，压测也压不出东西。
 * 这套数据现在的定位是：原型比对基准 + 功能与性能验收的数据源，100 条同处一区。
 * 老库里散出去的种子由 store 的 adoptSeedPartitions 搬回来。
 */
const SEED_TASKS: Task[] = SEEDS.map((task) => ({
  ...task,
  partition: DEMO_PARTITION_ID,
  activities: task.activities.map((activity) => ({ ...activity, at: seedStamp(activity.at) })),
}));

function cloneTask(task: Task): Task {
  return {
    ...task,
    tags: [...task.tags],
    start: [...task.start] as MonthDay,
    end: [...task.end] as MonthDay,
    created: [...task.created] as MonthDay,
    activities: task.activities.map((activity) => ({ ...activity })),
    related: [...task.related],
  };
}

export const TASKS: Task[] = SEED_TASKS.map(cloneTask);

/** 种子的一份深拷贝。启动补齐 / 将来做「重置演示数据」时用。 */
export const seedTasks = (): Task[] => SEED_TASKS.map(cloneTask);

/** 压测任务条数（见 STRESS_EXTRA）。大于 0 时启动会把缺的补进库里。 */
export const stressExtra = (): number => STRESS_EXTRA;

/**
 * 种子里写死的「今天 HH:MM」必须落在**过去**。
 *
 * 数据是字面量，而真机上的「现在」是一天里任意时刻 —— 写 15:03，早上九点打开
 * 就会看到一条「还没发生的活动」挂在轴上，而且因为时刻最大，它排在所有活动最
 * 前面，看着像是刚刚才发生的。所以把这一批整体往前压：最晚一条落在 5 分钟前，
 * 其余按原间隔等比跟着走（间隔还在，密集时段照样挤成一簇），最早不早于 6:00。
 */
function clampSeedClock(seed: SeedTask[]): void {
  const found: { minutes: number; write: (text: string) => void }[] = [];
  for (const task of seed) {
    for (const activity of task.activities) {
      const match = /^今天 (\d{2}):(\d{2})$/.exec(activity.at);
      if (!match) continue;
      found.push({
        minutes: Number(match[1]) * 60 + Number(match[2]),
        write: (text: string) => {
          activity.at = text;
        },
      });
    }
  }
  if (found.length === 0) return;

  const lo = 6 * 60;
  const hi = Math.min(23 * 60 + 55, Math.max(lo + 20, nowMinutes() - 5));
  const min = Math.min(...found.map((item) => item.minutes));
  const max = Math.max(...found.map((item) => item.minutes));
  if (max <= hi) return;

  const span = max - min || 1;
  for (const item of found) {
    const at = Math.round(lo + ((item.minutes - min) * (hi - lo)) / span);
    item.write(`今天 ${pad2(Math.floor(at / 60))}:${pad2(at % 60)}`);
  }
}

export const byId = (id: string): Task | undefined => TASKS.find((task) => task.id === id);

/**
 * 当前分区里的**全部**任务（含已归档）—— 只有管理页用它：那页要单列一列归档。
 *
 * 为什么单独立一个：`activeTasks()` 把「只看本分区」和「不看归档」两重过滤揉在一起。
 * 管理页当初为了放开归档而绕开它、直接读 `TASKS`，结果**把分区过滤也一起放开了** ——
 * 表现就是「切到一个空分区，总览 / 任务 / 图谱都空了，管理页却还列着别的分区的任务」，
 * 顺带把分区口令那道屏风也绕了过去。要放开归档，就只放开归档。
 */
export const partitionTasks = (): Task[] =>
  TASKS.filter((task) => task.partition === activePartitionId());

/**
 * 当前分区里的未归档任务 —— 除管理页的归档列之外，所有视图都只看这批。
 *
 * 分区过滤写在这里而不是各页面里：漏掉一处的后果是「切了分区，某个页面还显示
 * 别的分区的任务」，这种错误比性能问题难查得多。
 */
export const activeTasks = (): Task[] => partitionTasks().filter((task) => !task.archived);

export const countByStatus = (): Record<TaskStatus, number> => {
  const counts: Record<TaskStatus, number> = { overdue: 0, doing: 0, done: 0 };
  for (const task of activeTasks()) counts[task.status] += 1;
  return counts;
};

/** 每个标签挂多少个未归档任务。 */
export const tagCounts = (): Map<string, number> => {
  const counts = new Map<string, number>();
  for (const task of activeTasks()) {
    for (const tag of task.tags) counts.set(tag, (counts.get(tag) ?? 0) + 1);
  }
  return counts;
};
