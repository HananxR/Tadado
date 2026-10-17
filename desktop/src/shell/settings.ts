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
import { invoke, isTauri } from "@tauri-apps/api/core";
import { autostartEnabled, setAutostart } from "./autostart";
import { loadSetting, saveSetting } from "../data/db";
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
import {
  ARCHIVE_NEVER,
  ARCHIVE_NOW,
  archiveAfterDays,
  onDataChange,
  setArchiveDays,
} from "../data/store";

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
import {
  ALIYUN_URL,
  RELEASES_URL,
  REPO_URL,
  WECHAT,
  copyText,
  openExternal,
} from "./links";
import { panelClosed, panelOpened, registerOpen, registerPanel } from "./panels";
import { promptText, promptWithExtra } from "./prompt";
import { subscribePages } from "./router";
import { seg } from "./seg";
import { toast } from "./toast";
import { getThemeMode, setThemeMode, type ThemeMode } from "./theme";
import {
  UPDATE_UNSUPPORTED,
  checkForUpdate,
  dateOf,
  installUpdate,
  type UpdateState,
} from "./update";

interface SettingRow {
  label: string;
  /** 只读展示值；缺省显示占位符。 */
  value?: string;
  /** 自定义控件，优先于 value。 */
  control?: () => HTMLElement;
  /** 给只读值 / 整行按钮一个 id，供事后填真实值或 e2e 定位。 */
  id?: string;
  /**
   * 整行就是一个动作（目前只有「帮助文档」）。
   *
   * 它**不参与任何折叠**：帮助是常驻入口，跟着「关于」的展开状态一起消失，等于
   * 把说明书锁在抽屉里。右侧只写一个「打开 ↗」，不做成主按钮 —— 它旁边就是
   * 「检查更新」，两枚主按钮并排会让人以为它们是一组同样的操作。
   */
  action?: { hint: string; run: () => void };
}

interface SettingGroup {
  title: string;
  rows: SettingRow[];
  /** 组标题下的一段自定义内容（目前只有「关于」用得上）。 */
  intro?: () => HTMLElement;
  /** 行下面的一段自定义内容（「关于」的下载渠道与联系方式）。 */
  footer?: () => HTMLElement;
  /**
   * 有值 = 这一组的 intro / footer 可以各自收起，值是**介绍块**记状态的设置键。
   *
   * 只给「关于」用：它的介绍与渠道块压在抽屉最下面、常显只会把上面几组设置挤走，
   * 而「帮助文档 / 检查更新」两行是日常要看的，必须一直露在外面。
   */
  collapsibleKey?: string;
  /** 版本号的 id：有值就把版本写进组标题，形如「关于（v1.0.1）」。 */
  versionId?: string;
  /** 尾部折叠块自己的标题（「下载与反馈」），缺省时随组名。 */
  footerTitle?: string;
  /** 尾部折叠块的状态键：与介绍块**互不联动**。 */
  footerKey?: string;
}

const PLACEHOLDER = "—";

/** 版本号兜底：`getVersion()` 拿不到时（浏览器预览）显示这个。 */
const VERSION_FALLBACK = "v1.0.4";

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

/** 归档档位的短标签（那枚「自动 ▾」的悬浮提示用）。 */
const archiveShort = (days: number): string =>
  days === ARCHIVE_NEVER ? "不归档" : days === ARCHIVE_NOW ? "立即" : `${days} 天`;

/** 归档档位的整句说法（toast 用）：「完成即归档」/「完成后 7 天归档」/「不归档」。 */
const archiveLabel = (days: number): string =>
  days === ARCHIVE_NEVER
    ? "不归档"
    : days === ARCHIVE_NOW
      ? "完成即归档"
      : `完成后 ${days} 天归档`;

/**
 * 完成后归档（**按分区**）：勾完「已完成」之后，过多久把它从任务页收进归档。
 *
 * 档位就是这句话的后半截：**不归档 / 立即 / 7 天 / 30 天 / 90 天**。
 * 以前它叫「自动归档」—— 那个词说不出**什么时候**自动（7/30/90 也是自动），
 * 而第一档叫「关」也错位：它是这条刻度上的 0，不是「这个功能开不开」。
 * 现在左边第一档叫「不归档」（功能显式关掉），「立即」是真正的 0 天。
 */
function archiveControl(partition: Partition): HTMLElement {
  const control = seg(
    [
      { value: String(ARCHIVE_NEVER), label: "不归档" },
      { value: String(ARCHIVE_NOW), label: "立即" },
      { value: "7", label: "7 天" },
      { value: "30", label: "30 天" },
      { value: "90", label: "90 天" },
    ],
    String(archiveAfterDays(partition.id)),
    (value) => {
      control.setValue(value);
      void setArchiveDays(Number(value), partition.id).then(() => {
        toast(`「${partition.name}」${archiveLabel(Number(value))}`);
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
      // 「立即」(-1) 也算**开着** —— 它只是延迟为 0，不代表关掉（只有 ARCHIVE_NEVER 才是关）
      auto.classList.toggle("on", days !== ARCHIVE_NEVER || idle > 0);
      auto.title = `完成后归档 ${archiveShort(days)} · 空闲锁定 ${idle === 0 ? "关" : `${idle} 分钟`}`;
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

    // 展开了才建那两个 seg：一个分区两个、多数人不会天天动，建了也是常年不动的死控件
    let built = false;
    auto.addEventListener("click", () => {
      if (!built) {
        more.append(
          subRow("完成后归档", archiveControl(partition)),
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
 * 按**实际能做什么**逐条写：对着五个页面和那几项真做出来的能力列，不写愿景、
 * 不写「基于 XX 框架」—— 用户点开这里想知道的是「它能替我做什么」，技术栈是
 * 开发文档的事。
 *
 * 两组各三条（2026-10-16 精简）：原来两组共十条，一路读下来像产品说明书，而它
 * 就压在设置抽屉的最下面，没人会当正文读完。砍掉的不是没做（分区口令、Markdown
 * 迁入、图谱双击直达都还在），只是不值得在这个宽度里逐条列。
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
      // 这行原来写「色条为起止区间…档位从今天到全年」：条形 2026-09-20 已改成
      // **创建 → 截止**，档位也从来没有「全年」这一档（是 昨天 / 今天 / 上周 / 本周 /
      // 上月 / 本月 + 全部）。精简时把图谱并进来——两者都是「同一批数据换个形状看」，
      // 拆成两条只是把清单撑长，信息反而更稀
      "任务页是甘特时间轴（条 = 创建 → 截止，颜色只编码状态）；任务图谱把「任务 × 标签 × 分区」铺成关系网络",
      "活动分析：整年热力图 + 分标签报告，可按当前范围导出 md / txt / xlsx",
    ]),

    el("div", { class: "about-h", text: "特色" }),
    list([
      "本地优先：单文件 SQLite，无账号、无云端同步",
      "键盘优先：Ctrl+1–5 切页，Ctrl+Shift+Space 全局唤起",
      "变更留痕：进度与优先级的改动、手写的进展都留在活动时间线",
    ]),
  ]);
}

// ─── 检查更新 ────────────────────────────────────────────────────────────────
//
// 只在点击时联网，不做启动时的静默检查：一个本地优先、无账号的工具，没有任何
// 理由每次启动都偷偷发一个请求出去。版本比较在 Rust 侧（`src/update.rs`），
// 这里只把结果落成一句话。

/** 这一行当前处在哪一步。按钮文字与禁用态都由它推出来。 */
type UpdatePhase =
  | "idle"
  | "checking"
  | "available"
  | "downloading"
  | "installing"
  | "none"
  | "failed"
  | "unsupported";

/**
 * 「检查更新」行右侧：一句状态 + 一枚按钮。
 *
 * **两步**（2026-10-17 定的）：第一次点击只查有没有新版，按钮换成「下载并安装」；
 * 用户再点一次才真的下载。4 MB 虽不大，但「什么时候占带宽、什么时候退出重启」
 * 该由用户决定 —— 检查不该被读成「立即更新」。下载完成后应用会被安装器退出并
 * 自动拉起新版，所以没有「重启」这一步。
 *
 * 结果**内联**在按钮左边，不另开弹窗、也不用底部提示条 —— 提示条 2.2 秒就没了，
 * 而「发现新版本」「下载到哪了」是要留在界面上直到这件事做完的。
 */
function updateControl(): HTMLElement {
  const state = el("span", { class: "about-state", id: "set-upd" });
  const button = el("button", { class: "btn sm", text: "检查更新" });
  let phase: UpdatePhase = "idle";
  let available: Extract<UpdateState, { kind: "available" }> | null = null;

  const paint = (
    next: UpdatePhase,
    text: string,
    label: string,
    tone: "" | "newer" | "done" | "error",
  ): void => {
    phase = next;
    state.className = tone ? `about-state ${tone}` : "about-state";
    state.textContent = text;
    button.textContent = label;
    button.disabled = next === "checking" || next === "downloading" || next === "installing";
  };

  const runCheck = (): void => {
    paint("checking", "正在查询…", "检查中…", "");
    void checkForUpdate()
      .then((result) => {
        if (result.kind === "available") {
          available = result;
          const date = dateOf(result.date);
          paint(
            "available",
            `发现新版本 v${result.version}${date ? ` · ${date}` : ""}`,
            "下载并安装",
            "newer",
          );
          // 同时展开下载渠道：GitHub 下载不通时，那是最近的替代出口
          markNewRelease(result);
          return;
        }

        available = null;
        if (result.kind === "none") {
          // 「已是最新 / 网络不通 / 超时」在结论上是同一件事：这次没查到新版。
          // 用中性色，不套 .error —— 失败不是用户做错了什么。
          paint("none", "已是最新版本", "检查更新", "");
          clearNewRelease();
          return;
        }

        paint("unsupported", UPDATE_UNSUPPORTED, "检查更新", "");
      })
      .catch(() => {
        // 理论上到不了（门面里已经收口）；真冒出来也别把按钮永远钉在「检查中…」
        paint("none", "已是最新版本", "检查更新", "");
      });
  };

  const runInstall = (): void => {
    paint("downloading", "下载中…", "下载中…", "");
    void installUpdate((percent) => {
      if (percent === null) {
        paint("downloading", "下载中…", "下载中…", "");
        return;
      }
      if (percent >= 100) {
        // 下载完就轮到安装器：应用即将退出，重启由安装器负责
        paint("installing", "正在安装 · 应用会自动重启", "安装中…", "");
        return;
      }
      paint("downloading", `下载中 ${percent}%`, "下载中…", "");
    })
      .then(() => {
        // Windows 上通常回不到这里（应用已被安装器接管）；真回来了也别让界面停在「下载中」
        paint("installing", "正在安装 · 应用会自动重启", "安装中…", "");
      })
      .catch(() => {
        // 用户已经表达过更新意图，静默吞掉才是误导。保留展开的渠道，手动下载仍走得通
        paint("failed", "更新失败 · 可手动下载", "重试", "error");
        if (available) markNewRelease(available);
      });
  };

  button.addEventListener("click", () => {
    if (phase === "available") {
      runInstall();
      return;
    }
    if (phase === "downloading" || phase === "installing") return;
    runCheck();
  });

  return el("div", { class: "about-upd" }, [state, button]);
}

/**
 * 发现新版时的动作：展开**下载与反馈**这一行、打上「有新版本」标记，并在渠道块
 * 里补一行「哪一版、什么时候发的」。
 *
 * 只展开下载行（`persist = false`）：这是这次检查的结果，看完就该能收起来；也不去
 * 动「关于」的介绍块 —— 用户点的是检查更新，不是想读产品简介。
 */
function markNewRelease(release: Extract<UpdateState, { kind: "available" }>): void {
  applyDownloadsOpen(true, false);

  document.getElementById("set-new-badge")?.removeAttribute("hidden");
  document.getElementById("about-aliyun")?.classList.add("on");

  const note = document.getElementById("about-note");
  if (!note) return;

  const date = dateOf(release.date);
  const detail = el("button", { class: "about-note-link", text: "查看更新说明 ↗" });
  // 更新说明统一去 Releases 看：`latest.json` 里的 notes 只用于状态行，不在这里铺全文
  detail.addEventListener("click", () => void openLink(RELEASES_URL));
  note.replaceChildren(
    el("span", { text: date ? `${date} 已发布 v${release.version}` : `已发布 v${release.version}` }),
    detail,
  );
}

/** 回到「没有查到」：清掉上一次留下的徽标、日期与渠道高亮，别让它继续骗人。 */
function clearNewRelease(): void {
  document.getElementById("set-new-badge")?.setAttribute("hidden", "");
  document.getElementById("about-note")?.replaceChildren();
  document.getElementById("about-aliyun")?.classList.remove("on");
}

// ─── 下载渠道与联系方式 ──────────────────────────────────────────────────────

/**
 * 「下载与反馈」：下载渠道 + 联系方式。
 *
 * 它有自己的折叠头与状态（默认收起），不跟「关于」的介绍块联动 —— 想知道去哪下载
 * 的人，不该先展开一段产品简介。内容**不随检查结果增减**：检测失败时它仍是用户
 * 唯一的出口，按钮也不忽隐忽现。
 *
 * 渠道顺序按**能不能打开**排，不按官方不官方：阿里云盘在国内可直达，GitHub
 * Releases 经常打不开。链接与公众号都从 shell/links.ts 取，这里不写字面量。
 */
function aboutFooter(): HTMLElement {
  return el("div", { class: "about-foot" }, [
    el("div", { class: "about-h", text: "下载渠道" }),
    el("div", { class: "about-links" }, [
      channelButton("阿里云盘(国内推荐)", ALIYUN_URL, "about-aliyun", "btn primary"),
      channelButton("GitHub Releases", RELEASES_URL, undefined, "btn"),
    ]),
    downloadTip(),
    el("div", { class: "about-note", id: "about-note" }),

    el("div", { class: "about-h", text: "反馈与联系" }),
    el("div", { class: "about-kv" }, [el("span", { text: "微信公众号" }), copyValue(WECHAT)]),
    el("div", { class: "about-kv" }, [
      el("span", { text: "GitHub 仓库" }),
      linkValue("HananxR/Tadado", REPO_URL),
    ]),
    el("p", { class: "about-lic", text: "MIT License © HananxR" }),
  ]);
}

/**
 * 云盘链接的退路：一句话 + 两个行内动作，**不做探测**。
 *
 * 阿里云盘对失效分享同样返回 200，分享页又全靠脚本渲染，客户端拿不到「死没死」
 * 的判据；探测只会多一次联网、一次延迟，还容易误报。所以这里只把后路摆出来：
 * 换 GitHub Releases，或去公众号找作者要新链接。
 */
function downloadTip(): HTMLElement {
  const github = el("button", {
    class: "about-tip-link",
    type: "button",
    id: "about-tip-github",
    "data-url": RELEASES_URL,
    text: "GitHub Releases",
  });
  github.addEventListener("click", () => void openLink(RELEASES_URL));

  const wechat = el("button", {
    class: "about-tip-link",
    type: "button",
    id: "about-tip-wechat",
    title: "点击复制公众号",
    text: WECHAT,
  });
  wechat.addEventListener("click", () => {
    void copyText(WECHAT).then((ok) => {
      toast(ok ? `已复制公众号：${WECHAT}` : "复制失败，请手动记下 Pyvan");
    });
  });

  return el("p", { class: "about-tip", id: "about-tip" }, [
    el("span", { text: "链接失效？换 " }),
    github,
    el("span", { text: "，或公众号 " }),
    wechat,
    el("span", { text: " 留言。" }),
  ]);
}

function channelButton(label: string, url: string, id?: string, className = "btn"): HTMLElement {
  const button = el("button", { class: className, text: label, id, "data-url": url });
  button.addEventListener("click", () => void openLink(url));
  return button;
}

/** 点开外链；交不出去时说一句 —— 点了没反应会被当成按钮坏了。 */
async function openLink(url: string): Promise<void> {
  if (!(await openExternal(url))) toast("打不开链接，请在浏览器里手动打开");
}

/** 可复制的值（公众号）：复制完在行尾闪一下「已复制」，两秒后收回。 */
function copyValue(text: string): HTMLElement {
  const hint = el("span", { class: "about-copied", text: "已复制" });
  const button = el("button", { class: "about-value", title: "点击复制" }, [
    el("span", { text }),
    hint,
  ]);

  button.addEventListener("click", () => {
    void copyText(text).then((ok) => {
      hint.textContent = ok ? "已复制" : "复制失败";
      button.classList.add("copied");
      window.setTimeout(() => button.classList.remove("copied"), 2000);
    });
  });

  return button;
}

/** 可点开的值（仓库地址）。 */
function linkValue(label: string, url: string): HTMLElement {
  const button = el("button", { class: "about-value", text: `${label} ↗`, "data-url": url });
  button.addEventListener("click", () => void openLink(url));
  return button;
}

/** 「关于」介绍块的开关（true = 展开）；记进 kv，重启后保持上次的选择。 */
const KEY_ABOUT_OPEN = "settings.aboutOpen";

/** 「下载与反馈」的开关：**独立记忆**，与介绍块互不影响。 */
const KEY_DOWNLOADS_OPEN = "settings.downloadsOpen";

/** 读回来之前先按默认（收起）渲染 —— 抽屉启动时是关着的，不会看到切换过程。 */
let aboutOpen = false;
let downloadsOpen = false;

/** 折叠头的可见状态：`aria-expanded` + 右侧那两个字（只转箭头不够醒目）。 */
function paintHead(head: HTMLElement | null, open: boolean): void {
  if (!head) return;
  head.setAttribute("aria-expanded", String(open));
  const hint = head.querySelector<HTMLElement>(".set-sec-hint");
  if (hint) hint.textContent = open ? "收起" : "展开";
}

/**
 * 应用「关于」介绍块的折叠状态。
 *
 * 只切 `hidden` 与属性，不重建 DOM：版本号的异步回填、检查更新的状态节点都挂在
 * 同一棵树里，重建会把它们手里的引用全部作废。
 */
function applyAboutOpen(open: boolean, persist: boolean): void {
  aboutOpen = open;
  paintHead(document.getElementById("set-about-head"), open);

  const intro = document.getElementById("set-about-intro");
  if (intro) intro.hidden = !open;

  // 设置不是高频操作，立刻写、不防抖；失败就按默认收起，不必打断交互
  if (persist) void saveSetting(KEY_ABOUT_OPEN, open);
}

/** 应用「下载与反馈」的折叠状态。与「关于」各管各的：查完更新只动这一块。 */
function applyDownloadsOpen(open: boolean, persist: boolean): void {
  downloadsOpen = open;
  paintHead(document.getElementById("set-downloads-head"), open);

  const block = document.getElementById("set-about-downloads");
  if (block) block.hidden = !open;

  if (persist) void saveSetting(KEY_DOWNLOADS_OPEN, open);
}

/**
 * 帮助文档：整行一个动作，**常驻**、不参与任何折叠。
 *
 * 文档（HTML + 截图）嵌在可执行文件里（`src-tauri/src/help.rs`），打开时落盘到
 * 缓存目录再交给默认浏览器 —— 便携版只有一个 exe，也能离线看。
 */
async function openHelp(): Promise<void> {
  if (!isTauri()) {
    toast("请使用桌面版打开帮助文档");
    return;
  }
  try {
    await invoke("open_help");
  } catch {
    toast("打不开帮助文档，请稍后重试");
  }
}

const ABOUT: SettingGroup = {
  title: "关于",
  intro: aboutIntro,
  collapsibleKey: KEY_ABOUT_OPEN,
  // 版本号只留这一处：启动时由 Tauri 填真实值（见 mountSettings），这里写的是拿不到
  // 时的兜底（浏览器预览），与 package.json / tauri.conf.json 保持一致
  versionId: "set-about-ver",
  // 顺序固定：帮助文档 → 检查更新 → 下载与反馈（折叠头）。
  // 帮助是常驻动作，不塞进折叠块；检查更新单独一行 —— 和版本号混在一行里，那个
  // 版本号看着就像个能点的按钮
  rows: [
    {
      label: "帮助文档",
      id: "set-help",
      action: { hint: "打开 ↗", run: () => void openHelp() },
    },
    { label: "检查更新", control: updateControl },
  ],
  footer: aboutFooter,
  footerTitle: "下载与反馈",
  footerKey: KEY_DOWNLOADS_OPEN,
};

function renderRow(row: SettingRow): HTMLElement {
  // 整行动作（帮助文档）：用 button 承载，键盘可达，焦点环沿用全局样式
  if (row.action) {
    const button = el("button", { class: "set-row set-row-link", type: "button" }, [
      el("span", { text: row.label }),
      el("span", { class: "set-hint", text: row.action.hint }),
    ]);
    if (row.id) button.id = row.id;
    button.addEventListener("click", row.action.run);
    return button;
  }

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

/** 一个折叠头：标题 +（可选）附加内容 + 「展开 / 收起」+ 箭头。整行可点。 */
function foldHead(
  id: string,
  controls: string,
  title: HTMLElement,
  extra: HTMLElement[] = [],
): HTMLElement {
  return el(
    "button",
    {
      class: "set-sec-head",
      id,
      type: "button",
      "aria-expanded": "false",
      "aria-controls": controls,
    },
    [
      title,
      ...extra,
      el("span", { class: "set-sec-hint", text: "展开" }),
      el("span", { class: "set-sec-arrow", "aria-hidden": "true", text: "▸" }),
    ],
  );
}

function renderGroup(group: SettingGroup): HTMLElement {
  const collapsible = group.collapsibleKey !== undefined;

  // 可折叠的分组：整行是开关，与下面的 .set-row 同一字号/行高 ——「关于」和它的
  // 几行是平级条目，不是一个小标签。
  const title = el("span", { class: "set-sec-t", text: group.title });
  // 版本号并进组标题：「关于（v1.0.1）」。单独一行「版本」既占地方，又和检查更新
  // 挨在一起，看着像两个都能点的东西
  const version = group.versionId
    ? el("span", {
        class: "set-sec-ver",
        id: group.versionId,
        text: `（${VERSION_FALLBACK}）`,
      })
    : null;

  const head = collapsible
    ? foldHead("set-about-head", "set-about-intro", title, version ? [version] : [])
    : null;

  // 「下载与反馈」自带一个折叠头：它和「关于」介绍块是两件事，共用一个开关时，
  // 想看渠道得先展开一段产品简介
  const downloadsHead =
    collapsible && group.footer
      ? foldHead(
          "set-downloads-head",
          "set-about-downloads",
          el("span", { class: "set-sec-t", text: group.footerTitle ?? group.title }),
          [
            el("span", {
              class: "set-new-badge",
              id: "set-new-badge",
              hidden: true,
              text: "有新版本",
            }),
          ],
        )
      : null;

  // 两个折叠块被若干行隔开，包不进一个 details，所以各自一个容器、各自的开关
  const more = (node: HTMLElement, id: string, key?: string): HTMLElement =>
    el("div", { class: "set-more", id, hidden: true, "data-collapsible": key }, [node]);

  const section = el(
    "div",
    collapsible
      ? { class: "set-sec", "data-collapsible": group.collapsibleKey }
      : { class: "set-sec" },
    [
      head ?? title,
      ...(group.intro
        ? [collapsible ? more(group.intro(), "set-about-intro", group.collapsibleKey) : group.intro()]
        : []),
      ...group.rows.map(renderRow),
      ...(downloadsHead ? [downloadsHead] : []),
      ...(group.footer
        ? [
            collapsible
              ? more(group.footer(), "set-about-downloads", group.footerKey ?? group.collapsibleKey)
              : group.footer(),
          ]
        : []),
    ],
  );

  head?.addEventListener("click", () => applyAboutOpen(!aboutOpen, true));
  downloadsHead?.addEventListener("click", () => applyDownloadsOpen(!downloadsOpen, true));

  return section;
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

  // 两个折叠状态各自读回来：默认都收起，只有明确记着「展开」才打开。
  // 设置抽屉启动时是关着的，这次异步回填不会让人看见闪一下
  void loadSetting<boolean>(KEY_ABOUT_OPEN)
    .then((saved) => {
      if (saved === true) applyAboutOpen(true, false);
    })
    .catch(() => {});
  void loadSetting<boolean>(KEY_DOWNLOADS_OPEN)
    .then((saved) => {
      if (saved === true) applyDownloadsOpen(true, false);
    })
    .catch(() => {});

  // 版本号等 Tauri 回话再写进去（标题栏那个徽章撤了，这里是唯一一处）。
  // 浏览器预览 / 拿不到就保留 ABOUT 里写死的那个，不为版本号卡住外壳
  void getVersion()
    .then((version) => {
      const node = document.getElementById("set-about-ver");
      // 括号与 v 都是给标题看的：念作「关于 v1.0.1」，而 Tauri 回话给的是纯数字
      if (node) node.textContent = `（v${version}）`;
    })
    .catch(() => {});

  need("#set-close").addEventListener("click", closeSettings);
  need("#set-btn").addEventListener("click", toggleSettings);
  // 第三参是「这块面板的根节点」：shell/panels.ts 靠它判断「点在某块面板里还是外」，
  // 点在面板外就收起（2026-10-16 加）。用 getElementById 而不是 need()——那是事件
  // 回调，节点万一没了也不该炸；而 #set-btn 同时也是「打开手势」，所以它在
  // index.html 上打了 data-panel-keep，不会被外部关闭抢先（否则 toggle 会失效：
  // 按下先关、抬起又开）。
  registerPanel("settings", closeSettings, () => document.getElementById("set-drawer"));
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
