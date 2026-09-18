// ─────────────────────────────────────────────────────────────────────────────
// 标签规则。
//
// 标签**不是固定集合**：用户在表单里写 `#新项目`，它就是一个新标签。原来图谱把
// 标签集合写死在六个预置名里，于是任何新标签在图上都不存在，连挂在它上面的任务
// 也一起消失 —— 那是把「演示数据里出现过什么」当成了「这个系统允许什么」。
//
// 这里收三件事：预置标签的顺序、怎么把用户输入解析成标签、当前数据里有哪些标签。
// ─────────────────────────────────────────────────────────────────────────────

import type { Task } from "./types";

/**
 * 预置标签。只用来定**顺序**（图谱环上的排布先后）：预置的在前，新标签按字面
 * 排在后面。不复存在「只有这些才算标签」的意思。
 *
 * ⚠️ 别和 data/partitions.ts 的分区名混起来：分区是**数据的隔离边界**
 * （工作 / 学习 / 个人 / 演示空间），标签是任务身上的一个维度。两者名字会撞
 * ——分区「工作」与标签「#工作」——所以标签一律带 `#`，分区名一律不带，图谱上
 * 分区节点还额外挂一枚「分区」小签。演示数据里恰好按标签粗分了组（`#学习` 的任务
 * 多数落在「学习」分区），那是**种子数据的巧合**，不是系统规则。
 */
export const SEED_TAGS = ["#工作", "#后端", "#前端", "#学习", "#生活", "#健康"];

/** 一个任务最多几个标签。 */
export const MAX_TAGS = 3;

/**
 * 没有标签的任务在图上归到这里。新建已不允许无标签，但历史数据里可能还有。
 *
 * 故意**不带 `#`**：`#` 是标签的记法，而这一项不是一个标签，是「没有标签」这件事。
 * 同理，分区名也不带 `#` —— 三者靠记法就能分开：标签带 `#`，分区是数据的隔离边界。
 */
export const UNTAGGED = "未分类";

/**
 * 把输入框里的一串字解析成标签。
 *
 * 带不带 `#` 都认：写「学习 工作」和写「#学习 #工作」是一回事。以前只认带 `#` 的
 * 写法，于是「学习 工作」被解析成空数组 —— 新建时被兜底成单个 `#工作`（用户看到
 * 的就是「我维护了好几个标签，列表里只剩一个」），编辑时则是静默清空。
 *
 * 超上限的部分不静默丢弃：返回 dropped 让调用方提示。
 */
export function normalizeTags(input: string): { tags: string[]; dropped: string[] } {
  const names = input
    .split(/[\s,，、;；]+/)
    .map((piece) => piece.replace(/^#+/, "").trim())
    .filter(Boolean);

  const seen = new Set<string>();
  const tags: string[] = [];
  const dropped: string[] = [];

  for (const name of names) {
    const tag = `#${name}`;
    if (seen.has(tag)) continue;
    seen.add(tag);
    if (tags.length >= MAX_TAGS) dropped.push(tag);
    else tags.push(tag);
  }

  return { tags, dropped };
}

/** 当前这批任务里出现过的标签：预置的按预置顺序在前，其余按字面排序。 */
export function tagsInUse(tasks: Task[]): string[] {
  const present = new Set(tasks.flatMap((task) => task.tags).filter((tag) => tag && tag !== UNTAGGED));
  const known = SEED_TAGS.filter((tag) => present.has(tag));
  const rest = [...present].filter((tag) => !SEED_TAGS.includes(tag)).sort();
  return [...known, ...rest];
}
