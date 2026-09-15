// ─────────────────────────────────────────────────────────────────────────────
// 任务图谱页：分区 / 标签 / 任务的关系网络。
//
// 布局是**确定性**的，不是力导向。原型把这个视图写成「力导向布局画布」，
// 但真跑起来的力导向每次刷新都给出不同形状 —— 同一个任务这次在左上、
// 下次在右下，看久了什么都记不住，而且拖动一个节点会让整张图跟着漂。
// 这里改成：分区在圆心，标签铺一圈，任务挂在各自主标签外侧的弧上。
// 位置固定 ⇒ 可以凭肌肉记忆找到节点；拖动只影响被拖的那一个。
//
// 多标签任务只挂到一个标签下（TAG_NAMES 里最靠前的那个），否则一个任务在
// 图上会出现两次，「双击直达任务」就有了两个一模一样的入口。
//
// 数据变更时整页重建：节点集合、位置、连线、统计都得跟着换，增量改的代码比
// 重建还多。代价是缩放和拖动会被重置 —— 数据都变了，布局本来就该重排。
// ─────────────────────────────────────────────────────────────────────────────

import { TAG_NAMES, activeTasks } from "../data/mock";
import { activePartition } from "../data/partitions";
import { onDataChange } from "../data/store";
import type { Task } from "../data/types";
import { el } from "../shell/dom";
import { subscribePages } from "../shell/router";
import { toast } from "../shell/toast";
import { jumpToTask } from "./focus";
import { STATUS_LABEL, dayNumber, monthDayText, statusVar } from "./shared";

/** 组内任务的角间距。0.125 是「7 个任务不出组」的上界附近。 */
const TASK_SPREAD = 0.125;

/** 标题栏 + 工具行 + 页头 + 图例占掉的高度，量舞台高度时要扣掉。 */
const CHROME_H = 268;

const SVG_NS = "http://www.w3.org/2000/svg";

const ICON = {
  plus: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>',
  minus:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 12h14"/></svg>',
  reset:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M3.5 12a8.5 8.5 0 1 0 2.6-6.1M3.5 4.5V10h5.5"/></svg>',
};

type NodeKind = "partition" | "tag" | "task";

interface GraphNode {
  id: string;
  kind: NodeKind;
  label: string;
  task?: Task;
}

interface Point {
  x: number;
  y: number;
}

interface Edge {
  a: string;
  b: string;
  line: SVGPathElement;
}

const FILTERS = ["全部", "紧急与重要", "进行中"] as const;
type Filter = (typeof FILTERS)[number];

let filter: Filter = "全部";

function passesFilter(task: Task): boolean {
  if (filter === "紧急与重要") return task.urgency <= 1;
  if (filter === "进行中") return task.status === "doing";
  return true;
}

/** 任务的主标签：TAG_NAMES 里最靠前的那一个，保证归组唯一。 */
function primaryTag(task: Task): string | null {
  return TAG_NAMES.find((tag) => task.tags.includes(tag)) ?? null;
}

function legendDot(background: string, border?: string): HTMLElement {
  const node = el("span", { class: "d" });
  node.style.background = background;
  if (border) node.style.border = border;
  return node;
}

// ─── 挂载 ────────────────────────────────────────────────────────────────────

let host: HTMLElement | null = null;

export function mount(target: HTMLElement): void {
  host = target;

  // 舞台按量出来的可用空间铺开。以前写死 900×520：窗口再宽，一圈任务也只占据
  // 中间一小块，四周是空的点阵底纹，图看着又小又偏。现在宽高都跟着容器走，
  // 两个半径按比例取 —— 舞台变大时节点会一起散开，而不是继续挤在中心。
  // 页面隐藏时 clientWidth 量不到（display:none 下是 0），兜一个够用的宽度，
  // 切回前台会重画一次（见文件末尾的 subscribePages）。
  const stageW = Math.max(720, (target.clientWidth || 1080) - 24);
  const stageH = Math.max(420, window.innerHeight - CHROME_H);
  const centerX = stageW / 2;
  const centerY = stageH / 2;
  const span = Math.min(stageW, stageH);
  const tagRadius = span * 0.21;
  const taskRadius = span * 0.34;

  const tasks = activeTasks().filter(passesFilter);

  const byTag = new Map<string, Task[]>();
  for (const tag of TAG_NAMES) byTag.set(tag, []);
  for (const task of tasks) {
    const tag = primaryTag(task);
    if (tag) byTag.get(tag)?.push(task);
  }
  // 没有任务的标签不画：一个空圈会让人以为「这里还没加载出来」
  const liveTags = TAG_NAMES.filter((tag) => (byTag.get(tag)?.length ?? 0) > 0);

  // ── 1. 确定性布局 ─────────────────────────────────────────────────────────
  const nodes: GraphNode[] = [
    { id: "core", kind: "partition", label: activePartition().name },
  ];
  const layout = new Map<string, Point>();
  layout.set("core", { x: centerX, y: centerY });

  liveTags.forEach((tag, index) => {
    const angle = (index / liveTags.length) * Math.PI * 2 - Math.PI / 2;
    nodes.push({ id: tag, kind: "tag", label: tag });
    layout.set(tag, {
      x: centerX + Math.cos(angle) * tagRadius,
      y: centerY + Math.sin(angle) * tagRadius,
    });

    const group = byTag.get(tag) ?? [];
    group.forEach((task, order) => {
      const taskAngle = angle + (order - (group.length - 1) / 2) * TASK_SPREAD;
      nodes.push({ id: task.id, kind: "task", label: task.title, task });
      layout.set(task.id, {
        x: centerX + Math.cos(taskAngle) * taskRadius,
        y: centerY + Math.sin(taskAngle) * taskRadius,
      });
    });
  });

  // 拖动只改这一份；复位时从 layout 还原
  const position = new Map(layout);

  // ── 2. 连线 ───────────────────────────────────────────────────────────────
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("class", "edges");
  svg.setAttribute("viewBox", `0 0 ${stageW} ${stageH}`);

  const edges: Edge[] = [];
  const link = (a: string, b: string): void => {
    const line = document.createElementNS(SVG_NS, "path");
    svg.append(line);
    edges.push({ a, b, line });
  };

  for (const tag of liveTags) link("core", tag);
  for (const task of tasks) {
    const tag = primaryTag(task);
    if (tag) link(tag, task.id);
  }

  const neighbours = new Map<string, Set<string>>();
  for (const edge of edges) {
    for (const [self, other] of [
      [edge.a, edge.b],
      [edge.b, edge.a],
    ]) {
      const set = neighbours.get(self) ?? new Set<string>();
      set.add(other);
      neighbours.set(self, set);
    }
  }

  /**
   * 连线走弧线而不是直线。二十来个任务连十几条线时，直线会在中间那段互相重叠，
   * 根本分不清哪条通向哪个任务；拉出一点弧度，每条线各自走一条能认的路径。
   * 弧的方向由法向量（dx/dy 交换取反）决定，凸起量随线长按比例、上限 52px。
   */
  const bowLine = (from: Point, to: Point): string => {
    const midX = (from.x + to.x) / 2;
    const midY = (from.y + to.y) / 2;
    const dx = to.x - from.x;
    const dy = to.y - from.y;
    const len = Math.hypot(dx, dy) || 1;
    const bow = Math.min(len * 0.18, 52);
    return `M${from.x} ${from.y} Q${midX - (dy / len) * bow} ${midY + (dx / len) * bow} ${to.x} ${to.y}`;
  };

  const paintEdges = (): void => {
    for (const edge of edges) {
      const from = position.get(edge.a);
      const to = position.get(edge.b);
      if (!from || !to) continue;
      edge.line.setAttribute("d", bowLine(from, to));
    }
  };

  // ── 3. 画布与节点 ─────────────────────────────────────────────────────────
  let zoom = 1;

  const canvas = el("div", { class: "gcanvas" }, [svg]);
  // 尺寸由上面量出来的值写进内联样式：CSS 里那份 900×520 只是没有 JS 时的兜底
  canvas.style.width = `${stageW}px`;
  canvas.style.height = `${stageH}px`;
  canvas.style.marginLeft = `${-stageW / 2}px`;
  canvas.style.marginTop = `${-stageH / 2}px`;

  const elements = new Map<string, HTMLElement>();

  const highlight = (focusId: string | null): void => {
    svg.classList.toggle("dimmed", focusId !== null);
    for (const edge of edges) {
      edge.line.classList.toggle("hi", focusId !== null && (edge.a === focusId || edge.b === focusId));
    }
    for (const [id, element] of elements) {
      const touched =
        focusId === null || id === focusId || (neighbours.get(focusId)?.has(id) ?? false);
      element.classList.toggle("ghost", !touched);
    }
  };

  const bindDrag = (element: HTMLElement, id: string): void => {
    element.addEventListener("mousedown", (event) => {
      if (event.button !== 0) return;
      event.preventDefault();

      const base = { ...(position.get(id) ?? { x: centerX, y: centerY }) };
      const originX = event.clientX;
      const originY = event.clientY;
      element.classList.add("dragging");

      const onMove = (moveEvent: MouseEvent): void => {
        // 缩放后 1px 指针位移对应 1/zoom 的画布位移
        const next = {
          x: base.x + (moveEvent.clientX - originX) / zoom,
          y: base.y + (moveEvent.clientY - originY) / zoom,
        };
        position.set(id, next);
        element.style.left = `${next.x}px`;
        element.style.top = `${next.y}px`;
        paintEdges();
      };

      const onUp = (): void => {
        element.classList.remove("dragging");
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
      };

      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
    });
  };

  for (const node of nodes) {
    const point = position.get(node.id);
    if (!point) continue;

    const classes = ["node", node.kind];
    if (node.kind === "task") classes.push(node.task?.status ?? "todo");

    const element = el("div", { class: classes.join(" "), "data-id": node.id });
    element.style.left = `${point.x}px`;
    element.style.top = `${point.y}px`;
    // 入场按「离中心多远」错峰：一圈铺开时注意力自然从中心的分区往外的任务上走，
    // 比整版一起闪现更容易看清结构
    const reach = Math.hypot(point.x - centerX, point.y - centerY);
    element.classList.add("enter");
    element.style.animationDelay = `${Math.min(reach / 1200, 0.34).toFixed(3)}s`;

    if (node.kind === "task" && node.task) {
      element.style.background = statusVar(node.task.status);
      // 只有紧急与重要才常驻名签：27 个节点全挂上标签就成了一张文字地毯
      if (node.task.urgency <= 1) element.append(el("span", { class: "nl", text: node.label }));
      element.title = `${node.label} · 双击直达`;
    } else {
      element.textContent = node.label;
      element.title = node.label;
    }

    bindDrag(element, node.id);
    element.addEventListener("mouseenter", () => highlight(node.id));
    element.addEventListener("mouseleave", () => highlight(null));
    element.addEventListener("click", (event) => {
      event.stopPropagation();
      select(node);
    });
    if (node.kind === "task" && node.task) {
      const task = node.task;
      element.addEventListener("dblclick", () => jumpToTask(task.id));
    }

    elements.set(node.id, element);
    canvas.append(element);
  }

  // ── 4. 浮层 ───────────────────────────────────────────────────────────────
  const detail = el("div", { class: "gdetail" });
  const stats = el("div", { class: "gstats" });

  function select(node: GraphNode): void {
    for (const [id, element] of elements) {
      element.classList.toggle("selected", id === node.id);
    }
    showDetail(node);
  }

  function showDetail(node: GraphNode): void {
    detail.replaceChildren(el("div", { class: "dn", text: node.label }));

    if (node.kind === "partition") {
      detail.append(
        el("div", { class: "ds", text: `${tasks.length} 个任务 · ${liveTags.length} 个标签` }),
        el("div", { class: "meta" }, [el("span", { class: "tag", text: "根节点" })]),
      );
      return;
    }

    if (node.kind === "tag") {
      const group = byTag.get(node.id) ?? [];
      const wrap = el("div", { class: "meta" });
      for (const task of group) {
        const chip = el("span", { class: "tag", text: task.title });
        chip.style.cursor = "pointer";
        chip.title = "点击打开维护抽屉";
        chip.addEventListener("click", () => jumpToTask(task.id));
        wrap.append(chip);
      }
      detail.append(el("div", { class: "ds", text: `${group.length} 个任务` }), wrap);
      return;
    }

    const task = node.task as Task;
    detail.append(
      el("div", { class: "ds", text: `${STATUS_LABEL[task.status]} · 进度 ${task.progress}%` }),
      el("div", {
        class: "ds mono",
        text: `${monthDayText(dayNumber(task.start))} → ${monthDayText(dayNumber(task.end))}`,
      }),
      el("div", { class: "meta" }, task.tags.map((tag) => el("span", { class: "tag", text: tag }))),
    );

    const open = el("button", { class: "btn primary", text: "打开维护抽屉" });
    open.style.marginTop = "10px";
    open.addEventListener("click", () => jumpToTask(task.id));
    detail.append(open);
  }

  detail.append(
    el("div", { class: "dn", text: "选择一个节点" }),
    el("div", { class: "ds", text: "悬停高亮相邻关系 · 双击任务直达维护抽屉" }),
  );

  // ── 5. 工具行与缩放 ───────────────────────────────────────────────────────
  const applyZoom = (): void => {
    canvas.style.transform = `scale(${zoom})`;
  };

  const zoomButton = (icon: string, title: string, onClick: () => void): HTMLElement => {
    const button = el("button", { type: "button", title, html: icon });
    button.addEventListener("click", onClick);
    return button;
  };

  const toolbar = el("div", { class: "gbar" }, [
    el("div", { class: "glegend" }, [
      el("span", { class: "it" }, [legendDot("var(--accent)"), "分区"]),
      el("span", { class: "it" }, [
        legendDot("transparent", "1.5px solid var(--accent)"),
        "标签",
      ]),
      el("span", { class: "it" }, [legendDot("var(--doing)"), "任务（色 = 状态）"]),
    ]),
    el("span", { class: "grow" }),
    el("div", { class: "gfilters" }, FILTERS.map((value) => {
      const chip = el("button", {
        class: `chip ${filter === value ? "on" : ""}`,
        type: "button",
        text: value,
      });
      chip.addEventListener("click", () => {
        if (filter === value) return;
        filter = value;
        remount();
      });
      return chip;
    })),
    el("span", { class: "dim mono", text: `节点 ${nodes.length} · 关联 ${edges.length}` }),
  ]);

  const doneCount = tasks.filter((task) => task.status === "done").length;
  stats.append(
    el("div", { text: `节点 ${nodes.length}` }),
    el("div", { text: `关联 ${edges.length}` }),
    el("div", {}, ["已完成 ", el("b", { text: String(doneCount) })]),
  );

  const stage = el("div", { class: "gwrap" }, [
    canvas,
    // 整张图都按分区铺开的，所以分区标注只写一次，放在右上角；
    // 给每个节点都挂一个「属于哪个分区」的标签，在只有一个分区的时候纯属噪音
    el("div", { class: "gpart" }, [
      el("span", { text: "当前分区" }),
      el("b", { text: activePartition().name }),
    ]),
    stats,
    detail,
    el("div", { class: "gzoom" }, [
      zoomButton(ICON.plus, "放大", () => {
        zoom = Math.min(1.8, zoom + 0.15);
        applyZoom();
      }),
      zoomButton(ICON.minus, "缩小", () => {
        zoom = Math.max(0.6, zoom - 0.15);
        applyZoom();
      }),
      zoomButton(ICON.reset, "复位布局", () => {
        zoom = 1;
        applyZoom();
        for (const [id, point] of layout) {
          position.set(id, { ...point });
          const element = elements.get(id);
          if (!element) continue;
          element.style.left = `${point.x}px`;
          element.style.top = `${point.y}px`;
        }
        paintEdges();
        highlight(null);
        toast("布局已复位");
      }),
    ]),
  ]);

  paintEdges();

  host.append(toolbar, stage);
}

function remount(): void {
  if (!host) return;
  host.replaceChildren();
  mount(host);
}

// 抽屉里改了状态或进度，节点颜色和统计要跟着变
onDataChange(remount);

// 页面隐藏时量不到宽度（display:none 下 clientWidth 是 0），切回前台重新量一次；
// 顺带让入场动画重播 —— 布局确实变了，闪一下反而是对的
subscribePages((id) => {
  if (id === "graph") remount();
});

// 窗口宽窄变了要重排：舞台尺寸是按视口算的，不重算就会留一圈空点阵
let resizeTimer: number | undefined;
window.addEventListener("resize", () => {
  window.clearTimeout(resizeTimer);
  resizeTimer = window.setTimeout(remount, 160);
});
