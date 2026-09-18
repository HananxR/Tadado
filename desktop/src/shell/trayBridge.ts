// ─────────────────────────────────────────────────────────────────────────────
// 托盘的「动作」这一半。
//
// 托盘图标和菜单在 Rust 侧（src-tauri/src/lib.rs）—— 那边的菜单项写不了前端
// 状态，所以「新建任务」「设置」两项只做一件事：把窗口叫出来 + 发一条事件；
// 真正切页面、开对话框在这里做。
//
// 为什么不是前端建托盘：托盘必须**进程级只建一次**，而前端每次重载都会重跑一遍
// 挂载代码 —— 那会堆出一排同名图标（lib.rs 顶部记着这段历史）。
//
// 浏览器预览里没有 Tauri 事件系统，listen 会失败 —— 静默忽略，那一半功能只在
// 桌面端存在。
// ─────────────────────────────────────────────────────────────────────────────

import { listen } from "@tauri-apps/api/event";
import { openSettings } from "./settings";

/** 托盘菜单能触发的动作。名字与 lib.rs 里 emit 的 payload 一一对应。 */
type TrayAction = "settings";

export function mountTrayBridge(): void {
  void listen<TrayAction>("tray", (event) => {
    if (event.payload === "settings") openSettings();
  }).catch(() => {
    // 浏览器预览：没有事件系统，也没有托盘
  });
}
