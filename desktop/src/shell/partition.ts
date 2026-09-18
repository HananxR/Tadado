// ─────────────────────────────────────────────────────────────────────────────
// 分区切换（rail 底部）。
//
// 列表与当前值都在 data/partitions.ts：分区是数据的隔离边界，
// mock.activeTasks() 按它过滤，所以外壳不能自己另存一份。
// 将来由 AppConfig 提供（DESIGN.md 2.13 配置驱动），那时候只换那个模块的取值方式。
// ─────────────────────────────────────────────────────────────────────────────

import {
  PARTITIONS,
  activePartition,
  onPartitionChange,
  onPartitionListChange,
  setPartition,
  type Partition,
} from "../data/partitions";
import { dataChanged } from "../data/store";
import { hasPassword, isUnlocked, syncScreen } from "./lock";
import { el, need } from "./dom";
import { toast } from "./toast";

export type { Partition } from "../data/partitions";

function close(pop: HTMLElement): void {
  pop.classList.remove("open");
}

export function mountPartition(): void {
  const button = need("#part-btn");
  const pop = need("#part-pop");

  const itemOf = (partition: Partition): HTMLElement => {
    const node = el("div", {
      class: partition.id === activePartition().id ? "part-item on" : "part-item",
      "data-part": partition.id,
    }, [
      el("span", { text: partition.name }),
      // 上锁的分区标出来：不然只能靠点了才知道要口令
      ...(hasPassword(partition.id)
        ? [el("span", { class: "lock", text: isUnlocked(partition.id) ? "🔓" : "🔒" })]
        : []),
    ]);

    node.addEventListener("click", () => {
      const before = activePartition().id;
      setPartition(partition.id);
      // 分区不是任务数据，但各页面都要按它重画一遍，所以走同一个广播 ——
      // 让页面再去订阅一个「分区变更」事件，等于多一条必须记得订阅的通知
      if (before !== partition.id) dataChanged();
      // 锁屏跟着这次切换走：切到上锁的分区就挡一层
      syncScreen();
      for (const other of pop.querySelectorAll(".part-item")) {
        other.classList.toggle("on", other === node);
      }
      close(pop);
      toast(`已切换至分区「${partition.name}」`);
    });

    return node;
  };

  // 分区能在设置里增删改名了，所以这个菜单也得能重画 —— 只画一次的话，新建的分区
  // 在这儿永远找不到，改名也只对不上
  const paint = (): void => {
    pop.replaceChildren(...PARTITIONS.map(itemOf));
    button.title = `分区：${activePartition().name}`;
  };

  paint();
  onPartitionListChange(paint);
  onPartitionChange(paint);

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
