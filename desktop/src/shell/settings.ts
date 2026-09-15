// ─────────────────────────────────────────────────────────────────────────────
// 设置面板（右侧抽屉）。
//
// 骨架阶段先把**设置项清单**落下来，让外壳结构完整；取值统一显示占位符，
// 等 AppConfig 接通后由配置层填值。
//
// 例外的几项已经真实可用 —— 它们都属于外壳自身或跨页面的共享偏好，没有它们
// 这个面板就只是张图：
//   · 主题         → theme.ts（light / dark / sys）
//   · 常驻置顶     → window.ts（与标题栏图钉共享同一份状态）
//   · 时间轴默认粒度 → data/timeline.ts（与任务页工具行共享同一份状态）
// ─────────────────────────────────────────────────────────────────────────────

import {
  TIMELINE_RANGES,
  onTimelineRangeChange,
  setTimelineRange,
  timelineRange,
} from "../data/timeline";
import { el, need } from "./dom";
import { seg } from "./seg";
import { getThemeMode, setThemeMode, type ThemeMode } from "./theme";
import { onPinChange, togglePinned } from "./window";

interface SettingRow {
  label: string;
  /** 只读展示值；缺省显示占位符。 */
  value?: string;
  /** 自定义控件，优先于 value。 */
  control?: () => HTMLElement;
}

interface SettingGroup {
  title: string;
  rows: SettingRow[];
}

interface TabSpec {
  id: string;
  label: string;
  groups: SettingGroup[];
}

const PLACEHOLDER = "—";

function themeControl(): HTMLElement {
  const modes: { id: ThemeMode; label: string }[] = [
    { id: "light", label: "亮色" },
    { id: "dark", label: "暗色" },
    { id: "sys", label: "跟随系统" },
  ];

  const buttons = modes.map((mode) => {
    const button = el("button", {
      "data-th": mode.id,
      text: mode.label,
      class: getThemeMode() === mode.id ? "on" : undefined,
    });
    button.addEventListener("click", () => {
      setThemeMode(mode.id);
      for (const other of buttons) {
        other.classList.toggle("on", other === button);
      }
    });
    return button;
  });

  return el("div", { class: "seg", style: "flex:none;width:auto" }, buttons);
}

/** 任务页时间轴的默认粒度。用短标签（周 / 月 / 30 天）——设置行的右侧没有
 *  任务页工具行那么宽，写「近 30 天」会把标题挤成两行。 */
function timelineRangeControl(): HTMLElement {
  const control = seg(
    TIMELINE_RANGES.map((range) => ({ value: range.value, label: range.short })),
    timelineRange(),
    (value) => setTimelineRange(value),
  );

  // 在任务页工具行里改了同一项，这里那排按钮也要跟上
  onTimelineRangeChange(() => control.setValue(timelineRange()));

  control.root.style.flex = "none";
  control.root.style.width = "auto";
  return control.root;
}

function pinControl(): HTMLElement {
  const toggle = el("span", { class: "sw", role: "switch", tabindex: "0" });

  onPinChange((pinned) => {
    toggle.classList.toggle("on", pinned);
    toggle.setAttribute("aria-checked", String(pinned));
  });

  toggle.addEventListener("click", () => void togglePinned());
  toggle.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      void togglePinned();
    }
  });

  return toggle;
}

const TABS: TabSpec[] = [
  {
    id: "gen",
    label: "常规",
    groups: [
      {
        title: "外观",
        rows: [{ label: "主题", control: themeControl }],
      },
      {
        title: "唤起与常驻",
        rows: [
          { label: "全局热键", value: "Ctrl+Shift+Space" },
          { label: "常驻置顶", control: pinControl },
          { label: "最小化到托盘" },
          { label: "开机自启动" },
        ],
      },
      {
        title: "任务视图",
        rows: [
          { label: "时间轴默认粒度", control: timelineRangeControl },
          { label: "已完成任务置底" },
          { label: "保存后自动收起抽屉" },
        ],
      },
      {
        title: "自动化",
        rows: [
          { label: "自动归档" },
          { label: "归档阈值（天）" },
          { label: "每日摘要" },
          { label: "安静时段" },
          { label: "逾期自动标记" },
        ],
      },
    ],
  },
  // 「AI 助手」页签已移除（2026-09-15）。它那一页 7 行里没有一行接了后端，
  // 值全是占位（其中「专用工作区」还指向一个已经不存在的目录）—— 一排死开关
  // 比没有这一页更误导人：看着能配，点了什么都不会发生。真要接入 AI 能力时，
  // 把它连着能用的开关一起放回来；现在这 7 行在 git 历史里取回即可。
  {
    id: "part",
    label: "分区",
    groups: [
      {
        title: "分区管理",
        rows: [
          { label: "工作" },
          { label: "学习" },
          { label: "个人" },
          { label: "演示空间" },
        ],
      },
      {
        title: "归档",
        rows: [{ label: "已完成任务置底" }, { label: "归档后从列表隐藏" }],
      },
    ],
  },
  {
    id: "about",
    label: "关于",
    groups: [
      {
        title: "关于",
        rows: [
          { label: "版本" },
          { label: "架构", value: "2.0 界面 · Windows 适配" },
          { label: "帮助文档", value: "随包分发" },
        ],
      },
    ],
  },
];

function renderRow(row: SettingRow): HTMLElement {
  const control = row.control?.();

  const right =
    control ??
    el("span", {
      class: row.value ? "v mono" : "v mono dim",
      text: row.value ?? PLACEHOLDER,
    });

  return el("div", { class: "set-row" }, [
    el("span", { text: row.label }),
    control ? right : el("span", { class: "v" }, [right]),
  ]);
}

function renderTab(tab: TabSpec): HTMLElement {
  const sections = tab.groups.map((group) =>
    el("div", { class: "set-sec" }, [
      el("div", { class: "set-sec-t", text: group.title }),
      ...group.rows.map(renderRow),
    ]),
  );

  sections.push(
    el("div", { class: "set-sec" }, [
      el("div", {
        class: "ph-note dim",
        text: "设置项由 AppConfig 驱动，当前仅主题、常驻置顶与时间轴粒度已接通",
      }),
    ]),
  );

  return el("div", { class: "set-tab", id: `tab-${tab.id}` }, sections);
}

// ─── 装配 ────────────────────────────────────────────────────────────────────

const drawer = (): HTMLElement => need("#set-drawer");
const body = (): HTMLElement => need("#set-body");

let activeTab = TABS[0].id;

function showTab(id: string): void {
  activeTab = id;
  for (const button of drawer().querySelectorAll<HTMLElement>("#set-tabs button")) {
    button.classList.toggle("on", button.dataset.tab === id);
  }
  for (const panel of body().querySelectorAll<HTMLElement>(".set-tab")) {
    panel.classList.toggle("active", panel.id === `tab-${id}`);
  }
}

export function openSettings(tab?: string): void {
  showTab(tab ?? activeTab);
  drawer().classList.add("open");
}

export function closeSettings(): void {
  drawer().classList.remove("open");
}

export const isSettingsOpen = (): boolean => drawer().classList.contains("open");

export function toggleSettings(): void {
  if (isSettingsOpen()) closeSettings();
  else openSettings();
}

export function mountSettings(): void {
  body().replaceChildren(...TABS.map(renderTab));

  for (const button of drawer().querySelectorAll<HTMLElement>("#set-tabs button")) {
    button.addEventListener("click", () => showTab(button.dataset.tab ?? TABS[0].id));
  }

  need("#set-close").addEventListener("click", closeSettings);
  need("#set-btn").addEventListener("click", toggleSettings);

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && isSettingsOpen()) closeSettings();
  });

  showTab(activeTab);
}
