#!/usr/bin/env node
// ─────────────────────────────────────────────────────────────────────────────
// 窗口显隐三态判定的断言。
//
// 为什么要有这一步：这条规则是「按热键唤不回主窗口」那个 bug 的心脏。Windows 上
// **最小化的窗口仍然算「可见」**（IsWindowVisible 对最小化窗口返回 TRUE），于是
// 旧判定把最小化当成「已经开着」→ 按热键反而把它藏掉；再按一次走 show()，而
// show() 是 SW_SHOW、**不会把最小化窗口还原** —— 症状正是「只到任务栏、再点一次
// 任务栏才出来」。
//
// 规则只有一句（最小化优先），但它同时被前端 shell/window.ts 和原生侧 lib.rs 用
// 着：两边实现一旦漂移，就是「热键能唤回、托盘唤不回」这种查起来最费劲的毛病。
// 规则写在本文件里、由脚本钉住，改坏立刻非零退出。
//
// 用法（desktop/）：node e2e/window-state.mjs
// 失败时非零退出；不静默通过。
// ─────────────────────────────────────────────────────────────────────────────

import { decideWindowAction } from "../src/shell/windowState.ts";

const failures = [];
const check = (name, ok, extra = "") => {
  console.log(`${ok ? "OK  " : "FAIL"} ${name}${extra ? ` — ${extra}` : ""}`);
  if (!ok) failures.push(name);
};

// 收起（隐藏）的窗口按热键要显示出来 —— 最基本的一条，先立住。
check(
  "收起（隐藏）的窗口按热键要显示出来",
  decideWindowAction({ visible: false, minimized: false }) === "show",
);

// 最小化的窗口按热键要**还原**，而不是当成「已经开着」把它藏掉。
// 这条曾经是错的：旧判定只看 visible，而最小化的窗口也算可见。
check(
  "最小化的窗口按热键要还原到屏幕",
  decideWindowAction({ visible: true, minimized: true }) === "restore",
);

// 开着（没最小化）的窗口按热键要收起 —— 这是热键的另一半用途。
check(
  "开着的窗口按热键要收起到托盘",
  decideWindowAction({ visible: true, minimized: false }) === "hide",
);

// **最小化优先于隐藏**：最小化的窗口在 Windows 上仍算「可见」，判定必须先看
// minimized。这条锁住的是「先判 visible 还是先判 minimized」这个顺序 ——
// 顺序写反了，最小化的窗口就会被当成「已经开着」而藏掉（就是那个 bug）。
check(
  "最小化 + 隐藏的窗口按热键也要还原（最小化优先）",
  decideWindowAction({ visible: false, minimized: true }) === "restore",
);

if (failures.length > 0) {
  console.error(`\n窗口三态判定：${failures.length} 条不通过`);
  process.exit(1);
}
console.log("\n窗口三态判定：全部通过");
