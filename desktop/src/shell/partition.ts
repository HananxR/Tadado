// ─────────────────────────────────────────────────────────────────────────────
// 分区切换（rail 底部）。
//
// 列表与当前值都在 data/partitions.ts：分区是数据的隔离边界，
// mock.activeTasks() 按它过滤，所以外壳不能自己另存一份。
// 将来由 AppConfig 提供（DESIGN.md 2.13 配置驱动），那时候只换那个模块的取值方式。
// ─────────────────────────────────────────────────────────────────────────────

import { PARTITIONS, activePartition, setPartition } from "../data/partitions";
import { dataChanged } from "../data/store";
import { hasPassword, isUnlocked, syncScreen } from "./lock";
import { el, need } from "./dom";
import { toast } from "./toast";

export type { Partition } from "../data/partitions";

function select(partition: { id: string; name: string }): void {
  const before = activePartition().id;
  setPartition(partition.id);
  if (before === partition.id) return;
  // 分区不是任务数据，但各页面都要按它重画一遍，所以走同一个广播 ——
  // 让页面再去订阅一个「分区变更」事件，等于多一条必须记得订阅的通知。
  dataChanged();
}

function close(pop: HTMLElement): void {
  pop.classList.remove("open");
}

export function mountPartition(): void {
  const button = need("#part-btn");
  const pop = need("#part-pop");

  const items = PARTITIONS.map((partition) => {
    const locked = hasPassword(partition.id);
    const node = el("div", {
      class: partition.id === activePartition().id ? "part-item on" : "part-item",
      "data-part": partition.id,
    }, [
      el("span", { text: partition.name }),
      // 上锁的分区标出来：不然只能靠点了才知道要口令
      ...(locked ? [el("span", { class: "lock", text: isUnlocked(partition.id) ? "🔓" : "🔒" })] : []),
    ]);

    node.addEventListener("click", () => {
      select(partition);
      // 锁屏跟着这次切换走：切到上锁的分区就挡一层
      syncScreen();
      for (const other of pop.querySelectorAll(".part-item")) {
        other.classList.toggle("on", other === node);
      }
      button.title = `分区：${partition.name}`;
      close(pop);
      toast(`已切换至分区「${partition.name}」`);
    });

    return node;
  });

  pop.replaceChildren(...items);
  button.title = `分区：${activePartition().name}`;

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
