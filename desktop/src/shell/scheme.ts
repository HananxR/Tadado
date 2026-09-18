// ─────────────────────────────────────────────────────────────────────────────
// 热力图配色方案。
//
// 四套色阶早就写在 tokens.css 里（warm / green / sea / sakura，含深色档），但一直
// 没有任何代码去设 `data-scheme` —— 等于四套色只能靠手改 DOM 才看得见。这里把
// 它接通：一个值、一处持久化，和 theme.ts 同一套写法（值存 localStorage，等配置
// 层接通后改由 AppConfig 提供）。
//
// 为什么只作用于热力图：色阶变量 --h0..--h4 只被热力图用，改它不会牵动全局配色。
// ─────────────────────────────────────────────────────────────────────────────

export type HeatScheme = "indigo" | "warm" | "green" | "sea" | "sakura";

export interface SchemeSpec {
  id: HeatScheme;
  label: string;
  /** 盖在按钮上的示意色，取该套色阶的第 3 档（--h2）。 */
  swatch: string;
}

export const SCHEMES: SchemeSpec[] = [
  // 默认这套是新配的：旧的四套在浅色底上第 1 档几乎和背景同色（--h1 只比 --h0
  // 深一点点），深色底上第 2 档又几乎看不见 —— 一排格子看上去像同一个颜色。
  // 现在每一档的明度差都在 15% 以上，深浅两套主题下都能一眼看出层级。
  { id: "indigo", label: "靛青", swatch: "#7b88e8" },
  { id: "warm", label: "暖橙", swatch: "#e8b96a" },
  { id: "green", label: "草绿", swatch: "#8fc47e" },
  { id: "sea", label: "海蓝", swatch: "#8ab5d4" },
  { id: "sakura", label: "樱粉", swatch: "#e896a8" },
];

// 键名带 v2：换默认配色是一次性的「重置」，沿用旧键的话，之前选过暖橙的人永远
// 留在那套洗白的色阶上，看不到新默认。
const STORAGE_KEY = "tadado-heat-scheme-v2";
const DEFAULT_SCHEME: HeatScheme = "indigo";

const listeners = new Set<(scheme: HeatScheme) => void>();

const isScheme = (value: unknown): value is HeatScheme =>
  SCHEMES.some((item) => item.id === value);

function readStored(): HeatScheme {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return isScheme(raw) ? raw : DEFAULT_SCHEME;
  } catch {
    // 隐私模式 / 存储被禁用时不该拖垮启动
    return DEFAULT_SCHEME;
  }
}

let scheme: HeatScheme = readStored();

export const getScheme = (): HeatScheme => scheme;

function apply(): void {
  document.documentElement.dataset.scheme = scheme;
  for (const listener of listeners) listener(scheme);
}

export function setScheme(next: HeatScheme): void {
  scheme = next;
  try {
    localStorage.setItem(STORAGE_KEY, next);
  } catch {
    // 存不下就只在本次运行内生效
  }
  apply();
}

/** 订阅配色变化，供色板按钮同步选中态。 */
export function onSchemeChange(listener: (scheme: HeatScheme) => void): void {
  listeners.add(listener);
}

export function initScheme(): void {
  apply();
}
