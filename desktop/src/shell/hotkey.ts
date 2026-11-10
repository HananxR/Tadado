// ─────────────────────────────────────────────────────────────────────────────
// 全局热键：只读状态门面。
//
// **热键在原生侧注册**（`src-tauri/src/lib.rs` 的 `build_hotkey`），不在前端。
// 曾经放在前端（JS 的 `register`，回调要绕 webview 的 IPC 通道才回到 JS）：跨日
// 续跑会重载 webview，通道随之消失，而系统层的热键还挂着 —— 那时按下去没人接，
// 就是「有时候唤不回来」。原生侧注册与界面生命周期解耦，界面活着死了都不影响。
//
// 前端这一层只做两件事：把「注册上了没有、是什么键」如实报给界面，以及给标题栏
// 提供键帽文案。加速键**只有原生侧那一份定义**，这里取的是它的副本 —— 两处写死
// 必然漂移，漂了就是「按的键和看到的键对不上」。
//
// 浏览器预览里没有宿主：返回 null 表示「不可用」（沿用 `shell/autostart.ts` 的范式）。
// ─────────────────────────────────────────────────────────────────────────────

import { invoke } from "@tauri-apps/api/core";

/** 原生侧报回来的热键信息。 */
export interface HotkeyInfo {
  /** 组合键本身（"Ctrl+Shift+Space"）。 */
  accelerator: string;
  /** 标题栏那几枚键帽（["Ctrl", "Shift", "Space"]）。 */
  keys: string[];
  /** 真的注册上了吗（被别的应用占用 → false）。 */
  registered: boolean;
}

/**
 * 读热键状态。浏览器预览 / 命令失败 → null（不可用）。
 */
export async function hotkeyInfo(): Promise<HotkeyInfo | null> {
  try {
    return await invoke<HotkeyInfo>("hotkey_info");
  } catch {
    return null;
  }
}
