// ─────────────────────────────────────────────────────────────────────────────
// 任务图谱页：分区 / 标签 / 任务的关系网络。
//
// 布局是**确定性**的，不是力导向。原型把这个视图写成「力导向布局画布」，
// 但真跑起来的力导向每次刷新都给出不同形状 —— 同一个任务这次在左上、
// 下次在右下，看久了什么都记不住，而且拖动一个节点会让整张图跟着漂。
// 这里改成：分区在圆心，标签铺一圈，任务挂在各自主标签外侧的弧上。
// 位置固定 ⇒ 可以凭肌肉记忆找到节点；拖动只影响被拖的那一个。
//
// 多标签任务只画**一个**节点（否则「双击直达任务」会出现两个一模一样的入口），
// 但它会连到自己拥有的**每一条**标签上 —— 关系看得见，入口只有一个。
//
// 标签集合按数据现算（见 data/tags.ts）：预置的在前、新标签接在后面。以前这里
// 用的是写死的六个预置名，于是「新建的标签」在图上不存在，连挂在它上面的任务也
// 一起消失 —— 用户看到的就是「图谱里没有体现」。
//
// 数据变更时整页重建：节点集合、位置、连线、统计都得跟着换，增量改的代码比
// 重建还多。代价是缩放和拖动会被重置 —— 数据都变了，布局本来就该重排。
//
// ── 版式（2026-11-10 重构）────────────────────────────────────────────────
// 以前「图谱」和「这个节点是什么」挤在同一块画布里：详情卡浮在右上、统计卡浮在
// 左上、分区角标也浮在右上 —— 三块浮层压在节点上，用户说的「视觉重叠」就是它们。
// 现在改成**左图右明细**（8:2）：左栏整块留给图谱，右栏是常驻的任务明细面板，
// 两者物理隔离，浮层全部撤掉（只剩缩放控件留在画布内）。
//
// 工具行也从「图例 + 四枚散落胶囊 + 一串计数」重排为「筛选（贴左顶格） + 留白 +
// 右端读数」：
//   · 图例撤了 ——「⬤分区 ◯标签 ●●●任务」在工具行里占掉约 140px 横宽，太占地方。
//     节点类型改由**自身记法**识别：标签节点带 `#`、任务节点悬停时浮出带 Px 的
//     名签，分区节点只留名字。
//   · 分区名不再显性标识 —— rail 上有分区选择器，这一页再标一遍是重复标识
//     （2026-11-10 用户提的）。
//   · 「节点 N · 关联 M」恢复成工具行右端的一行弱化小字（2026-11-10 用户说图上
//     少了它）。它不做成独立控件：节点数是「1 分区 + N 标签 + M 任务」，能推导；
//     关联数是边数、在图上没法用眼睛核对 —— 可它到底是「这张图有多大」的一种
//     说法，作为旁注留着比做成要读数的东西合适。
//   · 真正有用的计数（当前对象的任务数、进行中 / 已完成 / 逾期构成）在右栏头部
//     —— 数字和它描述的对象待在同一个地方。
//
// 工具行是**通栏**的（挂在 .page-body 这一层，不在左栏里）：这样左栏只剩画布、
// 右栏是明细面板，两者的上边缘齐平 —— 早先是右栏从工具行那一层起，比图谱区
// 高出一截。
// ─────────────────────────────────────────────────────────────────────────────

import { partitionTasks } from "../data/mock";
import { UNTAGGED, tagsInUse } from "../data/tags";
import { activePartition } from "../data/partitions";
import { onDataChange } from "../data/store";
import type { Task } from "../data/types";
import { el } from "../shell/dom";
import { subscribePages } from "../shell/router";
import { toast } from "../shell/toast";
import { jumpToTask } from "./focus";
import { STATUS_LABEL, matchesStatus, pad2, statusVar, urgencyBadge } from "./shared";

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

/** 空态那枚线性图标：一个被框住的节点 + 一条引线（表示「还没选中任何东西」）。 */
const ICON_EMPTY =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="8" cy="12" r="3.2"/><path d="M11.2 12h8.6"/><circle cx="19.8" cy="12" r="1.6"/></svg>';

/** 面板头部的类型标。分区 / 标签 / 任务 —— 与图上三类节点一一对应。
 *  分区那一档写「全部」而不是「分区」：分区名 rail 上有，这一页不必再标。 */
const KIND_LABEL: Record<Exclude<PanelView["kind"], null>, string> = {
  partition: "全部",
  tag: "标签",
  task: "任务",
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

// 「紧急与重要」改成「高优先级」：全应用讨论的都是优先级 P0–P3（编辑面板、
// 列表徽标、总览的优先级分布），这里单独用一组形容词会让人以为不是同一个字段
const FILTERS = ["全部", "高优先级", "进行中", "已完成"] as const;
type Filter = (typeof FILTERS)[number];

let filter: Filter = "全部";

function passesFilter(task: Task): boolean {
  if (filter === "高优先级") return task.urgency <= 1;
  // 「进行中」「已完成」与总览那几张卡、任务页与管理页那条筛选是**同一个谓词**
  // （shared.ts 的 `matchesStatus`）—— 同一个词在四个页面四种结果是这一页的老毛病。
  // ⚠️ 「已完成」是 2026-09-21 补的（用户报的「图谱的快捷选项里没有已完成」）：
  // 取数改成含归档之后（见 render 里那段），已完成的任务**在图上本来就有**，
  // 却没有一枚 chip 能筛它们 —— 那枚 chip 缺的是入口，不是数据
  if (filter === "进行中") return matchesStatus(task, "doing");
  if (filter === "已完成") return matchesStatus(task, "done");
  return true;
}

/**
 * 任务在图上连出去的标签节点：它拥有的每一条标签，顺序跟着环走。
 *
 * 没有任何一条标签能对上时归「未分类」—— 新建已经不允许无标签，但历史数据里
 * 可能还有；以前这种情况任务直接不画，等于数据在图上凭空少了。
 */
function linkedTags(task: Task, liveTags: string[]): string[] {
  const own = liveTags.filter((tag) => task.tags.includes(tag));
  return own.length > 0 ? own : [UNTAGGED];
}

// ─── 右栏面板的数据模型 ──────────────────────────────────────────────────────

/**
 * 右栏面板要显示什么。
 *
 * 面板的渲染函数（`renderPanel`）只认这个结构，**不关心数据从哪来** ——
 * 分区视图、标签视图、任务视图都先折成它再交给渲染。这条界线是「两阶段拆分
 * 不返工」的关键：面板内部长什么样，先定下来；之后换的只是喂进来的数据。
 */
interface PanelView {
  /** 选中对象的类型；null = 未选中（空态）。 */
  kind: "partition" | "tag" | "task" | null;
  /** 头部主标题：分区名 / 标签名 / 任务名。 */
  title: string;
  /** 头部副标题：如「8 个任务」。 */
  subtitle: string;
  /** 头部状态构成：数字前带同色圆点，颜色取 `statusVar()`。 */
  stats: { label: string; value: number; color: string }[];
  /** 列表条目。 */
  tasks: Task[];
  /**
   * 可选：头部下方的详情块。
   *
   * 只有「任务」这一档用得到（起止 / 截止 / 标签 / 打开维护抽屉）；分区与标签两档
   * 不给这个字段，面板就只画头部与列表。
   *
   * 为什么不让任务视图也「退化成一行」：那行就是这条任务自己，而面板存在的意义
   * 是**看清它** —— 状态、进度、什么时候到期、挂在哪些标签下。这几件事挤进副标题
   * 一行里没人读得下去。
   */
  detail?: HTMLElement;
}

/**
 * 状态构成的三档计数。
 *
 * 口径与别处同源：`matchesStatus` 是四个页面共用的那个谓词（总览卡 / 任务页
 * chip / 管理页筛选 / 图谱过滤），这里也走它 —— 同一件事只写一处。
 *
 * ⚠️ 「待办」这一档在 2026-09-21 已经删掉（见 data/types.ts），老数据在读入口
 * 归一到「进行中」，所以界面上只剩三档。
 */
function statusBreakdown(tasks: Task[]): PanelView["stats"] {
  return [
    { label: STATUS_LABEL.doing, value: tasks.filter((task) => matchesStatus(task, "doing")).length, color: statusVar("doing") },
    { label: STATUS_LABEL.done, value: tasks.filter((task) => matchesStatus(task, "done")).length, color: statusVar("done") },
    { label: STATUS_LABEL.overdue, value: tasks.filter((task) => matchesStatus(task, "overdue")).length, color: statusVar("overdue") },
  ];
}

/**
 * 列表的排序：优先级在前，同级按截止日。
 *
 * 与任务页的默认排序（`pages/tasks.ts` 的 `urgency`）同一口径 —— 两处列表排
 * 出来的先后一致，用户从一处看到「P0 在最前」，到另一处也该是这样。
 */
function byPriorityThenDue(a: Task, b: Task): number {
  if (a.urgency !== b.urgency) return a.urgency - b.urgency;
  return a.end[0] * 100 + a.end[1] - (b.end[0] * 100 + b.end[1]);
}

// ─── 挂载 ────────────────────────────────────────────────────────────────────

let host: HTMLElement | null = null;

export function mount(target: HTMLElement): void {
  host = target;

  // 舞台要先落地再量：可用高度是 CSS 排出来的（#page-graph 吃掉主区剩余高度，
  // .gwrap 是 flex:1），没进 DOM 之前量到的只有 0。以前拿 window.innerHeight
  // 减一个写死的 chrome 常量去估 —— 估错的代价是画布比容器高，而 .gwrap 是
  // overflow:hidden，底下半张图就这么没了。
  // 页面隐藏时量不到（display:none 下是 0），兜一组够用的尺寸，切回前台会重画
  // 一次（见文件末尾的 subscribePages）。
  //
  // 工具行必须比舞台先落地：它在舞台上方占一段高度（约 34px + 间距），
  // 先量后加工具行的话，量到的高度里有它的份，画布就会比容器高一截，底下照旧被切。
  const filters = el("div", { class: "seg hug" }, FILTERS.map((value) => {
    const button = el("button", {
      class: filter === value ? "on" : "",
      type: "button",
      text: value,
    });
    button.addEventListener("click", () => {
      if (filter === value) return;
      filter = value;
      remount();
    });
    return button;
  }));

  // 工具行右端的读数：这一批任务的条数 + 图的规模（节点 / 关联）。
  //
  // 分区名不在这儿写了 —— rail 上有分区选择器，这一页再标一遍是重复标识
  // （2026-11-10 用户提的：「最左侧分区已经有了，图谱界面不需要再显性标识」）。
  //
  // 「节点 N · 关联 M」回来了，但只做一行弱化小字：关联数在图上没法用眼睛核对
  // （它是边数），可它是**规模**的一种说法 —— 想知道这张图有多大时，那行字够了。
  const taskCount = el("span", { class: "num mono" });
  const scale = el("span", { class: "scale mono" });
  // 中间那个「·」：两组读数挨在一起时，「100 任务107 节点」粘成一句读不通的话
  const meta = el("div", { class: "gmeta" }, [
    taskCount,
    el("span", { class: "sep", text: "·" }),
    scale,
  ]);

  const toolbar = el("div", { class: "gbar" }, [filters, el("span", { class: "grow" }), meta]);

  const stage = el("div", { class: "gwrap" });

  // 右栏面板：卡片式，头部常驻，列表区自己滚。
  //
  // 它是**常驻的一栏**，不是浮层 —— 浮层天生压在节点上，这正是要撤掉的东西。
  const panelHead = el("div", { class: "gpanel-h" });
  const panelBody = el("div", { class: "gpanel-body" });
  const panel = el("div", { class: "gpanel" }, [panelHead, panelBody]);
  const side = el("div", { class: "gside" }, [panel]);

  // 工具行提到 .page-body 这一层（通栏），不放左栏里面 ——
  // 这样左栏只剩 .gwrap、右栏是 .gpanel，两者顶端就齐了（2026-11-10 用户提的：
  // 右侧表格上边缘要和图谱显示区域的上边缘一致）。放在左栏里的话，右栏从工具
  // 行那一层起，比图谱区高一截。
  const main = el("div", { class: "gmain" }, [stage]);
  target.append(toolbar, el("div", { class: "gpage" }, [main, side]));

  // 量画布：宽度下限必须**跟着左栏的实际宽度走**。
  //
  // 以前写死 720 是因为图谱独占整块主区；现在左栏是 8 分，右栏还要占掉 264px，
  // 窗口最小 1050 时左栏只剩约 650px —— 720 的下限会让画布比容器还宽，
  // .gwrap 的 overflow:hidden 就把边缘那圈节点裁掉了（e2e 那条「节点都在框内」
  // 会当场红）。所以下限改成自适应值，只留一个「别小到没法看」的兜底。
  const stageW = Math.max(320, (stage.clientWidth || 1080) - 24);
  const stageH = Math.max(260, (stage.clientHeight || 420) - 14);
  const centerX = stageW / 2;
  const centerY = stageH / 2;

  // 半径横竖分开取 —— 铺的是一圈椭圆，不是正圆。舞台是横长的，只按短边算半径的
  // 话，节点会挤在中间那三分之一宽度里，两侧全是空的点阵底纹：图「看着小」就是
  // 这么来的。x 方向还得给紧急任务的常驻名签留 90px —— 它挂在节点右侧，会往外
  // 伸出去一截。
  const tagRadiusX = stageW * 0.19;
  const tagRadiusY = Math.min(stageH * 0.25, stageH / 2 - 30);
  const taskRadiusX = Math.min(stageW * 0.35, stageW / 2 - 90);
  const taskRadiusY = Math.min(stageH * 0.42, stageH / 2 - 24);

  // ⚠️ **含归档**（2026-09-21 用户报的「图谱只显示进行中、已完成的都不见了」）：
  // 默认「完成后归档＝立即」（§4.10）之下，做完的任务**当场**就离开 `activeTasks()` ——
  // 于是图谱上永远只剩「进行中」，那张图看起来像坏了。归档只该影响**任务页**（那页的
  // 定位是「手上的活儿」，`activeTasks` 也是为它写的）；其余模块都是**看全貌**的：
  // 活动分析与管理页本来就含归档，图谱跟上（总览那张「已归档」卡也是这个意思）。
  const tasks = partitionTasks().filter(passesFilter);

  taskCount.textContent = `${tasks.length} 任务`;

  // 标签集合按数据现算：预置的在前，用户在表单里写出来的新标签接在后面
  const liveTags = tagsInUse(tasks);
  // 「未分类」只在真有任务一条标签都对不上时才出现
  const ringTags = tasks.some((task) => linkedTags(task, liveTags).includes(UNTAGGED))
    ? [...liveTags, UNTAGGED]
    : liveTags;

  // 布局锚点：任务挂在它第一个标签的弧上（位置稳定、不重复画节点）。
  // 「一个标签下有哪些任务」分两份：byTag 是锚在这里的（布局用），
  // byTagAll 是拥有这个标签的（详情面板用，多标签任务两条边都算）。
  const byTag = new Map<string, Task[]>();
  const byTagAll = new Map<string, Task[]>();
  for (const tag of ringTags) {
    byTag.set(tag, []);
    byTagAll.set(tag, []);
  }
  for (const task of tasks) {
    const tags = linkedTags(task, liveTags);
    byTag.get(tags[0])?.push(task);
    for (const tag of tags) byTagAll.get(tag)?.push(task);
  }

  // ── 1. 确定性布局 ─────────────────────────────────────────────────────────
  // 分区名和标签名很容易撞（分区「工作」、标签「#工作」）：中心节点在名字下面挂
  // 一枚「分区」小签（见下面画节点那段），标签节点则带 `#`，两边不用读第二眼
  const nodes: GraphNode[] = [
    { id: "core", kind: "partition", label: activePartition().name },
  ];
  const layout = new Map<string, Point>();
  layout.set("core", { x: centerX, y: centerY });

  ringTags.forEach((tag, index) => {
    const angle = (index / ringTags.length) * Math.PI * 2 - Math.PI / 2;
    nodes.push({ id: tag, kind: "tag", label: tag });
    layout.set(tag, {
      x: centerX + Math.cos(angle) * tagRadiusX,
      y: centerY + Math.sin(angle) * tagRadiusY,
    });

    const group = byTag.get(tag) ?? [];
    group.forEach((task, order) => {
      const taskAngle = angle + (order - (group.length - 1) / 2) * TASK_SPREAD;
      nodes.push({ id: task.id, kind: "task", label: task.title, task });
      layout.set(task.id, {
        x: centerX + Math.cos(taskAngle) * taskRadiusX,
        y: centerY + Math.sin(taskAngle) * taskRadiusY,
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

  for (const tag of ringTags) link("core", tag);
  // 任务连到它**拥有**的每一条标签，而不是只连锚点那一条：多标签关系才在图上
  // 看得出来（原来 #学习 这类第二标签在图上完全不可见）
  for (const task of tasks) {
    for (const tag of linkedTags(task, liveTags)) link(tag, task.id);
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
    if (node.kind === "task") classes.push(node.task?.status ?? "doing");
    // 「未分类」不是一个标签，给个虚线框：形状上先分开，不用去读文字
    if (node.kind === "tag" && node.label === UNTAGGED) classes.push("untagged");

    const element = el("div", { class: classes.join(" "), "data-id": node.id });
    element.style.left = `${point.x}px`;
    element.style.top = `${point.y}px`;
    // 入场按「离中心多远」错峰：一圈铺开时注意力自然从中心的分区往外的任务上走，
    // 比整版一起闪现更容易看清结构
    const reach = Math.hypot(point.x - centerX, point.y - centerY);
    element.classList.add("enter");
    element.style.animationDelay = `${Math.min(reach / 1200, 0.34).toFixed(3)}s`;

    if (node.kind === "task" && node.task) {
      const task = node.task;
      element.style.background = statusVar(task.status);
      // 名签：`Px + 标题`。名字与优先级一起看，才是「这条任务是什么、又多急」。
      //
      // 默认隐藏、悬停/选中才浮出 —— 全挂上常驻的话，几十个节点就是一张文字
      // 地毯（演示数据里一半是 P0/P1，常驻等于满屏小字）。最急的那一档（P0）
      // 另用一圈红晕标出（`.hot`），不占文字位置。
      element.append(el("span", { class: "nl" }, [urgencyBadge(task.urgency), node.label]));
      if (task.urgency === 0) element.classList.add("hot");
      element.title = `${node.label} · 双击直达任务`;
    } else if (node.kind === "partition") {
      // 名字下面原来挂一枚「分区」小签（分区名与标签名可能一字不差：工作 / #工作）。
      // 现在撤了 —— rail 上有分区选择器，这一页不必再显性标识「这是分区」
      // （2026-11-10 用户提的：「最左侧分区已经有了」）。节点只留名字。
      element.append(el("span", { class: "pn", text: node.label }));
      element.title = `${node.label} · 分区（数据的隔离边界）`;
    } else {
      element.textContent = node.label;
      element.title = node.label === UNTAGGED ? "没有标签的任务" : node.label;
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

  // ── 4. 右栏面板 ───────────────────────────────────────────────────────────

  /**
   * 面板的一行任务。
   *
   * 行首那枚圆点是**状态色**（不是优先级）—— 优先级在行尾那枚 `P0`–`P3` 徽标上。
   * 一左一右两个通道分开摆：颜色说状态，文字说优先级，不用去猜（与任务页
   * 行首「进度饼」+ 行尾「Px 徽标」是同一条规矩，见 pages/shared.ts 的说明）。
   */
  const taskRow = (task: Task): HTMLElement => {
    const dot = el("span", { class: "gdot" });
    dot.style.background = statusVar(task.status);

    const title = el("span", { class: "t", text: task.title, title: task.title });

    const second = el("div", { class: "gt2" });
    for (const tag of task.tags) second.append(el("span", { class: "tag", text: tag }));
    second.append(
      el("span", {
        class: "due mono",
        text: task.due ? `⏰ ${task.due}` : "无截止",
      }),
    );

    const row = el("div", { class: "gtask" }, [
      dot,
      el("div", { class: "gcol" }, [
        el("div", { class: "gt1" }, [title, urgencyBadge(task.urgency)]),
        second,
      ]),
    ]);
    // 点一行 = 打开这条任务的维护抽屉（与图上双击同一件事）
    row.title = "打开维护抽屉";
    row.addEventListener("click", () => jumpToTask(task.id));
    return row;
  };

  /**
   * 面板的空态：什么都没选。
   *
   * 抽成函数是因为它有两个消费者 —— 首次装配，以及「点画布空白把面板收空」
   * （第二阶段接上）。两处各抄一份，改文案时必然只改一处。
   */
  const panelEmpty = (): HTMLElement[] => [
    el("div", { class: "gpanel-empty" }, [
      el("div", { class: "ic", html: ICON_EMPTY }),
      el("div", { class: "t", text: "未选择节点" }),
      el("div", { class: "d", text: "点击图上的标签或任务，这里显示它的任务明细" }),
    ]),
  ];

  /**
   * 填右栏。
   *
   * 面板的渲染只认 `PanelView` —— 它不关心数据是分区来的、标签来的还是任务来的。
   * 头部常驻、列表区自己滚；换一组内容时滚动位置归零（否则会停在上一次的位置，
   * 看着像少了内容）。
   */
  const renderPanel = (view: PanelView): void => {
    panelHead.replaceChildren();
    panelBody.replaceChildren();

    if (view.kind === null) {
      panelBody.append(...panelEmpty());
      return;
    }

    panelHead.append(
      el("div", { class: "gpanel-kind", text: KIND_LABEL[view.kind] }),
      el("div", { class: "gpanel-title", text: view.title }),
      el("div", { class: "gpanel-sub", text: view.subtitle }),
    );

    // 状态构成：数字前带一枚同色圆点 —— 这行也是「颜色 = 状态」的对照表，
    // 与列表行首那枚圆点同源（图上不再另设图例解释颜色）。
    const stats = el("div", { class: "gpanel-stats" });
    for (const item of view.stats) {
      const dot = el("span", { class: "d" });
      dot.style.background = item.color;
      stats.append(
        el("div", { class: "st" }, [dot, el("b", { text: String(item.value) }), item.label]),
      );
    }
    panelHead.append(stats);

    // 任务视图才有的详情块（起止 / 截止 / 标签 / 打开抽屉）
    if (view.detail) panelHead.append(view.detail);

    if (view.tasks.length === 0) {
      panelBody.append(
        el("div", { class: "gpanel-empty" }, [
          el("div", { class: "t", text: "这一组没有任务" }),
          el("div", { class: "d", text: "换个标签或节点看看" }),
        ]),
      );
      return;
    }

    // 一次性构建再插入：逐条 append 会触发多次重排
    const fragment = document.createDocumentFragment();
    for (const task of view.tasks) fragment.append(taskRow(task));
    panelBody.append(fragment);
    panelBody.scrollTop = 0;
  };

  /**
   * 任务视图的详情块：这条任务自己的事。
   *
   * 起止用 `MonthDay`（月、日两个数）自己拼 —— `monthDayText` 接受的是「天数」，
   * 那是另一套基准（见 data/time.ts），用错会显示成完全不相干的日子。
   */
  const taskDetail = (task: Task): HTMLElement => {
    const row = (key: string, value: HTMLElement | string): HTMLElement => {
      const v = typeof value === "string" ? el("span", { class: "v", text: value }) : value;
      return el("div", { class: "dr" }, [el("span", { class: "k", text: key }), v]);
    };

    const tags = el("span", { class: "v vt" });
    for (const tag of task.tags) tags.append(el("span", { class: "tag", text: tag }));

    const open = el("button", { class: "btn sm", type: "button", text: "打开维护抽屉" });
    open.addEventListener("click", (event) => {
      event.stopPropagation();
      jumpToTask(task.id);
    });

    return el("div", { class: "gpanel-detail" }, [
      row("起止", el("span", { class: "v mono", text: `${pad2(task.start[0])}/${pad2(task.start[1])} → ${pad2(task.end[0])}/${pad2(task.end[1])}` })),
      row("截止", task.due ?? "无截止"),
      row("标签", task.tags.length > 0 ? tags : el("span", { class: "v", text: "无标签" })),
      open,
    ]);
  };

  /**
   * 按节点类型构造右栏要显示的内容。
   *
   * 三种节点三种口径：
   *  · **分区** → 这一批任务的全部（分区是数据的隔离边界，「这一区有哪些任务」）；
   *  · **标签** → **拥有**这条标签的全部任务（`byTagAll`，不是只含锚点的 `byTag`）。
   *    多标签任务的锚点只画在第一条标签上，但它的关系是**每一条**标签都该算 ——
   *    只用 `byTag` 的话，「锚在别处、却挂着这条标签」的任务就漏了，而那正是
   *    「点标签看它的任务」最该看到的那批；
   *  · **任务** → 这条任务自己的详情 + 同组任务（同一锚点标签下的其他任务）。
   */
  function viewFor(node: GraphNode): PanelView {
    if (node.kind === "partition") {
      const list = [...tasks].sort(byPriorityThenDue);
      return {
        kind: "partition",
        title: "全部任务",
        subtitle: `共 ${list.length} 个任务`,
        stats: statusBreakdown(list),
        tasks: list,
      };
    }

    if (node.kind === "tag") {
      const list = [...(byTagAll.get(node.id) ?? [])].sort(byPriorityThenDue);
      return {
        kind: "tag",
        title: node.label,
        subtitle: `共 ${list.length} 个任务`,
        stats: statusBreakdown(list),
        tasks: list,
      };
    }

    const task = node.task;
    if (!task) {
      return { kind: null, title: "", subtitle: "", stats: [], tasks: [] };
    }
    // 同组 = 同一个锚点标签下的其他任务（不含它自己）
    const anchor = linkedTags(task, liveTags)[0];
    const group = [...(byTagAll.get(anchor) ?? [])]
      .filter((item) => item.id !== task.id)
      .sort(byPriorityThenDue);
    return {
      kind: "task",
      title: task.title,
      subtitle: `${STATUS_LABEL[task.status]} · 进度 ${Math.round(task.progress)}%`,
      stats: statusBreakdown(group),
      tasks: group,
      detail: taskDetail(task),
    };
  }

  /**
   * 选中一个节点：高亮它，并把右栏换成它那一组。
   */
  function select(node: GraphNode): void {
    for (const [id, element] of elements) {
      element.classList.toggle("selected", id === node.id);
    }
    renderPanel(viewFor(node));
  }

  /**
   * 取消选中：右栏回到空态。
   *
   * 空态不是「没有数据」，是「还没选东西」—— 两者要分得清：没选东西时给一句
   * 引导（点这里），没有任务时也给一句（换个节点看看），混成一句话就会有一半
   * 情况在骗人。
   */
  function clearSelection(): void {
    for (const element of elements.values()) element.classList.remove("selected");
    renderPanel({ kind: null, title: "", subtitle: "", stats: [], tasks: [] });
  }

  /**
   * 点画布空白：把选中清掉。
   *
   * 节点自己的 click 已经 stopPropagation（选中即展示，不能同一次点击里又被清掉），
   * 所以冒泡到这里的就是「空白」。缩放按钮要豁免 —— 点它不该把选中清掉。
   */
  stage.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof Element)) return;
    if (target.closest(".gzoom")) return;
    clearSelection();
  });

  // ── 5. 工具行与缩放 ───────────────────────────────────────────────────────
  const applyZoom = (): void => {
    canvas.style.transform = `scale(${zoom})`;
  };

  const zoomButton = (icon: string, title: string, onClick: () => void): HTMLElement => {
    const button = el("button", { type: "button", title, html: icon });
    button.addEventListener("click", onClick);
    return button;
  };

  // 尺寸量的是这个容器自己，所以这里不能重新建一个 —— 用上面已经落地的那个
  stage.append(
    canvas,
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
  );

  // 默认选中中心那个分区节点（2026-11-10 用户定的方案 A）：进页面右栏就有内容，
  // 不用先点一下才知道这页是干什么的。点画布空白仍然可以清空回空态。
  //
  // `nodes[0]` 就是中心分区节点（它是第一个 push 进 nodes 的）。
  select(nodes[0]);

  // 图的规模读数：节点数（1 分区 + N 标签 + M 任务）与关联数（边数）。
  //
  // 这两个数第一阶段按「冗余」撤掉了 —— 节点数能推导，关联数在图上没法用眼睛
  // 核对。2026-11-10 用户说图上少了这两个读数，于是恢复成工具行右端的一行
  // 弱化小字：不是控件，是一句「这张图有多大」的旁注。
  scale.textContent = `${nodes.length} 节点 · ${edges.length} 关联`;

  paintEdges();
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
