// ─────────────────────────────────────────────────────────────────────────────
// 主题。
//
// 三态：light / dark / sys。DESIGN.md 2.13 规定主题由**应用配置**决定而不是
// 跟随系统，默认浅色 —— 所以：
//   · 未设置过时默认 light，而不是读 prefers-color-scheme
//   · sys 是用户显式选项，靠 CSS 里的媒体查询兜底（见 tokens.css）
//   · 值存 localStorage，等配置层接通后改由 AppConfig 提供
// ─────────────────────────────────────────────────────────────────────────────

export type ThemeMode = "light" | "dark" | "sys";
export type ResolvedTheme = "light" | "dark";

const STORAGE_KEY = "tadado-theme";
const DEFAULT_MODE: ThemeMode = "light";

const listeners = new Set<(theme: ResolvedTheme) => void>();

const isMode = (value: unknown): value is ThemeMode =>
  value === "light" || value === "dark" || value === "sys";

function readStored(): ThemeMode {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return isMode(raw) ? raw : DEFAULT_MODE;
  } catch {
    // 隐私模式 / 存储被禁用时不该拖垮启动
    return DEFAULT_MODE;
  }
}

let mode: ThemeMode = readStored();

const darkQuery = window.matchMedia("(prefers-color-scheme: dark)");

export const getThemeMode = (): ThemeMode => mode;

export function resolveTheme(source: ThemeMode = mode): ResolvedTheme {
  if (source === "sys") return darkQuery.matches ? "dark" : "light";
  return source;
}

function apply(): void {
  document.documentElement.dataset.theme = mode;
  const resolved = resolveTheme();
  for (const listener of listeners) listener(resolved);
}

export function setThemeMode(next: ThemeMode): void {
  mode = next;
  try {
    localStorage.setItem(STORAGE_KEY, next);
  } catch {
    // 存不下就只在本次运行内生效
  }
  apply();
}

/** 订阅「实际生效的明暗」，供标题栏图标之类的表现层同步。 */
export function onThemeChange(listener: (theme: ResolvedTheme) => void): void {
  listeners.add(listener);
}

export function initTheme(): void {
  // 系统主题变化只在 sys 模式下有影响，其余情况重放一次也无害
  darkQuery.addEventListener("change", () => {
    if (mode === "sys") apply();
  });
  apply();
}
