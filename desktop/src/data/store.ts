// ─────────────────────────────────────────────────────────────────────────────
// 数据变更通知。
//
// 样例数据是**可变的**：在维护抽屉里改进度、把任务标记完成，总览的指标卡、
// 任务页的色条、管理页的表格都得跟着变 —— 这正是要让人看出来的「实际效果」。
//
// 这里刻意只做一个「有人改了数据」的广播，不引入响应式框架：页面各自订阅、
// 各自重建自己那棵树。规模到不了需要 diff 的地步，全量重建反而更好读、更少 bug。
//
// 数据在启动时装进 mock 的 TASKS 数组（TASKS.length = 0 再 push，而不是换一个新
// 数组 —— 各页面持有的是同一个引用，换引用等于让它们继续读旧数据）。
// 写路径也只有一处：改完数据的人调用 dataChanged()，由它落盘 + 广播。
// ─────────────────────────────────────────────────────────────────────────────

import { loadSetting, loadTasks, saveSetting, saveTasks } from "./db";
import { TASKS, seedTasks, stressExtra } from "./mock";
import { DEMO_PARTITION_ID, activePartitionId } from "./partitions";
import { asNumberRecord } from "./schema";
import { TODAY, dayNumber } from "./time";
import type { Task } from "./types";

type Listener = () => void;

const listeners = new Set<Listener>();

/**
 * 逾期标记。写在 store 而不是页面里：它是数据自身的状态，所有页面都该看到同一份。
 *
 * 为什么必须有：`TODAY` 读真实时钟，而状态是数据里写死的 —— 截止 09-12 没做完的
 * 任务，到了 09-15 还显示「待办」。没有这一步，时间轴上的逾期色、总览的
 * 「最早逾期」全在说谎。
 *
 * 只从 `todo` 标成 `overdue`，**不动 `doing`**：用户手动设的「进行中」如果下一秒
 * 就被系统改成逾期，那个下拉框就像坏了。已完成的更不会动 —— done 优先。
 */
function refreshOverdue(tasks: Task[]): void {
  for (const task of tasks) {
    if (task.status === "done" || task.status === "doing") continue;
    if (dayNumber(task.end) < TODAY) task.status = "overdue";
    else if (task.status === "overdue") task.status = "todo";
  }
}

// 活动时刻的归一化（展示串 → 时间戳）已经搬到**读入口**：data/schema.ts 的
// normalizeTasks 顺手把字段缺失、类型不对一起处理掉了。两份归位逻辑并存的结果
// 是「都修好了，但没人知道哪一份说了算」。

/**
 * 演示数据归位：种子里的任务一律落在**演示空间**（见 data/mock.ts 的 SEED_TASKS）。
 *
 * 为什么要在启动时做：早先这套数据按标签散在「工作 / 学习 / 个人 / 演示空间」
 * 四个区里，老库里就是那个样子。交付口径是「演示空间 100 条、其他分区为空」，
 * 光改种子只对全新安装成立 —— 已经写过库的那台机器上，散出去的还在原地。这里
 * 把它们搬回来，让这个口径在任何一台机器上都成立。
 *
 * 只动**种子 id**：用户自己建的任务不在这个集合里，一条都不碰（分区是他的）。
 */
function adoptSeedPartitions(tasks: Task[]): number {
  const seedIds = new Set(seedTasks().map((task) => task.id));
  let moved = 0;

  for (const task of tasks) {
    if (!seedIds.has(task.id) || task.partition === DEMO_PARTITION_ID) continue;
    task.partition = DEMO_PARTITION_ID;
    moved += 1;
  }

  return moved;
}

const KEY_ARCHIVE = "archive.afterDays";

/**
 * 自动归档：分区 id → 已完成任务结束 N 天后收进归档，0 = 不自动归档（默认）。
 *
 * **按分区**设：工作区的任务过期就该收走，个人区那几条想留着翻 —— 一个全局值只能
 * 取折中，结果两头都不对。
 */
let archiveDays: Record<string, number> = {};

/** 这次会话里被手动「取消归档」的任务 —— 自动归档不再碰，否则刚恢复就没了。 */
const restored = new Set<string>();

/**
 * 已完成、且结束日过了 N 天的任务自动归档。
 *
 * 用**结束日**而不是完成日：完成日要从活动记录里反推，而解析函数在 pages 层，
 * store 在 data 层，反过来 import 会把依赖方向搞乱。结束日只可能晚于完成日，
 * 晚几天归档，比把还在用的数据收走安全。
 */
function refreshArchive(tasks: Task[]): void {
  for (const task of tasks) {
    if (task.archived || task.status !== "done" || restored.has(task.id)) continue;
    const days = archiveDays[task.partition] ?? 0;
    if (days > 0 && dayNumber(task.end) + days <= TODAY) task.archived = true;
  }
}

export const archiveAfterDays = (id: string = activePartitionId()): number =>
  archiveDays[id] ?? 0;

/** 手动取消归档：本次会话内自动归档不再动这条。 */
export const keepActive = (id: string): void => {
  restored.add(id);
};

/** 改归档天数会立刻扫一遍 —— 拨完开关当场能看见哪些任务被收走了。 */
export async function setArchiveDays(days: number, id: string = activePartitionId()): Promise<void> {
  archiveDays[id] = days;
  await saveSetting(KEY_ARCHIVE, archiveDays);
  refreshArchive(TASKS);
  dataChanged();
}

/**
 * 启动。有存档就用存档，没有就把种子数据写进去 ——
 * 之后一律以库为准，用户改过的东西不会被下一次启动覆盖。
 */
export async function bootStore(): Promise<void> {
  const result = await loadTasks();

  // 库在、数据却读不出来（存档损坏 / 库故障）：**绝不能拿种子盖上去**。
  // 盖上之后「打不开」就变成了「数据没了」，而且写入会覆盖掉原本还能人工捞
  // 回来的那份。这里只把内存清空、广播一次，等外壳把原因说给用户听
  if (result.issue !== null) {
    TASKS.length = 0;
    broadcast();
    return;
  }

  const saved = result.tasks;
  if (saved && saved.length > 0) {
    TASKS.length = 0;
    TASKS.push(...saved);

    // 压测模式（STRESS_EXTRA > 0）下让**种子说了算**：
    //   · 缺的补进来（改完 STRESS_EXTRA 就多出几十条）
    //   · 已有的 `bulk-*` 用种子里的版本**覆盖**（改了生成逻辑，刷新就看得见）
    // 这条路径只在压测时走。正常情况一律「以库为准」，用户删掉的任务不该在
    // 下一次启动又冒出来 —— 覆盖也只覆盖 `bulk-*`：那批是自动生成的演示数据，
    // 不是用户资产；上面手写的 28 条原型任务仍然尊重库里的版本。
    if (stressExtra() > 0) {
      const index = new Map(TASKS.map((task, at) => [task.id, at]));
      for (const task of seedTasks()) {
        const at = index.get(task.id);
        if (at === undefined) TASKS.push(task);
        else if (task.id.startsWith("bulk-")) TASKS[at] = task;
      }
      saveTasks(TASKS);
    }
  } else {
    saveTasks(TASKS);
  }

  // 结构层面的修补（缺字段、旧展示串时刻、非法枚举）已经在读入口做完了
  // （data/schema.ts）；这里只做**业务上的搬移**：散在别的分区里的演示数据
  // 回到演示空间
  if (adoptSeedPartitions(TASKS) > 0) saveTasks(TASKS);

  // 隔夜再打开时，昨天「待办」的任务今天可能已经过期了
  refreshOverdue(TASKS);
  // 存档的形状不对就当没设过：以前是读出来直接用，存档要是个数组，
  // `archiveDays[id]` 全是 undefined，界面上一片空白却不报错
  archiveDays = asNumberRecord(await loadSetting<Record<string, number>>(KEY_ARCHIVE));
  refreshArchive(TASKS);
  dataChanged();
}

/** 订阅数据变更，返回退订函数。 */
export function onDataChange(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** 只广播、不落盘 —— 给「内存变了但绝不能写盘」的场合用（见 bootStore 的库故障分支）。 */
function broadcast(): void {
  for (const listener of listeners) listener();
}

/**
 * 数据已变更 —— 由修改数据的一方在改完之后调用。
 * 先落盘再广播：万一落盘抛错，至少页面这一帧还是对的，而不是「改了但没存上」。
 */
export function dataChanged(): void {
  // 每次变更都重算一遍逾期：改了截止（往前挪到今天之前）要立刻看出来，
  // 把截止挪回未来则要退回待办。一百条数据扫一遍不值一提
  refreshOverdue(TASKS);
  saveTasks(TASKS);
  broadcast();
}
