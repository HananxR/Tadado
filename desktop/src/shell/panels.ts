// ─────────────────────────────────────────────────────────────────────────────
// 右侧抽屉的互斥。
//
// 设置抽屉和任务抽屉从同一侧滑出、占同一块地方。各管各的显隐就会出现两块同时
// 开着：后开的那块只露出一条边，两个 Esc 也不知道在关谁。这里只维护一条不变量
// ——同一时刻最多一个右侧抽屉是开的。
//
// 放在 shell 层是有意的：shell 不该认识任务域，所以这里只认一个 id 和一句
// 「怎么关掉我」，两侧各自注册。
// ─────────────────────────────────────────────────────────────────────────────

export type PanelId = "settings" | "task";

const closers = new Map<PanelId, () => void>();
const openers = new Map<PanelId, () => void>();
let open: PanelId | null = null;

/** 注册「怎么关掉我」。同一个 id 重复注册只保留最后一次。 */
export function registerPanel(id: PanelId, close: () => void): void {
  closers.set(id, close);
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
