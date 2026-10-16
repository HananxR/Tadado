// ─────────────────────────────────────────────────────────────────────────────
// 右侧抽屉的互斥与「点外部收起」。
//
// 设置抽屉和任务抽屉从同一侧滑出、占同一块地方。各管各的显隐就会出现两块同时
// 开着：后开的那块只露出一条边，两个 Esc 也不知道在关谁。这里只维护一条不变量
// ——同一时刻最多一个右侧抽屉是开的。
//
// 「点在面板之外就收起来」也放在这里（2026-10-16 加），理由同上：两块抽屉的判定
// 一模一样，各写一份迟早分叉（任务抽屉会关、设置抽屉忘了关）。为此 registerPanel
// 多收一个**根节点**——判断「这点在不在面板里」只能靠它。
//
// 放在 shell 层是有意的：shell 不该认识任务域，所以这里只认一个 id、一个根节点、
// 和一句「怎么关掉我」，两侧各自注册。
// ─────────────────────────────────────────────────────────────────────────────

export type PanelId = "settings" | "task";

/**
 * 抽屉滑出动画时长（ms）。
 *
 * 数值与 styles/shell.css 的 `.drawer` 过渡保持一致（0.3s）。仅当 `transitionend`
 * 没来时才用它兜底（`prefers-reduced-motion`、元素被中途移走、以及「上一次过渡还
 * 没结束就被改回原值」这三种情况下，过渡事件都不会到）。多给一点余量，免得兜底
 * 抢在真正的动画前面把面板又推回来。
 */
export const PANEL_LEAVE_MS = 340;

/**
 * 「点这些地方不算点在面板外」。
 *
 * - `.mask`：二次确认 / 提示输入 / 新建任务 / 数据迁入等模态。遮罩铺满全屏且
 *   z-index 120 高于抽屉 70 —— 设置抽屉开着时从里面弹出口令提示框，点提示框里的
 *   输入框本来该由**那一层**处理；不豁免的话会被判成「点在抽屉外」，把设置抽屉
 *   一起关掉（而提示框还开着，看上去像是点了一下关掉两样东西）。
 * - `.lock-screen`：锁屏盖住整个应用、本来就不该响应点击；`body.lock-suppressed`
 *   时「抽屉压在锁屏之上、侧栏仍被盖着」是既有的刻意口径，不能被顺手改掉。
 * - `.ctx-menu`：任务行的右键菜单（fixed）。点里面的「打开维护抽屉」时，若先被
 *   当成「点外部」把当前抽屉关掉，会看到一次多余的滑出再滑入。
 */
const KEEP_SELECTOR = ".mask, .lock-screen, .ctx-menu";

/**
 * 「打开抽屉的那只手」——任务列表的行、侧栏的设置入口。
 *
 * 点它们不算「点外部」，否则「同一条任务再双击一次收起」会当场失效：双击的第一下
 * 先把抽屉关掉，第二下 `isTaskOpen` 已经是 false，于是又打开 —— 闪一下、抽屉还在。
 * 见 tasks.ts 的 dblclick 与 index.html 的 #set-btn。
 *
 * 值必须是它服务的那块面板的 **PanelId**（`data-panel-keep="task"` / `"settings"`）：
 * 只有「当前开的正是它」时才豁免。写成裸属性（等于空串）不豁免 —— 任务行对设置抽屉
 * 来说不是打开手势，设置开着时点一行，那就是真的「点了外面」，该收起来。
 */
const KEEP_ATTR = "data-panel-keep";

/** 这一点是不是「正在开的那块面板的打开手势」。 */
function isOwnTrigger(target: Element, id: PanelId): boolean {
  return target.closest<HTMLElement>(`[${KEEP_ATTR}]`)?.dataset.panelKeep === id;
}

const closers = new Map<PanelId, () => void>();
const roots = new Map<PanelId, () => HTMLElement | null>();
const openers = new Map<PanelId, () => void>();
let open: PanelId | null = null;

/**
 * 注册「怎么关掉我」，以及「我在哪块 DOM 里」。
 *
 * 根节点传的是 **getter** 而不是元素：任务抽屉的 DOM 是懒建的（第一次 openTask
 * 才 build），注册那一刻还不存在。同一个 id 重复注册只保留最后一次。
 */
export function registerPanel(
  id: PanelId,
  close: () => void,
  root?: () => HTMLElement | null,
): void {
  closers.set(id, close);
  if (root) roots.set(id, root);
}

/**
 * 注册「怎么打开我」。
 *
 * 锁屏要在自己身上开一个「设置」入口（忘了口令时的唯一出口），而 lock.ts 不能
 * 反过来 import settings.ts —— settings 依赖 lock，那是个环。这里只认 id，
 * 两边都够用。
 */
export function registerOpen(id: PanelId, open: () => void): void {
  openers.set(id, open);
}

export function openPanel(id: PanelId): void {
  openers.get(id)?.();
}

/** 某个抽屉打开了：先把别的关掉。 */
export function panelOpened(id: PanelId): void {
  if (open && open !== id) closers.get(open)?.();
  open = id;
}

/**
 * 某个抽屉关掉了。
 *
 * 只有它确实是「当前打开的那个」时才清状态：互斥关掉别人之后，那个被关的抽屉
 * 也会走到这里，此时 open 已经换成新的了，不能让它把新状态抹掉。
 */
export function panelClosed(id: PanelId): void {
  if (open === id) open = null;
}

export const openedPanel = (): PanelId | null => open;

/**
 * 点在面板之外 → 收起它。
 *
 * 用 `pointerdown` 而不是 `click`：与 ctx 菜单 / 下拉菜单的既有选择一致（它们也
 * 是按下就响应，等不到松手），而且不会和任务页甘特拖动后的 `swallowAfterDrag`
 * 相互干扰——那个是在 capture 阶段拦 click / dblclick 的。
 *
 * 只认鼠标左键：右键是「要处置这一行」，不该顺手把抽屉关掉。
 *
 * 常驻一个监听，`open === null` 时第一行就返回。没有它就得每次开抽屉挂一次、
 * 关抽屉摘一次，漏摘一处就是内存里多一个闭包。
 */
document.addEventListener("pointerdown", (event) => {
  if (!open || event.button !== 0) return;

  const target = event.target;
  if (!(target instanceof Element)) return;

  // 点在面板里 → 不关。root 取不到时（理论上不该发生）宁可不动：关错了比不关更糟
  const root = roots.get(open)?.();
  if (!root || root.contains(target)) return;

  // 点在模态 / 锁屏 / 打开手势上 → 不关（见上面两处的逐条说明）
  if (target.closest(KEEP_SELECTOR) || isOwnTrigger(target, open)) return;

  closers.get(open)?.();
});
