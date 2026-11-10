// ─────────────────────────────────────────────────────────────────────────────
// 窗口显隐三态判定的**书面规则**：可见 / 隐藏 / 最小化，按一次「唤起」该做什么。
//
// 运行时实现在原生侧（`src-tauri/src/lib.rs` 的 `decide_window_action`）——
// 热键、托盘、单实例都在那边执行，界面这一层不碰窗口显隐（理由见 shell/window.ts
// 开头那段）。这份 TypeScript 是同一条规则的**书面版本**，两边必须一致：
// 改了这边就要改那边，反之亦然。
//
// 为什么规则是「最小化优先」：Windows 上**最小化的窗口仍然算「可见」**
// （IsWindowVisible 对最小化窗口返回 TRUE）。所以只看 visible 的话，最小化态会被
// 误判成「已经开着」→ 按热键反而把窗口藏掉；再按一次走 show()，而 show() 是
// SW_SHOW、**不会把最小化窗口还原**（还原是 SW_RESTORE）—— 症状正是用户报的
// 「只到任务栏，需要从任务栏再点一次」。
//
// 零依赖、无副作用：node 脚本（e2e/window-state.mjs）直接 import 它断言，于是
// 「最小化优先」这条最容易回归的规则在 CI 上也有检查（CI 不装 Rust 工具链，
// 原生侧那份实现另有 `cargo test` 钉着）。
// ─────────────────────────────────────────────────────────────────────────────

/** 一次「唤起」该做的动作。 */
export type WindowAction = "restore" | "show" | "hide";

/** 窗口此刻的真实状态（问系统要，不信前端自记的那份）。 */
export interface WindowState {
  /** 窗口是否可见（注意：最小化的窗口也算可见）。 */
  visible: boolean;
  /** 窗口是否处于最小化。 */
  minimized: boolean;
}

/**
 * 判定该做什么。
 *
 * - 最小化 → 还原（`restore`）：先把最小化这一层解开，别让它冒充「已经开着」。
 * - 其余可见 → 收起（`hide`）：已经开着，按一次就是收起来。
 * - 其余 → 显示（`show`）。
 */
export function decideWindowAction(state: WindowState): WindowAction {
  if (state.minimized) return "restore";
  if (state.visible) return "hide";
  return "show";
}
