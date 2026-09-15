# Tadado Desktop（Tauri 外壳）

Tadado 2.0 界面的 Tauri（Rust + WebView2 + TypeScript）重写。目标是把界面从
PySide6 + QSS 迁到 Web 技术栈，**去掉「用 QSS 把 Fusion 掰成 Web 样」这层阻抗**。

当前状态：**外壳已就位，业务未接入**。

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
  window.ts             窗口状态（置顶 / 最大化 / 显隐），标题栏与设置共享
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
- 常驻置顶、最小化、最大化 / 还原、双击标题栏最大化
- 标题栏拖拽（`data-tauri-drag-region="deep"`）、系统边缘缩放与 Aero Snap
- 托盘常驻（左键切换显隐）、全局热键 `Ctrl+Shift+Space`

**五个页面的交互逻辑**已经写完了（不再是占位卡），但跑在演示数据上：总览的今日
速览与热力图、任务页的甘特时间轴与增删改、图谱页的力导向布局、活动分析页的热力图
与时间轴报表、管理页的批量操作与标签改名合并（改名成已存在的标签即视为合并）。

仍是骨架：

- 设置面板：只有主题 / 常驻置顶 / 时间轴粒度三项真的生效，其余条目显示为 `—`
- 写死的演示口径活动分析页「导出」按钮目前只弹 toast「（演示）」，没有真的写文件

## 数据层

业务数据当前**全是假的**。动这三个地方之前先看清楚各自的约定：

| 文件 | 现状 | 接真实数据时要做的事 |
|------|------|--------------------|
| `mock.ts` | 28 条硬编码任务 | 整个删掉（文件头写着这个约定） |
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

还没有 lint / format / test：`npm run build` 里的 `tsc` 是唯一一道检查，`package.json`
里没有对应 script，`desktop/` 也不在 CI 覆盖范围内。加自动化测试之前，改完记得对着
`resources/ui-mockup/tadado-2.0.html` 手动核一遍视觉差异。

## 窗口形态

- 无边框（`decorations: false`）+ 自绘标题栏，`resizable: true` 以保留系统缩放热区
- 不透明（`transparent: false`）：页面有实底，透明窗口没有收益且合成更贵
- 默认 1180×760，最小 1050×680
- `alwaysOnTop` 关闭启动，由置顶按钮 / 设置开关控制
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
