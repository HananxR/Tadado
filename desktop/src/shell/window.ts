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
//
// **「把窗口叫回来」不归这一层**：全局热键、托盘左键、托盘菜单「显示窗口」、
// 单实例第二次启动，全都在原生侧（src-tauri/src/lib.rs）走同一套「显示 → 还原
// → 聚焦」。这么分是因为那几个入口**不能依赖界面活着** —— 跨日续跑会重载
// webview（见 shell/rollover.ts），界面也可能卡住；那时候热键必须照样能把窗口
// 叫回来，而界面上的按钮按不动就是按不动。
// 于是这一层只留「收起来」的动作（标题栏的关闭 / 最小化）。
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
