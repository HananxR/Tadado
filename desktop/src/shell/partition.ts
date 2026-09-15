// ─────────────────────────────────────────────────────────────────────────────
// 分区切换（rail 底部）。
//
// 分区列表将来由 AppConfig 提供（DESIGN.md 2.13 配置驱动），当前是内置常量：
// 这一步只打通「选中 → 广播」的通道，页面接入后订阅 onPartitionChange 即可。
// ─────────────────────────────────────────────────────────────────────────────

import { el, need } from "./dom";
import { toast } from "./toast";

export interface Partition {
  id: string;
  name: string;
}

const PARTITIONS: Partition[] = [
  { id: "work", name: "工作" },
  { id: "study", name: "学习" },
  { id: "personal", name: "个人" },
  { id: "demo", name: "演示空间" },
];

let active = PARTITIONS[0];

const listeners = new Set<(partition: Partition) => void>();

export const activePartition = (): Partition => active;

export function onPartitionChange(listener: (partition: Partition) => void): void {
  listeners.add(listener);
}

function select(partition: Partition): void {
  if (partition.id === active.id) return;
  active = partition;
  for (const listener of listeners) listener(partition);
}

function close(pop: HTMLElement): void {
  pop.classList.remove("open");
}

export function mountPartition(): void {
  const button = need("#part-btn");
  const pop = need("#part-pop");

  const items = PARTITIONS.map((partition) => {
    const node = el("div", {
      class: partition.id === active.id ? "part-item on" : "part-item",
      "data-part": partition.id,
    }, [el("span", { text: partition.name })]);

    node.addEventListener("click", () => {
      select(partition);
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
  button.title = `分区：${active.name}`;

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
