// ─────────────────────────────────────────────────────────────────────────────
// 全局热键：唤起／收起主窗口。
//
// 文案与加速键放一起导出，标题栏的 kbd 提示从这里取 —— 两处写死必然漂移。
// ─────────────────────────────────────────────────────────────────────────────

import {
  isRegistered,
  register as registerHotkey,
  unregister as unregisterHotkey,
} from "@tauri-apps/plugin-global-shortcut";
import { toggleWindow } from "./window";

/** Tauri 加速键语法。 */
export const HOTKEY_ACCELERATOR = "Control+Shift+Space";

/** 展示用文案，供标题栏提示渲染。 */
export const HOTKEY_KEYS = ["Ctrl", "Shift", "Space"] as const;

export async function setupHotkey(): Promise<string> {
  // 先摘掉可能还挂着的那一份。**重载之后 Rust 侧的注册仍然在**（托盘与热键都由
  // Rust 侧持有，与 webview 生命周期解耦 —— 见 main.ts 开头那段），直接再 register
  // 会以「已注册」失败，于是每次重载都弹一句「热键不可用」，而热键其实是好用的。
  // 跨日自动重载（见 shell/rollover.ts）会让这条路成为常态，所以这里必须是幂等的。
  if (await isRegistered(HOTKEY_ACCELERATOR).catch(() => false)) await teardownHotkey();

  await registerHotkey(HOTKEY_ACCELERATOR, (event) => {
    if (event.state === "Pressed") void toggleWindow();
  });

  const ok = await isRegistered(HOTKEY_ACCELERATOR);
  return `register(${HOTKEY_ACCELERATOR}) 成功，isRegistered=${ok}`;
}

export async function teardownHotkey(): Promise<void> {
  await unregisterHotkey(HOTKEY_ACCELERATOR).catch(() => {});
}
