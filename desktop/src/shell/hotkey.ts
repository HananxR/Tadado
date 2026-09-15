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
  await registerHotkey(HOTKEY_ACCELERATOR, (event) => {
    if (event.state === "Pressed") void toggleWindow();
  });

  const ok = await isRegistered(HOTKEY_ACCELERATOR);
  return `register(${HOTKEY_ACCELERATOR}) 成功，isRegistered=${ok}`;
}

export async function teardownHotkey(): Promise<void> {
  await unregisterHotkey(HOTKEY_ACCELERATOR).catch(() => {});
}
