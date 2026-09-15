// ─────────────────────────────────────────────────────────────────────────────
// 窗口能力封装。
//
// 标题栏和设置面板都要动同一批窗口状态（置顶 / 最大化 / 显隐），状态留在这
// 一层，两边只订阅结果，避免各存一份然后互相打架。
//
// 窗口形态：无边框（decorations:false）+ 自绘标题栏，边缘缩放与 Aero Snap 交给
// Tauri 的 resizable + shadow。DESIGN.md 2.12。
//
// 宿主探测：不在 Tauri 里时（纯 vite 预览）窗口调用降级为本地状态切换 ——
// 这样外壳能在浏览器里直接调样式，不必每次都编译 Rust。@tauri-apps/api 的
// getCurrentWindow() 在非 Tauri 环境会抛，所以必须惰性获取。
// ─────────────────────────────────────────────────────────────────────────────

import { isTauri } from "@tauri-apps/api/core";
import { getCurrentWindow } from "@tauri-apps/api/window";

type TauriWindow = ReturnType<typeof getCurrentWindow>;

type PinListener = (pinned: boolean) => void;
type MaximizeListener = (maximized: boolean) => void;

const pinListeners = new Set<PinListener>();
const maximizeListeners = new Set<MaximizeListener>();

let cached: TauriWindow | null = null;
let pinned = false;
let maximized = false;

/** 宿主窗口句柄；不在 Tauri 中时为 null。 */
function appWindow(): TauriWindow | null {
  if (!isTauri()) return null;
  cached ??= getCurrentWindow();
  return cached;
}

export function onPinChange(listener: PinListener): void {
  pinListeners.add(listener);
}

export function onMaximizeChange(listener: MaximizeListener): void {
  maximizeListeners.add(listener);
}

function emitPin(): void {
  for (const listener of pinListeners) listener(pinned);
}

function emitMaximize(): void {
  for (const listener of maximizeListeners) listener(maximized);
}

export async function setPinned(next: boolean): Promise<void> {
  await appWindow()?.setAlwaysOnTop(next);
  pinned = next;
  emitPin();
}

export async function togglePinned(): Promise<boolean> {
  await setPinned(!pinned);
  return pinned;
}

export async function minimizeWindow(): Promise<void> {
  await appWindow()?.minimize();
}

export async function toggleMaximizeWindow(): Promise<void> {
  const win = appWindow();
  if (!win) {
    maximized = !maximized;
    emitMaximize();
    return;
  }
  await win.toggleMaximize();
  await syncMaximized();
}

/** 收起到托盘的唯一入口，将来接「最小化到托盘」配置也只改这里。 */
export async function hideWindow(): Promise<void> {
  await appWindow()?.hide();
}

export async function showWindow(): Promise<void> {
  const win = appWindow();
  if (!win) return;
  await win.show();
  await win.setFocus();
}

export async function toggleWindow(): Promise<void> {
  const win = appWindow();
  if (!win) return;

  // 以窗口的**真实可见性**为准，不能只信 JS 侧状态：窗口可能被外部隐藏
  // （Win+D 显示桌面、DWM 最小化），状态不同步的症状是「按热键没反应」。
  if (await win.isVisible()) await hideWindow();
  else await showWindow();
}

async function syncMaximized(): Promise<void> {
  const win = appWindow();
  if (!win) return;

  const next = await win.isMaximized();
  if (next === maximized) return;
  maximized = next;
  emitMaximize();
}

/**
 * 启动时把状态对齐到窗口真实值。窗口配置里的 alwaysOnTop 由应用配置决定，
 * 读回来才不会出现「按钮显示置顶、实际没置顶」。
 */
export async function initWindowState(): Promise<void> {
  const win = appWindow();
  if (!win) {
    emitPin();
    emitMaximize();
    return;
  }

  pinned = await win.isAlwaysOnTop();
  maximized = await win.isMaximized();
  emitPin();
  emitMaximize();

  // 双击标题栏 / Win+方向键 / Aero Snap 都会改最大化状态，只能靠事件同步
  await win.onResized(() => {
    void syncMaximized();
  });
}
