// ─────────────────────────────────────────────────────────────────────────────
// 设置面板（右侧抽屉）。
//
// 这里的每一行都必须**真的**接到了什么 —— 要么开关真的能用，要么值就是代码里的
// 真实状态。骨架阶段那种「清单先摆出来、取值统一 `—`」的做法已经废止：
// 一排看着能配、点了什么都不会发生的开关，比没有这一页更误导人 —— 人会把时间
// 花在反复拨开关上，然后开始怀疑整个应用是坏的。没做的要么删掉，要么老老实实
// 写成只读值。
//
// 已经接通的几项都属于外壳自身或跨页面的共享偏好：
//   · 主题           → theme.ts（light / dark / sys）
//   · 常驻置顶       → window.ts（与标题栏图钉共享同一份状态）
//   · 时间轴默认粒度 → data/timeline.ts（与任务页工具行共享同一份状态）
//   · 分区口令 / 空闲锁定 → lock.ts
//   · 保存后收起抽屉 → drawerPref.ts
// ─────────────────────────────────────────────────────────────────────────────

import { TASKS } from "../data/mock";
import { PARTITIONS, activePartitionId } from "../data/partitions";
import { onDataChange } from "../data/store";
import {
  TIMELINE_RANGES,
  onTimelineRangeChange,
  setTimelineRange,
  timelineRange,
} from "../data/timeline";
import { confirmAction } from "./confirm";
import { el, need } from "./dom";
import { setCloseOnSave, shouldCloseOnSave } from "./drawerPref";
import { hasPassword, idleLimit, isUnlocked, setIdleMinutes, setPassword } from "./lock";
import { promptText } from "./prompt";
import { seg } from "./seg";
import { toast } from "./toast";
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

/**
 * 分区口令：先挑分区，再设 / 清。
 *
 * 不做「找回」这一步：单机应用里加安全问题或邮箱找回，只会把「防君子」变成
 * 「防自己」。忘了就是忘了 —— 所以设置时把这句话摆在浮层里，而不是等忘了才说。
 */
function passwordControl(): HTMLElement {
  let target = activePartitionId();

  const picker = seg(
    PARTITIONS.map((partition) => ({ value: partition.id, label: partition.name })),
    target,
    (value) => {
      target = value;
      sync();
    },
  );
  picker.root.style.flex = "none";
  picker.root.style.width = "auto";

  const button = el("button", { class: "btn sm", type: "button" });

  const sync = (): void => {
    button.textContent = hasPassword(target) ? "清除口令" : "设置口令";
  };

  button.addEventListener("click", () => {
    void (async () => {
      const name = PARTITIONS.find((partition) => partition.id === target)?.name ?? target;

      if (hasPassword(target)) {
        const ok = await confirmAction({
          title: `清除「${name}」的口令？`,
          detail: "之后进入这个分区不再需要口令。",
          confirmText: "清除",
        });
        if (!ok) return;
        await setPassword(target, "");
        toast(`已清除「${name}」的口令`);
        sync();
        return;
      }

      const password = await promptText({
        title: `给「${name}」设口令`,
        detail: "这是防路过的人瞄一眼，不是加密存储 —— 而且忘了没法找回，请自己记牢。",
        placeholder: "口令",
        password: true,
        confirmText: "设置",
      });
      if (password === null) return;
      if (!password.trim()) {
        toast("口令不能为空");
        return;
      }

      await setPassword(target, password);
      toast(`已为「${name}」设置口令`);
      sync();
    })();
  });

  sync();
  return el("div", { class: "rowctl" }, [picker.root, button]);
}

/** 空闲多久自动上锁。0 = 不自动锁（默认）。 */
function idleLockControl(): HTMLElement {
  const control = seg(
    [
      { value: "0", label: "关" },
      { value: "5", label: "5 分" },
      { value: "10", label: "10 分" },
      { value: "30", label: "30 分" },
    ],
    String(idleLimit()),
    (value) => {
      void setIdleMinutes(Number(value)).then(() => {
        toast(value === "0" ? "已关闭空闲锁定" : `空闲 ${value} 分钟后自动上锁`);
      });
    },
  );
  control.root.style.flex = "none";
  control.root.style.width = "auto";
  return control.root;
}

/** 保存之后要不要把抽屉收起来。默认收（DESIGN.md 的规定），但连续整理时不收更顺手。 */
function closeOnSaveControl(): HTMLElement {
  const toggle = el("span", { class: "sw", role: "switch", tabindex: "0" });

  const paint = (): void => {
    toggle.classList.toggle("on", shouldCloseOnSave());
    toggle.setAttribute("aria-checked", String(shouldCloseOnSave()));
  };

  const flip = (): void => {
    void setCloseOnSave(!shouldCloseOnSave()).then(paint);
  };

  toggle.addEventListener("click", flip);
  toggle.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    flip();
  });

  paint();
  return toggle;
}

/**
 * 一个分区一行：条数 + 锁没锁。
 *
 * 上锁状态也摆在这里 —— 不然「哪几个分区要口令」只能靠一个个点过去试。
 */
function partitionRow(partition: (typeof PARTITIONS)[number]): SettingRow {
  return {
    label: partition.name,
    control: () => {
      const count = el("span", { class: "v mono" });
      const lock = el("span", { class: "lock" });

      const paint = (): void => {
        count.textContent = `${TASKS.filter((task) => task.partition === partition.id).length} 条`;
        lock.textContent = hasPassword(partition.id)
          ? isUnlocked(partition.id)
            ? "🔓"
            : "🔒"
          : "";
      };

      onDataChange(paint);
      paint();
      return el("span", { class: "rowctl" }, [count, lock]);
    },
  };
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
          // 只读值：这个组合键是 shell/hotkey.ts 里的常量，不是可配项。
          // 摆成能改的样子、改完才发现不生效，比直接把现实摆出来更气人
          { label: "全局热键", value: "Ctrl+Shift+Space" },
          { label: "常驻置顶", control: pinControl },
        ],
      },
      {
        title: "任务视图",
        rows: [
          { label: "时间轴默认粒度", control: timelineRangeControl },
          { label: "保存后收起抽屉", control: closeOnSaveControl },
        ],
      },
      {
        title: "安全",
        rows: [
          { label: "分区口令", control: passwordControl },
          { label: "空闲锁定", control: idleLockControl },
        ],
      },
      {
        title: "自动化",
        rows: [
          // 逾期标记不设开关：它每次加载顺手扫一遍（store.refreshOverdue），
          // 关掉的后果是过了截止日的任务永远停在「待办」上，比自动更正还糟。
          // 归档 / 摘要 / 安静时段一样没做 —— 没做就不摆一排好看的开关
          { label: "逾期自动标记", value: "每次加载时扫一遍" },
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
    // 分区里有什么（多少条、锁没锁）是活的，所以这些行自己订阅 dataChanged ——
    // 设置面板的节点是常驻的，不订阅的话数字会停在「打开设置那一刻」
    groups: [{ title: "分区", rows: PARTITIONS.map(partitionRow) }],
  },
  {
    id: "about",
    label: "关于",
    groups: [
      {
        title: "关于",
        rows: [
          // 版本号与 package.json 一致（为一个版本号去开 JSON 导入不值得）
          { label: "版本", value: "0.1.0 · Tauri 重写" },
          { label: "架构", value: "2.0 界面 · Windows 适配" },
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

  // 以前每个页签底下都压一行「仅主题 / 置顶 / 粒度已接通」的说明。
  // 现在这一句已经不成立（安全组、保存行为都真的生效），而没接通的项目根本
  // 不在这里了 —— 留着它等于继续替每一行道歉，不如让它别来稀释视线。
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
