// ─────────────────────────────────────────────────────────────────────────────
// 入口：装配外壳。
//
// 这里只做「按顺序调用 mount」，不放业务逻辑 —— 各模块自己管好自己的节点。
// 顺序要求：主题先落 data-theme（避免首帧闪白），再装配会读它的标题栏。
// ─────────────────────────────────────────────────────────────────────────────

import { isTauri } from "@tauri-apps/api/core";
import { storageIssue } from "./data/db";
import { bootPartitions } from "./data/partitions";
import { bootStore, progressHealReport } from "./data/store";
import { setupHotkey } from "./shell/hotkey";
import { bootLock } from "./shell/lock";
import { mountNav } from "./shell/nav";
import { mountPartition } from "./shell/partition";
import { watchDayRollover } from "./shell/rollover";
import { initScheme } from "./shell/scheme";
import { mountSettings } from "./shell/settings";
import { initTheme } from "./shell/theme";
import { mountTitlebar } from "./shell/titlebar";
import { mountTrayBridge } from "./shell/trayBridge";
import { toast } from "./shell/toast";
import { initWindowState } from "./shell/window";

const describe = (error: unknown): string =>
  error instanceof Error ? error.message : String(error);

async function boot(): Promise<void> {
  initTheme();
  // 热力图色阶：和主题一样是「画之前就要定下来」的东西
  initScheme();

  // 数据先装好再画页面：否则第一帧画的是种子数据，存档一到位整屏跳一次。
  // 读档失败不该让外壳起不来（读的是样例数据，不是关键路径）。
  await bootStore().catch(() => {});
  // 分区列表可增删，先读存档再用 —— 用户自己分过的区不能被内置那四个盖回去。
  // 排在锁之前：空闲锁定按分区判定，得先知道有哪些区
  await bootPartitions().catch(() => {});
  // 分区密码与空闲锁定：要在画页面之前决定要不要先挡一层
  await bootLock().catch(() => {});

  mountTitlebar();
  mountNav();
  mountPartition();
  mountSettings();

  // 存储出问题了要说出来：以前这种情况是「静静地降级 / 静静地空库」，
  // 用户看到的是「我的任务全没了」，然后开始怀疑自己 —— 而数据其实还在
  const issue = storageIssue();
  if (issue !== null) toast(`${issue}（数据没有被覆盖，请联系维护者）`);
  // 升级口径带来的批量归一（2026-10-16：「进度满 = 已完成」）要说一句 ——
  // 不说的话，用户看到的是任务成批变色、成批从任务页消失，那看起来就是数据坏了。
  // 只在启动扫到东西时才有报告（运行时每次编辑都是 0 条）
  const healed = progressHealReport();
  if (healed !== null) {
    // 逐条拼：只有「退回」时也别说成「已把 0 条标记为已完成」
    const parts: string[] = [];
    if (healed.done > 0) parts.push(`已把 ${healed.done} 条进度已满的任务标记为已完成`);
    if (healed.archived > 0) parts.push(`其中 ${healed.archived} 条按归档设置收进归档`);
    if (healed.rolledBack > 0) {
      parts.push(`${healed.rolledBack} 条「已完成但进度不足 100%」的退回进行中`);
    }
    // 历史遗留的归位（2026-10-17）：不说的话，用户看到的是「归档里的任务自己回来了」
    if (healed.restored > 0) {
      parts.push(`已把 ${healed.restored} 条重新打开过的任务从归档放回`);
    }
    if (parts.length > 0) toast(parts.join(" · "));
  }
  // 托盘菜单里的「新建任务 / 设置」要落到前端来做（见 shell/trayBridge.ts）
  mountTrayBridge();

  // 对齐窗口真实状态（置顶 / 最大化），失败不影响外壳可用
  await initWindowState().catch(() => {});

  // 纯 vite 预览（浏览器里调样式）没有宿主，托盘和热键无从谈起
  if (!isTauri()) return;

  // 托盘由 Rust 侧在进程启动时创建（与 webview 生命周期解耦，不会随重载重复叠加），
  // 前端只需管好热键。热键挂了意味着窗口收起后唤不回，必须明确告警。
  await setupHotkey().catch((error) => {
    toast(`热键（${describe(error)}）不可用`);
  });

  // 跨日续跑：托盘常驻的应用会开着过夜，过了午夜得把「今天」重新算一遍
  // （重载一次，见 shell/rollover.ts 里为什么是这个办法）。
  // 放在 `isTauri()` 之后：常驻这件事只存在于 Tauri，而 e2e 跑到一半被重载会更难查。
  watchDayRollover();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => void boot());
} else {
  void boot();
}
