# Tadado2（Tauri 桌面端）

Tauri（Rust + WebView2 + TypeScript）实现，版本从 **v1.0.0** 起。

当前状态：**外壳与五个页面的交互都已就位**，数据落在本地 SQLite
（版本与迁移见「数据层」一节；样例数据全部在演示空间）。

> 本文档讲的是**结构、现状与怎么开发**；「为什么这么设计」在仓库根的 [DESIGN.md](../DESIGN.md)
> （v1.x 的设计文档，与 README 同级）。**Py 版**（v0.x）的设计随代码在 `archive/pyversion` 分支上。

## 设计来源（改动前必读）

颜色和几何有两个权威源，不要在这里自由发挥：

| 内容 | 权威源 |
|------|--------|
| 语义色、字体栈 | `src/utils/design_tokens.py`（已随 Python 版归档到 **`archive/pyversion`** 分支，改色值时对着它改：`git show archive/pyversion:src/utils/design_tokens.py`） |
| 圆角、控件尺寸、阴影、动效曲线 | [`resources/ui-mockup/tadado-2.0.html`](../resources/ui-mockup/tadado-2.0.html) |
| 窗口形态、导航骨架 | **Py 版**设计文档（`archive/pyversion:DESIGN.md`）的 2.12 / 1.3.1 |

`src/styles/tokens.css` 只做一件事：把上面两者翻译成 CSS 变量。**不要新增颜色**。

## 结构

```
index.html              应用骨架：标题栏 + rail + 主区 + 设置抽屉
src/main.ts             入口，只负责按顺序调用各模块的 mount
src/styles/             五层，依赖方向单向（见 DESIGN.md §2.2）
  tokens.css            CSS 变量（语义色 / 几何 / 字体 / 热力图色阶）—— **唯一**的翻译层
  base.css              reset、滚动条、焦点环、提示条
  shell.css             标题栏、rail、主区、页面骨架、抽屉
  controls.css          按钮 / 胶囊 / 分段 / 输入 / 下拉 / 卡片 / 开关 / 确认浮层 / 分段控件
  pages.css             五个页面 + 维护抽屉各自的排版
src/shell/              外壳能力（23 个模块，常打交道的几个）
  theme.ts              light / dark / sys，localStorage 持久化
  window.ts             窗口状态（置顶 / 最大化 / 显隐），标题栏按钮专用
  titlebar.ts           标题栏装配
  nav.ts                rail 渲染 + 页面切换 + Ctrl+1..5
  router.ts / panels.ts 页面注册与浮层开合（设置面板从锁屏也能打开，见 §5.3）
  lock.ts               分区口令与空闲锁定（隐私屏风，不是加密保险箱）
  partition.ts          分区切换（rail 底部）
  settings.ts           设置面板
  trayBridge.ts         托盘事件（Rust 叫前端）；托盘 / 热键另见 hotkey.ts、autostart.ts
  menu.ts / seg.ts      下拉与分段控件（无状态，所以外部改数据后必须 setValue 回写）
  toast.ts / dom.ts     提示条、DOM 助手
  confirm.ts / prompt.ts 二次确认浮层（Promise，默认焦点给「取消」）、单行输入浮层
  rollover.ts           跨日重载（TODAY 是常量，跨日只能整页重来）
src/data/               数据层，见「数据层」一节（12 个模块）
  db.ts                 SQLite 连接与「读不出来不降级」
  schema.ts             PRAGMA user_version + 线性迁移链
  store.ts              变更广播（dataChanged / onDataChange）+ 启动装配
  markdown.ts           任务行写法：parseTasks（入）/ taskToMarkdown（出）
  time.ts               时间口径：TODAY / nowStamp / 天数与分钟互转（**日期一律走这里**）
  timeline.ts           时间轴档位与窗口算数（**只剩总览的焦点时间轴在用**）；partitions.ts / tags.ts 领域规则
  export.ts / xlsx.ts   三种导出格式；xlsx 自写 zip
  mock.ts               演示空间的 100 条种子（28 条手写 + 72 条确定性生成）
  types.ts              领域类型
src/pages/registry.ts   视图注册表：页面 / 分组 / 图标 / 骨架区块（导航要知道的）
src/pages/index.ts      页面实现表：PageId → 实现（只有外壳要知道的；分开是为了不绕成环）
src/pages/*.ts          五个页面 + 维护抽屉（taskDrawer / taskForm）+ 公共件
                        （shared 谓词与常量、pager 分页器、focus 跨页请求）
```

新增页面只需往 `src/pages/registry.ts` 追加一条 —— rail 按钮、页面 section、
`Ctrl+N` 快捷键会一起出现。

## 完成度：功能都已接通，唯一「假」的是种子数据

外壳（标题栏 / rail / 主题 / 窗口 / 托盘 / 热键 / 自启 / 锁屏 / 浮层）、五个页面、维护抽屉、
数据层（SQLite + 迁移 + 读入口归位 + 故障不降级）、导入导出都是**真的**，不是占位卡。
启动时看到的那 100 条任务才是「假」的 —— 它们是演示空间的种子（见下面「数据层」）。

**外壳**已能真实工作：

- 页面切换（rail + `Ctrl+1..5`）、rail 按钮、分区弹层
- 主题切换（亮 / 暗 / 跟随系统），首帧不闪白
- 窗口置顶（浮在其他应用之上）、最小化、最大化 / 还原、双击标题栏最大化
- 标题栏拖拽（`data-tauri-drag-region="deep"`）、系统边缘缩放与 Aero Snap
- 托盘常驻（左键切换显隐）、全局热键 `Ctrl+Shift+Space`、开机自启（设置里可关）
- 分区口令与空闲锁定（`shell/lock.ts`）：口令按分区设，切过去挡一层锁屏，空闲若干分钟无输入自动重锁。它是**隐私屏风不是加密保险箱** —— 挡的是路过的人瞄一眼，不防拿到数据文件的人，所以忘了口令没有找回入口
- 跨日：`TODAY` 是一个常量，跨过本地零点由 `shell/rollover.ts` 整页重载（见 DESIGN.md §5.4）
- Markdown 源实时预览（抽屉里）：敲 md 就地渲染成标题 / 标签 / 截止 / 进度，点「按 md 更新任务」才写回；这条写回路径**不采纳状态**（`[x]` 在这个框里不生效）、起点也不在写法里，所以这两样保持原值
- 数据迁入（任务管理页，`pages/tasks.ts` 的 `openImportDialog`）：选一个 md 文件解析成任务，认不出的行与同名任务都逐条列出来等你决定。任务页的「批量新建」吃**同一套写法**、但走粘贴框 —— 那边当场就看得见解析出几条
  （「方言」这个词已废弃：它把「任务行写法」说成一种需要翻译的东西，实际它就是本应用的写法本身）
- 导出：管理页与活动分析页各一个「导出 ▾」，三种格式（md / txt / xlsx）共用 `data/export.ts`。md 与 txt 内容一致（与 Py 版同一份排版），xlsx 由 `data/xlsx.ts` 现场生成（不依赖第三方库）。任务管理没有导入**那种清单** —— 导出的是给人看的清单，本来就回不来

**五个页面**（各自的行为口径见 DESIGN.md §4）：总览的五张指标卡（含「已归档」）+ 焦点时间轴 + 近期活动、
任务页的甘特时间轴（固定 32 天窗口 + 拖动平移；工具行那排档位 2026-09-21 撤了）、图谱页的力导向布局、
活动分析页的热力图与分标签报表、管理页的批量操作与标签改名合并（改名成已存在的标签即视为合并），
「归档」那一列只摆标（已归档 / —，与「状态」「标签」同性质）；动手的地方是页头「导出」旁边那枚
**按当前筛选批量归档 / 取消归档**的按钮（筛选已经说清是哪一批，所以它不要求先勾选），单条处置
走「勾一行 + 批量栏」。

**一屏到底**：主区不滚（`shell.css` 的 `.main` / `.page` / `.page-body` 逐层撑满），
每页固定的块留在原地、会长的那块（表格 / 列表）在卡片内部吃掉剩余高度并在那里滚 ——
五个页面都不再需要整页滚。总览下半页因此分成两列（左：焦点时间轴 + 优先级分布，
右：近期活动），否则常见窗口高度下近期活动只剩三行。每页条数仍是分页器上那个档位
（`pages/shared.ts` 的 `PAGE_SIZES`，不进设置）；「上限」是另一件事，见 DESIGN.md §4.7。

## 数据层

数据**是真的**：业务数据落在本地 SQLite（`tauri-plugin-sql`，库文件
`%APPDATA%\com.tadado.app\tadado.data`），由 `db.ts` 读写、`schema.ts` 管版本。
唯一「假」的是**种子**：演示空间那 100 条（`mock.ts`），首次启动写进库，之后以库为准。

**演示数据与分区**：样例数据只有一份，全部落在**演示空间**（100 条 = 28 条原型手写 +
72 条压测生成，其中 1 条在种子里就写着已归档）。注意另有**一批是已完成**的：默认
「完成后归档＝立即」（见 DESIGN.md §4.10）会在启动时把它们一并收进归档 —— 所以在任务页
看到的条数明显少于 99，那是设计使然，不是数据少了。启动就进这个分区；其他分区留给用户
自己建，初始为空。
老库里散在各分区的种子由 `store.ts` 的 `adoptSeedPartitions` 在启动时搬回演示空间 ——
只动种子 id，用户自己建的任务一条都不碰。

**存储层（`data/db.ts`）**：

- 桌面端走 SQLite（`sqlite:tadado.data`）；浏览器预览降级到 localStorage，但**迁移链是同一条**，
  所以 e2e 能真的验一遍。
- **读不出来时不静默降级**：以前 `db.ts` 的 catch 把「库打不开」和「没有宿主」当成同一件事，
  一律退回 localStorage —— 用户的库静静地不被读取、此后写入还落到别处；现在先用 `isTauri()`
  分环境，库故障是终态（`backend = "error"`），既不降级也不写入，由外壳给一句提示。
- 写入有 400ms 防抖；库故障或读失败之后**一律不写** —— 那份存档要原样留着，人还能去捞。

**版本与迁移（`data/schema.ts`）**：表结构变化走 `PRAGMA user_version` + `MIGRATIONS` 线性链
—— 照搬归档分支上 PySide6 版的 `src/models/migrations.py`（那边跑到 8，配套文档在
`docs/database-migration-technique.md`），规矩也照搬：只加不改、只 `ALTER TABLE ADD COLUMN`。
`setVersion` 写完会**在同一条连接上读回核对**：PRAGMA 万一被忽略是静默的，而机制静默退化
（每次启动重跑一遍迁移）要等很久以后才会暴露。
表结构之外还有一层：业务字段整条存在 `tasks.data` 里，版本号管不到列里面 —— 读入口的
`normalizeTasks` 负责给缺字段补默认、把旧格式（活动时刻的展示串）换成新格式，救不回来的
丢掉并计数（控制台有记录，不静默）。

**时间口径（`data/time.ts`）**：`TODAY` 是**本地日历日**的 anchor，时间戳的 UTC 分量就是
墙上时刻（`stampOf` / `dayOfStamp` / `hhmm` 同一套基准）。「现在」一律用 `nowStamp()`，
**不要**用 `Date.now()` —— 那是真实 UTC 时刻，混用会差一个时区；`Date.now()` 在数据层里
只用来生成 id。`mock.ts` 的 `DEMO_TODAY`（写死 09-12）只是**这批种子**的排布锚点，
界面上显示的「今天」读真实时钟（`TODAY`，跨日由 `shell/rollover.ts` 整页重载）。

⚠️ **上一段是 Py 版（v0.x）的规矩，桌面端已经改写了它**（见 DESIGN §4.8）：这边 `[x]` 是
**读**的 —— 抽屉底部的 md 编辑框与「数据迁入」都靠它带状态。真正不采纳状态的只有抽屉那条
「按 md 更新任务」的写回路径（`mdApply` 只取标题 / 标签 / 进度 / 截止）。
另外**「待办」这一档 2026-09-21 删了**（新建即进行中）：`[ ]` 仍然收，但读进来算「进行中」，
于是往返会把 `[ ]` 写成 `[~]`。

## 开发

```bash
npm install
npm run dev            # 纯前端预览（非 Tauri 环境自动降级，只能调样式）
npm run build          # tsc + vite build，产物在 dist/
npm run e2e            # 构建 + 真浏览器冒烟（唯一的验证闸门，约 2–3 分钟）
npm run tauri dev      # 真实窗口（首次需编译 Rust，约 1–2 分钟）
npm run tauri build    # 出安装包：NSIS + MSI → src-tauri/target/release/bundle/
```

`npm run dev` 下 `@tauri-apps/api` 的窗口调用会走本地状态降级，页面与样式都能看，
只有窗口行为（置顶、托盘、热键）不可用。

`npm run e2e`（`e2e/smoke.mjs`）真开一个 Chromium（1280×860）把主流程点一遍：切页 ·
四张表的翻页与档位一致 · 总览的数字点得开且对得上 · 甘特窗口（固定 32 天 / 拖动平移）·
任务页的搜索排序筛选 · 维护抽屉（md 预览与写回、时间线正序、进度的草稿式
提交与再编辑）· 标签 · 图谱 · 数据迁入与导出 · 口令与锁屏 · 存储版本与读入口归位，
最后一条永远是「**没有 console 报错**」。分组与「判据怎么写」见 DESIGN.md §6.2。

它存在的理由是 `tsc` 看不出运行时故障 —— 曾经 `dropdown.setValue` 的回调 `onPick`
造成无限递归（`paint → setValue → onPick → paint`），抽屉节点建出来了却永远加不上 `.open`，
类型完全合法、构建照过，只有真点一遍才暴露。

**什么时候跑**（2026-09-21 定的）：一轮改动全写完再跑一次，不要每改一处就跑；动手之前先
`npx tsc --noEmit`（几秒）把编译错误挡在前面 —— `npm run e2e` 的第一件事就是
`tsc && vite build`，构建不过会直接停在那里。用户没让跑就不跑。

CI（`.github/workflows/desktop.yml`）在 `desktop/**` **或 `resources/skill/**`** 有改动时跑
`npm ci` → `npm run build` → `npx playwright install --with-deps chromium` → `npm run e2e`。
后者也要监听：冒烟里有一条**真的跑** `resources/skill/tadado-activity-import/scripts/migrate-activity.mjs`，
把它的输出喂进「数据迁入」并断言「共 N 条 · 0 行认不出」—— 那条链的两端分处两个目录，
只盯 `desktop/**` 会漏掉工具那侧。

还没有 lint / format script（CI 已覆盖类型检查、构建与冒烟）。改完样式记得
对着 `resources/ui-mockup/tadado-2.0.html` 核一遍视觉差异 —— 那部分自动化还做不到
（README 里的界面图是 `resources/screenshots.mjs` 对着真实构建拍的，改完界面要重跑一次）。

## 窗口形态

- 无边框（`decorations: false`）+ 自绘标题栏，`resizable: true` 以保留系统缩放热区
- 不透明（`transparent: false`）：页面有实底，透明窗口没有收益且合成更贵
- 默认 1180×760，最小 1050×680
- `alwaysOnTop` 关闭启动，由标题栏的置顶按钮控制
- 关闭按钮 = 收起常驻；真正退出走托盘菜单（`app_exit`）

## 与 Python 版的关系

**2026-09-15 起两支分家**：这一支（`main`）只保留桌面端；PySide6 版连同它自己的
`src/` `tests/` `resources/themes/` `scripts/` `pyproject.toml` 全部归档到
**`archive/pyversion`** 分支，本工作目录里已经没有它。

拿东西回来的两条常用命令：

```bash
git checkout archive/pyversion -- src/ tests/          # 单文件或整目录搬回来
git show archive/pyversion:src/utils/design_tokens.py  # 只看某一文件的旧版内容
```

旧版**数据**走另一条路：v0.x 的活动分析导出清单 → 转换工具
（[`resources/skill/tadado-activity-import/scripts/migrate-activity.mjs`](../resources/skill/tadado-activity-import/scripts/migrate-activity.mjs)）
转成能导入的任务行 → 任务管理页「数据迁入」导入，活动时间线一起过来。用法、对账口径与
导入后的复核步骤见同目录的 [`SKILL.md`](../resources/skill/tadado-activity-import/SKILL.md)。
（工具**住在 skill 里**、不在 `desktop/` 下：那个目录要能**单独拷出去用**，所以自带这份脚本。）

归档分支上完整保留了：2.0 阶段 2~7 的全部在制品、当时那 106 项未提交改动，以及几个
被 gitignore 但不可再生的资产（`resources/tadado.data` / `config.json` / `pack_scripts/` /
`Tadado.spec` / `RELEASE.md`） —— 这些是真删了就再也拿不回来的，所以特意
 `git add -f` 强塞进了归档提交。

语义色权威源 `design_tokens.py` 现在只在归档分支上（见「设计来源」表）。桌面的那份**翻译**
已经落在 `src/styles/tokens.css`（唯一的翻译层，见上）：要改色值，对着归档分支的 Python 那份
核一眼，改完落在这里 —— **不要新增颜色**，也不要让同一份值散到别处去。
