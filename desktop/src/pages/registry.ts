// ─────────────────────────────────────────────────────────────────────────────
// 视图注册表：导航层需要知道的全部页面信息。
//
// 对应 DESIGN.md 1.3.1「导航骨架」：NavShell 按注册表渲染 rail 入口，
// Ctrl+1..5 的序号就是数组顺序。新增页面只需在这里追加一条 —— rail 按钮、
// 页面容器、快捷键会一起出现，然后在 pages/index.ts 里把实现接上。
//
// 这里**只描述导航**，不描述页面内容。曾经每个页面还带着一份 blocks 区块清单
// （标题 + 占位说明 + 高度），那是外壳阶段用来撑骨架的；页面接了真实数据之后，
// 那份清单就成了一份永远追不上实现的过期文档，已删除。
//
// 同理删掉了 group（工作 / 洞察 / 管理）：它只服务于 rail 上的分组文字，
// 那行文字已经撤掉，留着这个字段就是一份没人读的分类表。
// ─────────────────────────────────────────────────────────────────────────────

export type PageId = "overview" | "tasks" | "graph" | "activity" | "manage";

export interface PageSpec {
  id: PageId;
  /** rail 上的 tooltip 与可访问名。 */
  label: string;
  /** rail 按钮图标（内联 SVG）。 */
  icon: string;
  /** 页头大标题。 */
  title: string;
  /** 页头说明。 */
  desc: string;
  /** 页头右侧主按钮文案，缺省则不渲染。 */
  action?: string;
}

const railIcon = (paths: string, strokeWidth = 1.7): string =>
  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="${strokeWidth}" stroke-linecap="round" stroke-linejoin="round">${paths}</svg>`;

export const PAGES: PageSpec[] = [
  {
    id: "overview",
    label: "总览",
    // 房子。「四格方块」是通用的「应用 / 更多」图形，放在第一位谁都认不出
    // 它是首页；房子是唯一没有第二种读法的形状，代价是画得稍微满一点。
    icon: railIcon(
      '<path d="M3.8 9.6L12 3.4l8.2 6.2V19a1.8 1.8 0 0 1-1.8 1.8H5.6A1.8 1.8 0 0 1 3.8 19z"/><path d="M9.6 20.8v-6.4h4.8v6.4"/>',
    ),
    title: "总览",
    desc: "今日指标 · 焦点时间轴 · 近期活动 · 优先级分布",
  },
  {
    id: "tasks",
    label: "任务",
    icon: railIcon('<circle cx="12" cy="12" r="8.5"/><path d="M8.5 12.2l2.4 2.4 4.6-5"/>'),
    title: "任务",
    // 新建入口回到页头。工具行原来那个「快速新建」只能填名称和标签，
    // 建出来的是「待办 + 普通 + 无起止」的半成品，必须再开抽屉补一遍；
    // 页头这个开的是与编辑同一套的完整表单，所以它是唯一入口。
    action: "＋ 新建任务",
    desc: "页头新建 · 单击选中 · 双击打开维护抽屉 · 右键处置",
  },
  {
    id: "graph",
    label: "任务图谱",
    // 一个中心节点连三条辐条。原来那版是三颗大小不一的散点 + 两根短线，
    // 19px 下就是几个噪点，连不成「关系」；辐射状至少有个能一眼看懂的中心。
    icon: railIcon(
      '<circle cx="12" cy="12" r="2.5"/><circle cx="12" cy="4.4" r="1.9"/><circle cx="5.8" cy="16.8" r="1.9"/><circle cx="18.2" cy="16.8" r="1.9"/><path d="M12 9.5V6.3M10.02 13.53L7.3 15.64M13.98 13.53l2.72 2.11"/>',
    ),
    title: "任务图谱",
    desc: "任务 × 标签 × 分区的关系网络 · 悬停高亮 · 双击直达任务",
  },
  {
    id: "activity",
    label: "活动分析",
    icon: railIcon('<path d="M5 20v-7M12 20V6M19 20v-9"/>', 2),
    title: "活动分析",
    desc: "热力图 + 分标签活动报告 · 点击日期查看当天活动",
  },
  {
    id: "manage",
    label: "任务管理",
    // 勾选清单：一只打过勾的方框 + 一条待办线。原来那个「大格子 + 十字线」
    // 缩到 19px 更像一扇带窗格的窗户，读不出「逐条处置」这层意思。
    icon: railIcon(
      '<rect x="3.6" y="4.4" width="5.6" height="5.6" rx="1.5"/><path d="M5 7.3l1.5 1.5 2.4-2.9"/><rect x="3.6" y="14" width="5.6" height="5.6" rx="1.5"/><path d="M12 7.2h8.4M12 16.8h8.4"/>',
    ),
    title: "任务管理",
    desc: "批量审视与处置 · 行点击打开任务 · 标签改名与合并",
  },
];

export const pageById = (id: string): PageSpec | undefined =>
  PAGES.find((page) => page.id === id);
