// ─────────────────────────────────────────────────────────────────────────────
// 入口：装配外壳。
//
// 这里只做「按顺序调用 mount」，不放业务逻辑 —— 各模块自己管好自己的节点。
// 顺序要求：主题先落 data-theme（避免首帧闪白），再装配会读它的标题栏。
// ─────────────────────────────────────────────────────────────────────────────

import { isTauri } from "@tauri-apps/api/core";
import { bootStore } from "./data/store";
import { setupHotkey } from "./shell/hotkey";
import { bootLock } from "./shell/lock";
import { mountNav } from "./shell/nav";
import { mountPartition } from "./shell/partition";
import { mountSettings } from "./shell/settings";
import { initTheme } from "./shell/theme";
import { mountTitlebar } from "./shell/titlebar";
import { toast } from "./shell/toast";
import { setupTray } from "./shell/tray";
import { initWindowState } from "./shell/window";

const describe = (error: unknown): string =>
  error instanceof Error ? error.message : String(error);

async function boot(): Promise<void> {
  initTheme();

  // 数据先装好再画页面：否则第一帧画的是种子数据，存档一到位整屏跳一次。
  // 读档失败不该让外壳起不来（读的是样例数据，不是关键路径）。
  await bootStore().catch(() => {});
  // 分区密码与空闲锁定：要在画页面之前决定要不要先挡一层
  await bootLock().catch(() => {});

  mountTitlebar();
  mountNav();
  mountPartition();
  mountSettings();

  // 对齐窗口真实状态（置顶 / 最大化），失败不影响外壳可用
  await initWindowState().catch(() => {});

  // 纯 vite 预览（浏览器里调样式）没有宿主，托盘和热键无从谈起
  if (!isTauri()) return;

  // 托盘与热键是常驻应用的第二入口：全挂了就意味着窗口一旦收起就再也唤不回，
  // 必须明确告警而不是静默降级。
  const failures: string[] = [];
  await setupTray().catch((error) => failures.push(`托盘（${describe(error)}）`));
  await setupHotkey().catch((error) => failures.push(`热键（${describe(error)}）`));

  if (failures.length === 2) {
    toast("托盘与热键均不可用：窗口收起后只能从任务管理器结束进程");
  } else if (failures.length === 1) {
    toast(`${failures[0]}不可用`);
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => void boot());
} else {
  void boot();
}
