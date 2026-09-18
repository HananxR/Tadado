// ─────────────────────────────────────────────────────────────────────────────
// 开机自启动。
//
// 开关本身是系统的事（Windows 写注册表 Run 项），由 tauri-plugin-autostart 做，
// 这里只是给它一个「浏览器里也不会炸」的门面：纯 vite 预览没有 Tauri 宿主，
// 三个调用全都会失败 —— 那种环境下这一行显示为不可用，而不是抛异常把设置面板
// 整个带下去（`.catch` 在设置面板里是做不到的，那里是同步渲染）。
// ─────────────────────────────────────────────────────────────────────────────

import { disable, enable, isEnabled } from "@tauri-apps/plugin-autostart";

/**
 * 现在是不是开着。
 *
 * `null` = 这个环境问不到（浏览器预览）。调用方据此显示「当前环境不可用」，
 * 而不是把 null 当成「关着」—— 那会让用户以为开关坏了。
 */
export async function autostartEnabled(): Promise<boolean | null> {
  try {
    return await isEnabled();
  } catch {
    return null;
  }
}

/** 开 / 关。返回是否真的改成功了（浏览器里永远是 false）。 */
export async function setAutostart(on: boolean): Promise<boolean> {
  try {
    if (on) await enable();
    else await disable();
    return true;
  } catch {
    return false;
  }
}
