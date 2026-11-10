// ─────────────────────────────────────────────────────────────────────────────
// 标题栏装配：软件名 / 热键提示 / 窗口置顶 / 主题切换 / 窗口按钮
//
// 无边框窗口（decorations:false），拖拽靠 index.html 上的
// data-tauri-drag-region —— 按钮不带该属性，所以点按钮是点击而非拖窗。
// ─────────────────────────────────────────────────────────────────────────────

import { el, need } from "./dom";
import { hotkeyInfo } from "./hotkey";
import { resolveTheme, setThemeMode, onThemeChange, type ResolvedTheme } from "./theme";
import { toast } from "./toast";
import {
  hideWindow,
  minimizeWindow,
  onMaximizeChange,
  onPinChange,
  toggleMaximizeWindow,
  togglePinned,
} from "./window";

/**
 * 键帽提示：组合键从**原生侧**取（那才是注册用的真值，见 shell/hotkey.ts）。
 *
 * 拿不到就**不动** index.html 里的静态首帧 —— 浏览器预览里没有宿主，而那里写的
 * 正是同一个组合键；抹成空反而少了一句话。
 */
async function renderHotkeyHint(): Promise<void> {
  const info = await hotkeyInfo();
  if (info === null) return;

  const hint = need(".hint");
  const nodes: Node[] = [];

  info.keys.forEach((key, index) => {
    if (index > 0) nodes.push(document.createTextNode("+"));
    nodes.push(el("kbd", { text: key }));
  });
  nodes.push(document.createTextNode("随时唤起"));

  hint.replaceChildren(...nodes);
}

function bindPin(): void {
  const button = need("#tb-pin");
  button.addEventListener("click", () => {
    void togglePinned().then((pinned) => {
      // 说清楚「置顶」是什么：切成别的应用时它还在最上层，不会被盖住
      toast(pinned ? "已窗口置顶 · 切到别的应用也不会被盖住" : "已取消窗口置顶");
    });
  });

  onPinChange((pinned) => button.classList.toggle("on", pinned));
}

function bindTheme(): void {
  const button = need("#tb-theme");
  const sun = need<SVGSVGElement>(".i-sun", button);
  const moon = need<SVGSVGElement>(".i-moon", button);

  onThemeChange((theme: ResolvedTheme) => {
    sun.style.display = theme === "dark" ? "none" : "block";
    moon.style.display = theme === "dark" ? "block" : "none";
  });

  button.addEventListener("click", () => {
    // 按**当前生效**的明暗取反：sys 模式下点一下也要得到肉眼可见的变化，
    // 所以这里写死 light/dark，而不是在 light→sys→dark 之间轮转。
    setThemeMode(resolveTheme() === "dark" ? "light" : "dark");
  });
}

function bindWindowButtons(): void {
  need("#tb-min").addEventListener("click", () => void minimizeWindow());

  const maxButton = need("#tb-max");
  const maxIcon = need<SVGSVGElement>(".i-max", maxButton);
  const restoreIcon = need<SVGSVGElement>(".i-restore", maxButton);

  maxButton.addEventListener("click", () => void toggleMaximizeWindow());
  onMaximizeChange((maximized) => {
    maxIcon.style.display = maximized ? "none" : "block";
    restoreIcon.style.display = maximized ? "block" : "none";
    maxButton.title = maximized ? "还原" : "最大化";
  });

  // 关闭 = 收起常驻。真正退出走托盘菜单，避免误点把常驻应用杀掉。
  need("#tb-close").addEventListener("click", () => {
    void hideWindow().then(() => toast("已收起到托盘，热键可随时唤回"));
  });
}

export function mountTitlebar(): void {
  // 键帽要问原生侧要（一次 IPC），所以不等它 —— 首帧那几枚静态键帽先顶着，
  // 内容一样，不会闪。
  void renderHotkeyHint();
  bindPin();
  bindTheme();
  bindWindowButtons();
}
