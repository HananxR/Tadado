// ─────────────────────────────────────────────────────────────────────────────
// 分区切换（rail 底部）。
//
// 列表与当前值都在 data/partitions.ts：分区是数据的隔离边界，
// mock.activeTasks() 按它过滤，所以外壳不能自己另存一份。
// 将来由 AppConfig 提供（DESIGN.md 2.13 配置驱动），那时候只换那个模块的取值方式。
//
// 2026-09-20 改版。改之前这条路只有 rail 底部一个**文件夹图标**，当前分区的名字只在
// 它的 title 里 —— **要悬浮才看得见自己在哪个区**；弹层里则只有一块淡底色表示当前项。
// 现在：
//   · 图标下面**写着分区名**（rail 64px，一行四个汉字够用；超长截断，全文在 title 里）；
//   · 每一项带**勾选标记**（底色之外还有一个明确的记号）、**口令状态**、**任务条数**；
//   · 按钮角上带**锁角标**（当前分区有口令时）。
// ─────────────────────────────────────────────────────────────────────────────

import { TASKS } from "../data/mock";
import {
  PARTITIONS,
  activePartition,
  onPartitionChange,
  onPartitionListChange,
  setPartition,
  type Partition,
} from "../data/partitions";
import { dataChanged } from "../data/store";
import { hasPassword, isUnlocked, onLockChange, syncScreen } from "./lock";
import { el, need } from "./dom";
import { toast } from "./toast";

export type { Partition } from "../data/partitions";

/** 分区弹层里用到的几个图标（勾选 / 开锁 / 闭锁）。 */
const PART_ICON = {
  check:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
  locked:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linejoin="round"><rect x="5" y="10.5" width="14" height="9.5" rx="2"/><path d="M8 10.5V8a4 4 0 018 0v2.5"/></svg>',
  open: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linejoin="round"><rect x="5" y="10.5" width="14" height="9.5" rx="2"/><path d="M8 10.5V8a4 4 0 017.2-2.4"/></svg>',
};

/** 当前分区是否**此刻锁着**（有口令，且本次运行里没解锁过）。 */
const isLocked = (id: string): boolean => hasPassword(id) && !isUnlocked(id);

/**
 * 口令状态用哪个图标表示；没设过口令的返回 `null`（不画锁）。
 *
 * 为什么「解锁中」也画锁：它有口令、只是这次进来时解开了，而空闲若干分钟后会自己
 * 锁上 —— 那正是用户需要知道的。反之给没设口令的分区画一把锁，读起来像「它锁着」。
 */
const lockIconOf = (id: string): string | null =>
  !hasPassword(id) ? null : isUnlocked(id) ? PART_ICON.open : PART_ICON.locked;

function close(pop: HTMLElement): void {
  pop.classList.remove("open");
}

export function mountPartition(): void {
  const button = need("#part-btn");
  const cap = need("#part-cap");
  const capLock = need("#part-lock");
  const pop = need("#part-pop");

  const itemOf = (partition: Partition): HTMLElement => {
    const current = partition.id === activePartition().id;
    const lock = lockIconOf(partition.id);
    const count = TASKS.filter((task) => task.partition === partition.id).length;

    const node = el(
      "div",
      {
        class: current ? "part-item on" : "part-item",
        "data-part": partition.id,
        title: current
          ? `${partition.name}（当前分区，${count} 条任务）`
          : `${partition.name} · ${count} 条任务`,
      },
      [
        // 勾选标记。**不能只靠底色**：底色同时被 :hover 用着，扫一眼分不出
        // 「当前项」和「鼠标正停在这一项上」
        el("span", { class: "pt-tick", html: current ? PART_ICON.check : "" }),
        el("span", { class: "pt-name", text: partition.name }),
        // 上锁的分区标出来：不然只能靠点了才知道要口令
        ...(lock === null ? [] : [el("span", { class: "pt-lock", html: lock })]),
        // 条数：让「隔离边界」有实感，也是选分区时的依据
        el("span", { class: "cnt", text: String(count) }),
      ],
    );

    node.addEventListener("click", () => {
      const before = activePartition().id;
      setPartition(partition.id);
      // 分区不是任务数据，但各页面都要按它重画一遍，所以走同一个广播 ——
      // 让页面再去订阅一个「分区变更」事件，等于多一条必须记得订阅的通知
      if (before !== partition.id) dataChanged();
      // 锁屏跟着这次切换走：切到上锁的分区就挡一层
      syncScreen();
      // 选中态交给 paint()：它重画整列，勾选标记与底色一起换。手动改 class 的话
      // 勾还留在原来那一项上（标记是画的时候带上的）
      close(pop);
      toast(`已切换至分区「${partition.name}」`);
    });

    return node;
  };

  // 分区能在设置里增删改名了，所以这个菜单也得能重画 —— 只画一次的话，新建的分区
  // 在这儿永远找不到，改名也只对不上
  const paint = (): void => {
    pop.replaceChildren(...PARTITIONS.map(itemOf));

    const partition = activePartition();
    const locked = isLocked(partition.id);
    const lock = lockIconOf(partition.id);

    // 名字写在图标下面。rail 有 64px，一行放得下四五个汉字 —— 在这之前名字只在 title
    // 里，也就是**要悬浮才知道自己在哪个区**；而这是随时要能答上来的问题。超长的名字
    // 由 CSS 截断，完整值仍在 title 里
    cap.textContent = partition.name;
    // 锁画在名字**旁边**，不是图标角上：13px 的角标在这个尺寸下认不出是锁
    // （看起来就是个方点），而跟名字排在一行、10px 的它读起来是「名字 + 状态」
    capLock.innerHTML = lock ?? "";
    capLock.title =
      lock === null
        ? ""
        : locked
          ? "该分区已锁定"
          : "该分区有口令，已解锁（空闲后自动上锁）";

    button.title = locked ? `分区：${partition.name}（已锁定）` : `分区：${partition.name}`;
  };

  paint();
  onPartitionListChange(paint);
  onPartitionChange(paint);
  // 解锁 / 上锁（含空闲自动锁）也要跟着改：不然角标与列表里的锁停在旧状态
  onLockChange(paint);

  button.addEventListener("click", (event) => {
    // 阻止冒泡，否则会立刻被下面的 document 监听关掉
    event.stopPropagation();
    pop.classList.toggle("open");
  });

  document.addEventListener("click", (event) => {
    const target = event.target as Node | null;
    if (target && !button.closest(".part-wrap")?.contains(target)) close(pop);
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") close(pop);
  });
}
