# Tadado2（Tauri 桌面端）

Tauri（Rust + WebView2 + TypeScript）实现，版本从 **v1.0.0** 起。

当前状态：**外壳与五个页面的交互都已就位**，数据落在本地 SQLite
（版本与迁移见「数据层」一节；样例数据全部在演示空间）。

## 设计来源（改动前必读）

颜色和几何有两个权威源，不要在这里自由发挥：

| 内容 | 权威源 |
|------|--------|
| 语义色、字体栈 | `src/utils/design_tokens.py`（已随 Python 版归档到 **`archive/pyversion`** 分支，改色值时对着它改：`git show archive/pyversion:src/utils/design_tokens.py`） |
| 圆角、控件尺寸、阴影、动效曲线 | [`resources/ui-mockup/tadado-2.0.html`](../resources/ui-mockup/tadado-2.0.html) |
| 窗口形态、导航骨架 | [DESIGN.md](../DESIGN.md) 2.12 / 1.3.1 |

`src/styles/tokens.css` 只做一件事：把上面两者翻译成 CSS 变量。**不要新增颜色**。

## 结构

```
index.html              应用骨架：标题栏 + rail + 主区 + 设置抽屉
src/main.ts             入口，只负责按顺序调用各模块的 mount
src/styles/
  tokens.css            CSS 变量（语义色 / 几何 / 字体 / 热力图色阶）
  base.css              reset、滚动条、焦点环、提示条
  shell.css             标题栏、rail、主区、页面骨架、抽屉
  controls.css          按钮 / 胶囊 / 分段 / 输入 / 下拉 / 卡片 / 开关 / 确认浮层
src/shell/              外壳能力
  theme.ts              light / dark / sys，localStorage 持久化
  window.ts             窗口状态（置顶 / 最大化 / 显隐），标题栏按钮专用
  titlebar.ts           标题栏装配
  nav.ts                rail 渲染 + 页面切换 + Ctrl+1..5
  partition.ts          分区切换（rail 底部）
  settings.ts           设置面板
  tray.ts / hotkey.ts   托盘、全局热键
  toast.ts / dom.ts     提示条、DOM 助手
  confirm.ts            破坏性操作的二次确认浮层（Promise，默认焦点给「取消」）
src/data/               数据层，见「数据层」一节
  mock.ts               28 条硬编码演示任务 —— 接真实数据后整个文件删掉
  store.ts              变更广播（dataChanged / onDataChange），替换写路径的落点
  types.ts / timeline.ts 领域类型与时间窗口算数
src/pages/registry.ts   视图注册表：页面 / 分组 / 图标 / 骨架区块
src/pages/*.ts          五个页面 + 任务抽屉 + 跨页跳转
```

新增页面只需往 `src/pages/registry.ts` 追加一条 —— rail 按钮、页面 section、
`Ctrl+N` 快捷键会一起出现。

## 已接通 / 仍是骨架

**外壳**已能真实工作：

- 页面切换（rail + `Ctrl+1..5`）、rail 按钮、分区弹层
- 主题切换（亮 / 暗 / 跟随系统），首帧不闪白
- 窗口置顶（浮在其他应用之上）、最小化、最大化 / 还原、双击标题栏最大化
- 标题栏拖拽（`data-tauri-drag-region="deep"`）、系统边缘缩放与 Aero Snap
- 托盘常驻（左键切换显隐）、全局热键 `Ctrl+Shift+Space`
- 分区口令与空闲锁定（`shell/lock.ts`）：口令按分区设，切过去挡一层锁屏，空闲若干分钟无输入自动重锁。它是**隐私屏风不是加密保险箱** —— 挡的是路过的人瞄一眼，不防拿到数据文件的人，所以忘了口令没有找回入口
- Markdown 源实时预览（抽屉底部）：敲 md 就地渲染成标题 / 标签 / 截止 / 进度，点「按 md 更新任务」才写回；状态不进 md、起点不在方言里，所以这两样写回时不被动
- 草稿（`shell/draft.ts`）：快速新建与批量框里没提交的字跟着 kv 走，重开也还在，页面上有草稿条说明「字还在那儿」；提交成功即清

**五个页面的交互逻辑**已经写完了（不再是占位卡），但跑在演示数据上：总览的今日
速览与热力图、任务页的甘特时间轴与增删改、图谱页的力导向布局、活动分析页的热力图
与时间轴报表、管理页的批量操作与标签改名合并（改名成已存在的标签即视为合并）。

**一屏到底**：主区不滚（`shell.css` 的 `.main` / `.page` / `.page-body` 逐层撑满），
每页固定的块留在原地、会长的那块（表格 / 列表）在卡片内部吃掉剩余高度并在那里滚 ——
五个页面都不再需要整页滚。总览下半页因此分成两列（左：焦点时间轴 + 优先级分布，
右：活动流），否则常见窗口高度下近期活动只剩三行。每页条数仍是分页器上那个档位
（`pages/shared.ts` 的 `PAGE_SIZES`，不进设置）。

除外壳之外的仍是骨架，主要是数据层（下面「数据层」一节）：

- 导出是真的写文件：管理页与活动分析页各一个「导出 ▾」，三种格式（md / txt / xlsx）共用 `data/export.ts`。md 与 txt 内容一致（与 python 版同一份排版），xlsx 由 `data/xlsx.ts` 现场生成（不依赖第三方库）。任务管理没有导入 —— 方言带不回状态，批量新建框吃同一套方言、当场看得见解析出几条

## 数据层

业务数据当前**全是假的**。动这三个地方之前先看清楚各自的约定：

**演示数据与分区**：样例数据只有一份，全部落在**演示空间**（100 条 = 28 条原型手写 +
72 条压测生成），启动就进这个分区；其他分区留给用户自己建，初始为空。老库里散在
各分区的种子由 `store.ts` 的 `adoptSeedPartitions` 在启动时搬回演示空间 —— 只动
种子 id，用户自己建的任务一条都不碰。

**存储版本与迁移**（`data/schema.ts`）：表结构变化走 `PRAGMA user_version` +
`MIGRATIONS` 线性链 —— 照搬归档分支上 PySide6 版的 `src/models/migrations.py`
（那边跑到 8，配套文档在 `docs/database-migration-technique.md`），规矩也照搬：
只加不改、只 `ALTER TABLE ADD COLUMN`。
`setVersion` 写完会**在同一条连接上读回核对**：PRAGMA 万一被忽略是静默的，而机制
静默退化（每次启动重跑一遍迁移）要等很久以后才会暴露。
浏览器预览没有 SQLite，版本号落在 localStorage 的一个 key 上，但**迁移链是同一条**，
所以 e2e 能真的验一遍。
表结构之外还有一层：业务字段整条存在 `tasks.data` 里，版本号管不到列里面 ——
读入口的 `normalizeTasks` 负责给缺字段补默认、把旧格式（活动时刻的展示串）换成新
格式，救不回来的丢掉并计数（控制台有记录，不静默）。
**读不出来时不再静默降级**：以前 `db.ts` 的 catch 把「库打不开」和「没有宿主」当成
同一件事，一律退回 localStorage —— 用户的库静静地不被读取、此后写入还落到别处；
现在先用 `isTauri()` 分环境，库故障是终态（`backend = "error"`），既不降级也不写入，
由外壳给一句提示。

| 文件 | 现状 | 接真实数据时要做的事 |
|------|------|--------------------|
| `mock.ts` | 演示空间的 100 条（28 条原型手写 + 72 条压测生成，其中 1 条已归档） | 整个删掉（文件头写着这个约定） |
| `store.ts` | 内存广播 `dataChanged` / `onDataChange` | 把写路径换成 Tauri 命令 + 事件订阅 |
| `pages/shared.ts` 的 `DEMO_TODAY` | 整个时序锚在一个固定的「演示今天」上，好让演示数据永远看得出相对关系 | 换成真实当天 |

这套安排有一个必须先讲的后果：**Markdown 往返不保留状态**。这是设计规范而不是
bug —— `DESIGN.md` 明确「状态关键字不在 Markdown 中体现」，`raw_md` 只承载优先级 /
日期 / 标题 / 标签，状态在数据库列里。所以导出 md 再导回来，所有完成任务都会变回待办。
桌面端决定怎么存的时候要先接受（或改写）这条。

至于「怎么接」还没有结论：走 Tauri 命令、前端直连 `sql` 插件、还是复用 Python 侧的
CLI / 命名管道 —— 三种都能落地，差别在于要不要再来一份重复的查询逻辑。

## 开发

```bash
npm install
npm run dev            # 纯前端预览（非 Tauri 环境自动降级，只能调样式）
npm run build          # tsc + vite build，产物在 dist/
npm run tauri dev      # 真实窗口（首次需编译 Rust，约 1–2 分钟）
```

`npm run dev` 下 `@tauri-apps/api` 的窗口调用会走本地状态降级，页面与样式都能看，
只有窗口行为（置顶、托盘、热键）不可用。

```bash
npm run e2e             # 真浏览器冒烟（自起预览服务器，约 20s）
```

`npm run e2e` 会真开一个 Chromium 点一遍：开抽屉、改标题、md 源预览与写回、草稿条、
右键菜单、新建、批量新建、切分区、活动报告搜索、分区口令与锁屏，最后还要
「没有 console 报错」。它存在的理由是 `tsc` 看不出运行时故障 ——
曾经 `dropdown.setValue` 回调 onPick 造成无限递归，抽屉建出来了却永远打不开，
类型完全合法、构建照过，只有真点一遍才暴露。

CI（`.github/workflows/desktop.yml`）跑的就是 `npm run build` + `npm run e2e`。

还没有 lint / format script（CI 已覆盖类型检查、构建与冒烟）。改完样式记得
对着 `resources/ui-mockup/tadado-2.0.html` 核一遍视觉差异 —— 那部分自动化还做不到。

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

归档分支上完整保留了：2.0 阶段 2~7 的全部在制品、当时那 106 项未提交改动，以及几个
被 gitignore 但不可再生的资产（`resources/tadado.data` / `config.json` / `pack_scripts/` /
`Tadado.spec` / `RELEASE.md`） —— 这些是真删了就再也拿不回来的，所以特意
 `git add -f` 强塞进了归档提交。

语义色权威源 `design_tokens.py` 现在只在归档分支上（见「设计来源」表）。桌面端的数据
层一旦接通（见「数据层」），色值就该在这里落一份，别总回头去抄 Python 版。
