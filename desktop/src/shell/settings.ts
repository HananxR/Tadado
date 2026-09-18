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
//   · 主题 → theme.ts（light / dark / sys）
//   · 分区（增 / 删 / 改名 / 指定默认，以及**各分区各一份**的口令 / 空闲锁定 /
//     自动归档）→ data/partitions.ts + lock.ts + data/store.ts
//
// **一页到底，不分页签**（2026-09-17）：分了「常规 / 分区 / 关于」三页之后，每页
// 只剩两三行，翻页成本比滚动高，还得记住「口令在哪一页」。现在整页从上到下就是
// 外观 → 窗口 → 分区 → 关于。
//
// 切到别的模块会收起（和「编辑任务」抽屉一致）：设置讲的是外壳与分区，翻页后还
// 挂在这儿，说不清它属于谁。
// ─────────────────────────────────────────────────────────────────────────────

import { getVersion } from "@tauri-apps/api/app";
import { autostartEnabled, setAutostart } from "./autostart";
import { TASKS } from "../data/mock";
import {
  PARTITIONS,
  addPartition,
  defaultPartitionId,
  onPartitionListChange,
  type Partition,
  removePartition,
  renamePartition,
  setDefaultPartition,
} from "../data/partitions";
import { archiveAfterDays, onDataChange, setArchiveDays } from "../data/store";

import { confirmAction } from "./confirm";
import { el, need } from "./dom";
import {
  hasPassword,
  idleLimit,
  isLockScreenUp,
  isUnlocked,
  onLockChange,
  restoreLockScreen,
  setIdleMinutes,
  setPassword,
  suppressLockScreen,
} from "./lock";
import { panelClosed, panelOpened, registerOpen, registerPanel } from "./panels";
import { promptText, promptWithExtra } from "./prompt";
import { subscribePages } from "./router";
import { seg } from "./seg";
import { toast } from "./toast";
import { getThemeMode, setThemeMode, type ThemeMode } from "./theme";

interface SettingRow {
  label: string;
  /** 只读展示值；缺省显示占位符。 */
  value?: string;
  /** 自定义控件，优先于 value。 */
  control?: () => HTMLElement;
  /** 给只读值一个 id，供事后填真实值（版本号要等 Tauri 回话）。 */
  id?: string;
}

interface SettingGroup {
  title: string;
  rows: SettingRow[];
  /** 组标题下的一段自定义内容（目前只有「关于」用得上）。 */
  intro?: () => HTMLElement;
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

/**
 * 分区口令：**设 / 改 / 清是同一个入口**。
 *
 * 它们本来就是一件事的三种结果（「这个分区要不要口令、要的话是什么」），拆成
 * 「设口令 / 改口令 / 清口令」三个按钮，用户每次都得先判断「我现在该点哪个」，
 * 而答案往往只有他自己知道 —— 一眼看不出这个区到底设没设。
 *
 * 改的时候**不校验旧口令**：它挡的是路过的人，不是拿到数据文件的人（见 lock.ts
 * 顶部），所以没有「证明你是你」的必要。忘了旧的，在别的分区里重设一个就行 ——
 * 要旧口令反而多出一个「忘了就彻底进不去」的死结，而屏风不值得配一把这样的锁。
 *
 * 清口令也不再二次确认：弹窗里那个「清除」就是明确动作，而口令随时能重设，
 * 没有什么会因此丢掉。
 */
async function editPassword(partition: Partition): Promise<void> {
  const had = hasPassword(partition.id);

  const result = await promptWithExtra({
    title: had ? `「${partition.name}」的口令` : `给「${partition.name}」设口令`,
    detail: had ? "填新口令就是换一个，留着不填就是不改" : undefined,
    placeholder: "新口令",
    password: true,
    confirmText: had ? "保存" : "设置",
    extra: had ? { label: "清除", danger: true } : undefined,
  });
  if (result === null) return;

  if (result.extra) {
    await setPassword(partition.id, "");
    toast(`已清除「${partition.name}」的口令`);
    return;
  }

  if (!result.value.trim()) {
    // 已经设过的、留空 = 不改（那就是取消的一种写法）；
    // 还没设过的留空则无处可退，说一句
    if (!had) toast("口令不能为空");
    return;
  }

  await setPassword(partition.id, result.value);
  toast(had ? `已改「${partition.name}」的口令` : `已设置「${partition.name}」的口令`);
}

/** 空闲多久自动上锁（**按分区**）。0 = 不自动锁（默认）。 */
function idleLockControl(partition: Partition): HTMLElement {
  const control = seg(
    [
      { value: "0", label: "关" },
      { value: "5", label: "5 分" },
      { value: "10", label: "10 分" },
      { value: "30", label: "30 分" },
    ],
    String(idleLimit(partition.id)),
    (value) => {
      // seg 是无状态的：选中态得由调用方自己更新，不然点了这一档，高亮还停在原来
      // 那个按钮上 —— 看着像没生效
      control.setValue(value);
      void setIdleMinutes(Number(value), partition.id).then(() => {
        toast(
          value === "0"
            ? `「${partition.name}」不再自动上锁`
            : `「${partition.name}」空闲 ${value} 分钟后上锁`,
        );
      });
    },
  );
  control.root.style.flex = "none";
  control.root.style.width = "auto";
  return control.root;
}

/** 自动归档（**按分区**）：已完成任务结束 N 天后收进归档。关 = 只在手动归档时收。 */
function archiveControl(partition: Partition): HTMLElement {
  const control = seg(
    [
      { value: "0", label: "关" },
      { value: "7", label: "7 天" },
      { value: "30", label: "30 天" },
      { value: "90", label: "90 天" },
    ],
    String(archiveAfterDays(partition.id)),
    (value) => {
      control.setValue(value);
      void setArchiveDays(Number(value), partition.id).then(() => {
        toast(
          value === "0"
            ? `「${partition.name}」不再自动归档`
            : `「${partition.name}」的已完成任务 ${value} 天后归档`,
        );
      });
    },
  );
  control.root.style.flex = "none";
  control.root.style.width = "auto";
  return control.root;
}

/**
 * 删分区。**里面有任务就不让删**。
 *
 * 不做「自动迁到别的分区」：迁去哪儿用户没得选，等于替他决定一批任务的归属，而
 * 这边只是想删个空分区。真要留着那些任务，他自己先移走更清楚 —— 所以按钮直接
 * 置灰，写明还剩几条。
 */
async function dropPartition(partition: Partition): Promise<void> {
  const mine = TASKS.filter((task) => task.partition === partition.id).length;
  if (mine > 0) {
    toast(`「${partition.name}」里还有 ${mine} 条任务，先移走再删`);
    return;
  }

  const ok = await confirmAction({ title: `删除分区「${partition.name}」？`, confirmText: "删除" });
  if (!ok) return;
  if (!removePartition(partition.id)) {
    toast("至少留一个分区");
    return;
  }
  toast(`已删除分区「${partition.name}」`);
}

/**
 * 分区那一段：**一个分区一行** —— 名字 · 条数 · 锁 · 口令 / 改名 / 删除。
 *
 * 口令、空闲锁定、自动归档都是**某个分区**的属性：工作区的东西比个人区更需要自动
 * 挡一层，过期任务也更该收走。摆成全局要么得先挑分区（多一层），要么取一个两头
 * 都不对的折中值。
 *
 * 后两项默认关、也是少数人用得着的那类设置，所以收在行尾「自动 ▾」里、展开了才
 * 建那两个 seg —— 四个分区不会各挂两个常年不动的控件。两项只要有一项不是「关」，
 * 按钮就染色：收着的时候也看得出这个分区动过默认值。
 *
 * 分区本身能增删改名：它本来就是用户想怎么分就怎么分的东西，只能看不能动等于没做。
 */
function partitionSection(): HTMLElement {
  const box = el("div", { class: "set-sec", id: "set-part" });

  const subRow = (label: string, control: HTMLElement): HTMLElement =>
    el("div", { class: "set-row" }, [
      el("span", { text: label }),
      el("span", { class: "rowctl" }, [control]),
    ]);

  const add = el("button", { class: "btn sm", type: "button", text: "+ 新建分区" });
  add.addEventListener("click", () => {
    void promptText({ title: "新建分区", placeholder: "分区名", confirmText: "创建" }).then(
      (name) => {
        if (name === null || !name.trim()) return;
        addPartition(name.trim());
        toast(`已新建分区「${name.trim()}」`);
      },
    );
  });

  // 重画时连订阅一起换掉：面板常驻，不退订的话每次重画都会多留一份旧闭包
  const unsubs: (() => void)[] = [];

  /** 收起的两行（自动归档 / 空闲锁定）挂在行下面，与行一起重排。 */
  const rowOf = (partition: Partition): HTMLElement[] => {
    const count = el("span", { class: "v mono" });
    const lock = el("span", { class: "lock" });
    // 默认分区是**一组里只有一个**的那种设置，所以画成单选点而不是按钮 ——
    // 「默认 / 设为默认」两种文字来回切换，一排分区里谁是哪个反而看不清
    const dot = el("button", { class: "part-dot", type: "button", role: "radio" });
    const pass = el("button", { class: "btn sm", type: "button", text: "设口令" });
    const auto = el("button", { class: "btn sm", type: "button", text: "自动 ▾" });
    const more = el("div", { class: "part-more", hidden: true });
    const del = el("button", { class: "btn sm", type: "button", text: "删除" });

    const paint = (): void => {
      count.textContent = `${TASKS.filter((task) => task.partition === partition.id).length} 条`;
      lock.textContent = !hasPassword(partition.id)
        ? ""
        : isUnlocked(partition.id)
          ? "🔓"
          : "🔒";

      // 设没设用**点亮**表示，不换按钮文字：设 / 改 / 清是同一个入口，
      // 换文字等于让用户先判断自己处在哪种状态
      const locked = hasPassword(partition.id);
      pass.classList.toggle("on", locked);
      pass.title = locked ? "改 / 清除这个分区的口令" : "给这个分区设口令";

      const mine = TASKS.filter((task) => task.partition === partition.id).length;
      del.disabled = mine > 0;
      del.title = mine > 0 ? `里面还有 ${mine} 条任务，先移走再删` : "删除这个分区";
      del.style.opacity = mine > 0 ? "0.45" : "";

      const isDefault = defaultPartitionId() === partition.id;
      dot.classList.toggle("on", isDefault);
      dot.setAttribute("aria-checked", String(isDefault));
      dot.title = isDefault ? "启动时进入这个分区" : "设为默认分区（启动时进入）";

      const days = archiveAfterDays(partition.id);
      const idle = idleLimit(partition.id);
      auto.classList.toggle("on", days > 0 || idle > 0);
      auto.title = `自动归档 ${days === 0 ? "关" : `${days} 天`} · 空闲锁定 ${idle === 0 ? "关" : `${idle} 分钟`}`;
    };

    pass.addEventListener("click", () => void editPassword(partition).then(paint));

    dot.addEventListener("click", () => {
      setDefaultPartition(partition.id);
      // 上锁的分区当默认，一开机就是一层口令。先说一句，不然看着像坏了 ——
      // 也提醒一句：锁屏上没有「换个分区」的出口，忘了口令只能靠别的分区重设
      toast(
        hasPassword(partition.id)
          ? `已把「${partition.name}」设为默认分区 · 它上着锁，启动时先要口令`
          : `已把「${partition.name}」设为默认分区`,
      );
    });

    // 展开了才建那两个 seg：一个分区两个、默认都是关，建了也是常年不动的死控件
    let built = false;
    auto.addEventListener("click", () => {
      if (!built) {
        more.append(
          subRow("自动归档", archiveControl(partition)),
          subRow("空闲锁定", idleLockControl(partition)),
        );
        built = true;
      }
      more.hidden = !more.hidden;
      auto.textContent = more.hidden ? "自动 ▾" : "自动 ▴";
    });

    const rename = el("button", { class: "btn sm", type: "button", text: "改名" });
    rename.addEventListener("click", () => {
      void promptText({
        title: `重命名「${partition.name}」`,
        placeholder: partition.name,
        confirmText: "保存",
      }).then((name) => {
        if (name === null || !name.trim()) return;
        renamePartition(partition.id, name.trim());
        toast(`已改名为「${name.trim()}」`);
      });
    });

    del.addEventListener("click", () => void dropPartition(partition));

    unsubs.push(onDataChange(paint), onLockChange(paint));
    paint();

    return [
      el("div", { class: "set-row" }, [
        // 条数与锁跟着名字：一眼看出这个区里有多少、上没上锁。
        // 摆右边会和那四个按钮抢位置 —— 抽屉只有 420px，挤到最后是谁都放不下
        el("span", { class: "rowctl" }, [
          dot,
          el("span", { class: "part-name", text: partition.name }),
          count,
          lock,
        ]),
        el("span", { class: "rowctl" }, [auto, pass, rename, del]),
      ]),
      more,
    ];
  };

  const paint = (): void => {
    while (unsubs.length > 0) unsubs.pop()?.();
    box.replaceChildren(
      el("div", { class: "set-sec-t", text: "分区" }),
      ...PARTITIONS.flatMap(rowOf),
      el("div", { class: "set-row" }, [add]),
    );
  };

  onPartitionListChange(paint);
  paint();
  return box;
}

/**
 * 开机自启动。
 *
 * 真实值要问系统（异步），所以先渲染成「关」，拿到再翻过来 —— 设置面板是同步
 * 渲染的，不能等一个 Promise。浏览器预览里问不到（`autostartEnabled` 返回 null），
 * 那一行就标成不可用：与其摆一个点了没反应的开关，不如直接说这个环境没有。
 */
function autostartControl(): HTMLElement {
  const toggle = el("span", {
    class: "sw",
    role: "switch",
    tabindex: "0",
    title: "开机后自动启动 Tadado2",
  });

  const flip = (): void => {
    const next = !toggle.classList.contains("on");
    void setAutostart(next).then((ok) => {
      if (!ok) {
        toast("当前环境改不了开机自启动");
        return;
      }
      toggle.classList.toggle("on", next);
      toggle.setAttribute("aria-checked", String(next));
      toast(next ? "已设为开机自动启动" : "已取消开机自动启动");
    });
  };

  toggle.addEventListener("click", flip);
  toggle.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      flip();
    }
  });

  void autostartEnabled().then((on) => {
    if (on === null) {
      toggle.classList.add("disabled");
      toggle.removeAttribute("tabindex");
      toggle.title = "当前环境不支持（浏览器预览里没有系统集成）";
      return;
    }
    toggle.classList.toggle("on", on);
    toggle.setAttribute("aria-checked", String(on));
  });

  return toggle;
}

// 分区自己管渲染（能增删，静态行不够用），插在「启动」和「关于」之间 ——
// 见 mountSettings。
const TOP_GROUPS: SettingGroup[] = [
  {
    title: "外观",
    rows: [{ label: "主题", control: themeControl }],
  },
  {
    // 组名从「窗口」改成「启动」：这一组回答的是「这个进程怎么被叫起来、怎么被
    // 叫出来」—— 开机自启动（进程层面）和全局热键（窗口层面）都在这里
    title: "启动",
    rows: [
      { label: "开机自启动", control: autostartControl },
      // 只读值：这个组合键是 shell/hotkey.ts 里的常量，不是可配项。
      // 摆成能改的样子、改完才发现不生效，比直接把现实摆出来更气人
      //
      // 「窗口置顶」那一行撤了（2026-09-17）：它是标题栏图钉的**第二个入口**，
      // 而图钉就在那儿一键切换 —— 和其他设置项不同，它是「现在就要这个窗口浮
      // 上来」的动作，不是一条需要翻两层菜单去改的偏好
      { label: "全局热键", value: "Ctrl+Shift+Space" },
    ],
  },
];

/**
 * 「关于」的介绍块。
 *
 * 按**实际能做什么**逐条写：对着五个页面和那十几条真做出来的能力列，不写愿景、
 * 不写「基于 XX 框架」—— 用户点开这里想知道的是「它能替我做什么」，技术栈是
 * 开发文档的事。
 *
 * 也不另开一个「关于」对话框：想知道版本和数据在哪的人，本来就会来设置里找，
 * 再套一层只是让这几句话住进一个更大的房间。
 */
function aboutIntro(): HTMLElement {
  const list = (items: string[]): HTMLElement =>
    el("ul", { class: "about-list" }, items.map((text) => el("li", { text })));

  return el("div", { class: "about" }, [
    el("div", { class: "about-name", text: "Tadado2" }),
    el("p", {
      class: "about-lead",
      text: "本地优先的个人任务管理：任务、进展与时间线都留在你自己的机器上。",
    }),

    el("div", { class: "about-h", text: "功能" }),
    list([
      "五个视图：总览、任务、任务图谱、活动分析、任务管理",
      "任务页是甘特时间轴：色条为起止区间、填充为进度，档位从今天到全年",
      "图谱把「任务 × 标签 × 分区」铺成关系网络，悬停高亮、双击直达",
      "活动分析：整年热力图 + 分标签报告，可按当前范围导出 md / txt / xlsx",
      "分区是数据的隔离边界，每个分区可单独设口令、空闲锁定与自动归档",
      "Markdown 方言：一行一条任务（- [ ] 标题 #标签 ⏰09-20 :: 30%），粘贴多行即建",
    ]),

    el("div", { class: "about-h", text: "特色" }),
    list([
      "本地存储：单文件 SQLite，无账号、无云端同步",
      "一屏到底：五个页面都撑满窗口，筛选与翻页不必整页滚动",
      "键盘优先：Ctrl+1–5 切页，Ctrl+Shift+Space 全局唤起",
      "改状态留痕：完成、改进度、改优先级都会写进活动时间线",
    ]),
  ]);
}

const ABOUT: SettingGroup = {
  title: "关于",
  intro: aboutIntro,
  rows: [
    // 版本号启动时由 Tauri 填真实值（见 mountSettings）；这里写的是拿不到时的
    // 兜底（浏览器预览），与 package.json / tauri.conf.json 保持一致
    { label: "版本", value: "v1.0.0", id: "set-ver" },
    { label: "运行环境", value: "Windows 桌面应用" },
  ],
};

function renderRow(row: SettingRow): HTMLElement {
  const control = row.control?.();

  const right =
    control ??
    el("span", {
      class: row.value ? "v mono" : "v mono dim",
      text: row.value ?? PLACEHOLDER,
    });
  if (row.id) right.id = row.id;

  return el("div", { class: "set-row" }, [
    el("span", { text: row.label }),
    control ? right : el("span", { class: "v" }, [right]),
  ]);
}

function renderGroup(group: SettingGroup): HTMLElement {
  return el("div", { class: "set-sec" }, [
    el("div", { class: "set-sec-t", text: group.title }),
    ...(group.intro ? [group.intro()] : []),
    ...group.rows.map(renderRow),
  ]);
}

// ─── 装配 ────────────────────────────────────────────────────────────────────

const drawer = (): HTMLElement => need("#set-drawer");
const body = (): HTMLElement => need("#set-body");

export function openSettings(): void {
  drawer().classList.add("open");
  // 从锁屏上进来的（忘了口令时的唯一出口）：把抽屉抬到锁屏之上，锁并没解
  if (isLockScreenUp()) suppressLockScreen();
  // 右侧只有一块地方：开设置就得把任务抽屉收起来（shell/panels.ts）
  panelOpened("settings");
}

export function closeSettings(): void {
  drawer().classList.remove("open");
  panelClosed("settings");
  // 配对收起让位：期间清了口令 / 重设了当前分区的口令，锁屏就不会再回来
  restoreLockScreen();
}

export const isSettingsOpen = (): boolean => drawer().classList.contains("open");

export function toggleSettings(): void {
  if (isSettingsOpen()) closeSettings();
  else openSettings();
}

export function mountSettings(): void {
  body().replaceChildren(
    ...TOP_GROUPS.map(renderGroup),
    partitionSection(),
    renderGroup(ABOUT),
  );

  // 版本号等 Tauri 回话再写进去（标题栏那个徽章撤了，这里是唯一一处）。
  // 浏览器预览 / 拿不到就保留 ABOUT 里写死的那个，不为版本号卡住外壳
  void getVersion()
    .then((version) => {
      const node = document.getElementById("set-ver");
      // 前面的 v 是给版本号看的：这一行念作「版本 v1.0.0」，
      // 而 Tauri 回话给的是纯数字
      if (node) node.textContent = `v${version}`;
    })
    .catch(() => {});

  need("#set-close").addEventListener("click", closeSettings);
  need("#set-btn").addEventListener("click", toggleSettings);
  registerPanel("settings", closeSettings);
  // 锁屏上那个「设置」按钮走这里（它不能直接 import 本模块：本模块依赖 lock）
  registerOpen("settings", openSettings);

  // 切到别的模块就收起，和「编辑任务」抽屉一致：设置讲的是外壳与分区，翻页后
  // 还挂在这儿，看上去就像新页面里长出来的一层，也说不清它属于谁
  subscribePages(() => {
    if (isSettingsOpen()) closeSettings();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && isSettingsOpen()) closeSettings();
  });
}
