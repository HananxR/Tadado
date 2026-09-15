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

import { DEMO_PARTITION, TAG_NAMES, activeTasks } from "../data/mock";
import { onDataChange } from "../data/store";
import type { Task } from "../data/types";
import { el } from "../shell/dom";
import { toast } from "../shell/toast";
import { jumpToTask } from "./focus";
import { STATUS_LABEL, dayNumber, monthDayText, statusVar } from "./shared";

// 画布比典型可视区略矮（520 而不是 560）：窗口只有 700px 高时，
// 560 的舞台会让最外圈的节点被 .gwrap 的 overflow:hidden 切掉。
const STAGE_W = 900;
const STAGE_H = 520;
const CENTER_X = STAGE_W / 2;
const CENTER_Y = STAGE_H / 2;
const TAG_RADIUS = 148;
const TASK_RADIUS = 210;
/** 组内任务的角间距。0.125 是「7 个任务不出组」的上界附近。 */
const TASK_SPREAD = 0.125;

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
  line: SVGLineElement;
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
  const nodes: GraphNode[] = [{ id: "core", kind: "partition", label: DEMO_PARTITION }];
  const layout = new Map<string, Point>();
  layout.set("core", { x: CENTER_X, y: CENTER_Y });

  liveTags.forEach((tag, index) => {
    const angle = (index / liveTags.length) * Math.PI * 2 - Math.PI / 2;
    nodes.push({ id: tag, kind: "tag", label: tag });
    layout.set(tag, {
      x: CENTER_X + Math.cos(angle) * TAG_RADIUS,
      y: CENTER_Y + Math.sin(angle) * TAG_RADIUS,
    });

    const group = byTag.get(tag) ?? [];
    group.forEach((task, order) => {
      const taskAngle = angle + (order - (group.length - 1) / 2) * TASK_SPREAD;
      nodes.push({ id: task.id, kind: "task", label: task.title, task });
      layout.set(task.id, {
        x: CENTER_X + Math.cos(taskAngle) * TASK_RADIUS,
        y: CENTER_Y + Math.sin(taskAngle) * TASK_RADIUS,
      });
    });
  });

  // 拖动只改这一份；复位时从 layout 还原
  const position = new Map(layout);

  // ── 2. 连线 ───────────────────────────────────────────────────────────────
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("class", "edges");
  svg.setAttribute("viewBox", `0 0 ${STAGE_W} ${STAGE_H}`);

  const edges: Edge[] = [];
  const link = (a: string, b: string): void => {
    const line = document.createElementNS(SVG_NS, "line");
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

  const paintEdges = (): void => {
    for (const edge of edges) {
      const from = position.get(edge.a);
      const to = position.get(edge.b);
      if (!from || !to) continue;
      edge.line.setAttribute("x1", String(from.x));
      edge.line.setAttribute("y1", String(from.y));
      edge.line.setAttribute("x2", String(to.x));
      edge.line.setAttribute("y2", String(to.y));
    }
  };

  // ── 3. 画布与节点 ─────────────────────────────────────────────────────────
  let zoom = 1;

  const canvas = el("div", { class: "gcanvas" }, [svg]);
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

      const base = { ...(position.get(id) ?? { x: CENTER_X, y: CENTER_Y }) };
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
