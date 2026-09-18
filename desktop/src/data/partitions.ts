// ─────────────────────────────────────────────────────────────────────────────
// 分区：数据的隔离边界。
//
// 原版（PySide6）里分区是数据模型的一部分 —— 任务、标签、活动都挂在某个分区下，
// 切分区等于换一批数据。桌面端此前只有一个写死的分区名：rail 底部那个切换器能点，
// 点了只是弹一个 toast，页面上一个字都没变。
//
// 放在 data/ 而不是 shell/：`mock.activeTasks()` 要按分区过滤，而数据层不该反过来
// 依赖外壳。shell/partition.ts（rail 底部那个按钮）从这里取列表和当前值。
// ─────────────────────────────────────────────────────────────────────────────

import { loadSetting, saveSetting } from "./db";
import { asPartitionList } from "./schema";

export interface Partition {
  id: string;
  name: string;
}

/**
 * 演示空间：**样例数据都在这里**（100 条，见 data/mock.ts），也是首次启动的落点。
 *
 * 其他分区从零开始 —— 空分区不是「数据没加载出来」，而是「这里本来就还没东西」。
 * 交付状态就是这一条：演示空间 100 条，其余分区为空。
 */
export const DEMO_PARTITION_ID = "demo";

export const PARTITIONS: Partition[] = [
  { id: "work", name: "工作" },
  { id: "study", name: "学习" },
  { id: "personal", name: "个人" },
  { id: DEMO_PARTITION_ID, name: "演示空间" },
];

type Listener = (partition: Partition) => void;

const listeners = new Set<Listener>();

const demo = (): Partition =>
  PARTITIONS.find((partition) => partition.id === DEMO_PARTITION_ID) ?? PARTITIONS[0];

let active: Partition = demo();
/** 启动时进哪个分区（见文件下方「默认分区」一节）。 */
let defaultId = DEMO_PARTITION_ID;

export const activePartition = (): Partition => active;
export const activePartitionId = (): string => active.id;
export const partitionName = (id: string): string =>
  PARTITIONS.find((partition) => partition.id === id)?.name ?? id;

export function onPartitionChange(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** 切分区。值没变就不广播 —— 重复广播会让各页面白重建一遍。 */
export function setPartition(id: string): void {
  const next = PARTITIONS.find((partition) => partition.id === id);
  if (!next || next.id === active.id) return;
  active = next;
  for (const listener of listeners) listener(next);
}

// ─── 增删 ────────────────────────────────────────────────────────────────────
//
// 以前这张表写死四个，设置里只能看、不能动 —— 而分区本来就是用户自己怎么分都行
// 的东西。现在列表可增删改名、存进库，名字和口令都跟着分区走。

const KEY_LIST = "partitions.list";
const KEY_DEFAULT = "partitions.default";

type ListListener = () => void;
const listListeners = new Set<ListListener>();

/** 列表本身变了（增删改名）—— 设置面板那一页要重画，光靠切分区的订阅不够。 */
export function onPartitionListChange(listener: ListListener): () => void {
  listListeners.add(listener);
  return () => {
    listListeners.delete(listener);
  };
}

const emitList = (): void => {
  for (const listener of listListeners) listener();
};

const persist = (): void => {
  void saveSetting(KEY_LIST, JSON.stringify(PARTITIONS));
};

/**
 * 启动：有存档就用存档 —— 用户自己分过的区不能被内置那四个盖回去。
 *
 * 落点是**默认分区**，不是列表第一个：以前只恢复列表，active 恒等于 PARTITIONS[0]，
 * 于是把自己常用的那个排在第二位的人，每次打开都得再切一次。
 */
export async function bootPartitions(): Promise<void> {
  const raw = await loadSetting(KEY_LIST);
  if (typeof raw === "string" && raw) {
    try {
      // 形状不对就当没存过（内置那四个还在）：以前只判了「是不是数组」，
      // 于是 `[{"id":1}]` 这种半对的存档能进来，页面上一片空白却不报错
      const saved = asPartitionList(JSON.parse(raw) as unknown);
      if (saved) {
        PARTITIONS.length = 0;
        PARTITIONS.push(...saved);
      }
    } catch {
      // 存档坏了就当没存过，内置的四个还在
    }
  }

  const savedDefault = await loadSetting<string>(KEY_DEFAULT);
  if (typeof savedDefault === "string" && PARTITIONS.some((p) => p.id === savedDefault)) {
    defaultId = savedDefault;
  }
  active = PARTITIONS.find((partition) => partition.id === defaultPartitionId()) ?? demo();

  emitList();
}

// ─── 默认分区 ────────────────────────────────────────────────────────────────
//
// 启动时进哪个区，和「现在在哪个区」是两件事：开机进默认的那个，之后随便切，
// 默认不变 —— 否则「默认」就等于「最后一次」，而切分区是随时都在做的事。

/** 默认分区。存档里那个 id 已经不在列表里（被删了 / 存档坏了）就退回第一个。 */
export const defaultPartitionId = (): string =>
  PARTITIONS.some((partition) => partition.id === defaultId) ? defaultId : PARTITIONS[0].id;

export function setDefaultPartition(id: string): void {
  const next = PARTITIONS.find((partition) => partition.id === id);
  if (!next || next.id === defaultId) return;
  defaultId = next.id;
  void saveSetting(KEY_DEFAULT, id);
  // 设置面板里那排单选点要跟着变：反正它订阅了列表变更、会重画整段，复用即可
  emitList();
}

export function addPartition(name: string): Partition {
  const partition: Partition = { id: `p${Date.now().toString(36)}`, name };
  PARTITIONS.push(partition);
  persist();
  emitList();
  return partition;
}

export function renamePartition(id: string, name: string): void {
  const partition = PARTITIONS.find((item) => item.id === id);
  if (!partition) return;
  partition.name = name;
  persist();
  emitList();
  // 名字显示在 rail 底部那个切换器上，改的是当前分区就得让它跟着变
  if (active.id === id) for (const listener of listeners) listener(partition);
}

/**
 * 删分区，至少留一个 —— 一个都不剩时 activeTasks() 返回空，五个页面全空，
 * 看着像数据丢了。
 *
 * 任务迁移交给调用方：这里在 data 层，不能反过来 import mock 里的 TASKS。
 */
export function removePartition(id: string): boolean {
  if (PARTITIONS.length <= 1) return false;
  const index = PARTITIONS.findIndex((partition) => partition.id === id);
  if (index === -1) return false;
  PARTITIONS.splice(index, 1);
  persist();

  // 删掉的正好是默认分区：落点得换一个，不然下次启动对着一个不存在的 id，
  // 退回第一个是唯一的自动选择（交给用户选的话，「删分区」就得再配一个对话框）
  if (defaultId === id) {
    defaultId = PARTITIONS[0].id;
    void saveSetting(KEY_DEFAULT, defaultId);
  }

  emitList();
  if (active.id === id) setPartition(demo().id);
  return true;
}
