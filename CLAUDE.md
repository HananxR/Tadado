# CLAUDE.md

Tadado 项目指导文件。详细设计文档见 [DESIGN.md](DESIGN.md)，更新日志见 [CHANGELOG.md](CHANGELOG.md)。

> **2026-09-15 分支分家**：本工作目录只保留 **Tauri 桌面端**（`desktop/`）。
> PySide6 版（`src/` `tests/` `pyproject.toml` …）已归档到 **`archive/pyversion`** 分支，
> 本分支下已不存在。取回旧代码：`git checkout archive/pyversion -- <路径>`。
> 因此本文件里涉及 Python 工具链（uv / pytest / ruff）的段落只对归档分支有效。

## 项目概览

**Tadado2**（v1.x，`desktop/`）—— Windows 桌面任务管理工具，任务写成 Markdown 一行、
每次推进落在它自己的时间线上。当前主线实现是 **Tauri + TypeScript**（Windows WebView2），
版本自 **v1.0.0** 起；PySide6 版（Tadado，v0.x，最后 v0.2.7）是上一代实现，已归档。
面向用户的功能介绍、安装与升级说明在 [README.md](README.md)。

## 工作流程

### 功能优化 → 文档同步

软件功能优化/新增/修改后，**必须**同步更新以下关联文档，确保与软件实际功能一致、术语使用一致：

| 文件 | 说明 |
|------|------|
| [DESIGN.md](DESIGN.md) | 详细设计说明，记录功能模块需求与实现方案（**权威源**：行为为什么是这样） |
| [CLAUDE.md](CLAUDE.md) | 项目指导文件（本文件），运行时 AI 指令 |
| [desktop/README.md](desktop/README.md) | 桌面端结构、设计权威源、数据层现状（**权威源**：代码在哪、现状是什么） |
| [README.md](README.md) | 面向用户的功能介绍、安装与升级口径（版本号、安装包体积、截图会随发布变） |
| [TODO.md](TODO.md) | 剩余工作与流水，其中「桌面版工作线」一节是主线在追的 |

**提交流程**：文档更新完成后自动执行 `git add` + `git commit`（commit message 以 `docs:` 开头）。

### 验证 → 什么时候跑 e2e

`npm run e2e`（在 `desktop/`）是唯一的验证闸门：它先 `tsc` + `vite build`（构建不过就直接停），
再真开一个 Chromium 把主流程点一遍 —— 一轮**约 2–3 分钟**。所以：

- **攒批跑**：一轮改动全部写完再跑一次。动手之前先 `npx tsc --noEmit`（几秒）把编译错误挡在前面 ——
  否则可能白等两分钟，才发现卡在第一行。
- **由用户发指令再跑**（2026-09-21 定的）：用户没让跑就不跑。之前的做法是每改一小处就全量跑一遍，
  还常常「改 → 跑 → 还原证伪 → 恢复 → 再跑」，一行改动里 90% 的时间都在等测试。
- **证伪只针对可疑的绿**：新写的断言如果有可能「空跑」（前提不成立也照样绿），才单独去证伪一次
  （改坏被测代码，确认它真的会红）；不是每条都要走一遍。
- **红的第一件事是分类**：先看这条失败是「被测行为真的变了」还是「断言自己的前提没设对」
  （时间、分页、当前筛选、焦点窗口都会让断言的前提不成立）。别急着改被测代码。

### version.py 动态修改判定（**仅 `archive/pyversion` 分支**）

> 本分支没有 `src/`，这一节只在归档分支上有效。

[src/version.py](src/version.py) 是公开 API，数据已拆到 [src/_version_data.py](src/_version_data.py)：
- **数据文件** `_version_data.py`：`__version__` 值、`_RELEASE_HIGHLIGHTS` 字典 — 发版时由 `generate_db.bat` 更新
- **逻辑文件** `version.py`：`get_version()`、`parse_version()`、`get_release_highlights()` 等函数 — 不再因发版而被修改

**规则**：
- 仅数据变更（如改版本号、增删 highlights 条目）→ **不自动 commit**，留给发版流程统一提交
- 逻辑变更（如新增/修改函数、调整解析规则）→ 自动 commit

### CHANGELOG.md 更新规则

- **触发条件**：仅在用户明确要求"发版"或"发布新版本"时才更新 CHANGELOG.md
- **提交流程**：更新后**不自动 commit**，等待用户确认后再提交
- 日常功能优化不更新 CHANGELOG.md，只需更新 [DESIGN.md](DESIGN.md) 与 [desktop/README.md](desktop/README.md)
- 本分支的 CHANGELOG.md **自 2026-09-15 起封存**（里面只到 v0.2.7，是 Py 版的历史）；
  桌面端的进展流水记在 [TODO.md](TODO.md) 的「桌面版工作线」一节 —— 连打包发版也记在那里

---

## 常用命令

```bash
# 桌面端（本分支，都在 desktop/ 下执行）
npm install
npm run dev          # 纯前端预览（无 Tauri 宿主，只能调样式）
npm run build        # tsc + vite build
npm run e2e          # 构建 + 真浏览器冒烟（唯一的验证闸门，见「工作流程」）
npm run tauri dev    # 真实窗口（首次需编译 Rust）
npm run tauri build  # 出安装包：NSIS + MSI → src-tauri/target/release/bundle/
                     # 便携版不在 bundler 的目标里，两步手工：把 target/release/desktop.exe
                     # 拷成 bundle/portable/Tadado2.exe，再压成 bundle/portable/Tadado2-portable.zip
                     # 第四份是给用户的迁移 skill 包（不在构建流程里，要手工压一次）：
                     # Compress-Archive resources/skill/tadado-activity-import -DestinationPath \
                     #   desktop/src-tauri/target/release/bundle/tadado-activity-import.zip
                     # 发版时这四份一起交（见 resources/skill/tadado-release/SKILL.md）
```

<details>
<summary>已归档的 Python 版命令（只在 <code>archive/pyversion</code> 分支上有效）</summary>

```bash
uv venv --python 3.10 .venv && uv sync --dev
uv run python main.py                     # GUI
uv run python main.py --cli list          # CLI
uv run pytest                             # 全部用例
uv run black src/ tests/ && uv run ruff check src/ tests/
```

### CLI 通道（v0.2.7+，**仅 `archive/pyversion` 分支**）

> 本分支是桌面端，没有 CLI 通道；这一节只在归档分支上有效。

- `tadado-cli.exe`（打包版）/ `uv run python main.py --cli`（开发版）提供 12 个命令：
  `list / today / add / edit / done / rm / tags / partitions / archive / recurrence / reminder / export`
- GUI 运行时 CLI 经本地管道转发（单一写者），未运行时 headless 直写
- Claude Code skill 的**仓库副本**是 `resources/skill/tadado/SKILL.md`（CLI 的 AI 操作手册）。
  它是**本机配置**而非仓库内容：`.claude/` 在 `.gitignore` 里，要生效得把它拷到当前工作区的
  `.claude/skills/tadado/SKILL.md` —— 别在仓库里找那个路径
- `src/cli/commands.py` 是命令执行核心，GUI 管道处理（`src/app.py`）与 headless 共用

## 架构摘要

**桌面端（本分支，`desktop/`）**：`index.html`（骨架）→ `src/main.ts`（按顺序 mount 各模块）
→ `src/shell/`（外壳：标题栏 / rail / 主题 / 托盘 / 热键 / 锁屏 / 浮层控件）→ `src/pages/`
（五个页面 + 维护抽屉 + 跨页跳转 `focus.ts` + 通用分页器 `pager.ts` + `shared.ts` 里的公共谓词与常量）
→ `src/data/`（`db.ts` SQLite 与故障不降级 / `store.ts` 变更广播 / `schema.ts` 版本与迁移 /
`markdown.ts` 写法 / `time.ts` 时间口径 / `mock.ts` 演示空间的 100 条种子）。
分层与依赖方向见 [DESIGN.md](DESIGN.md) 的 §1.2、§2.2；逐文件清单见 [desktop/README.md](desktop/README.md)。

桌面端的几条核心原则（细节都在 DESIGN.md）：

- **一个谓词、多个消费方** —— 「今天到期」「逾期」这类判据只写一处，那排指标卡 / 筛选 / 时间轴共用
  （各写一份迟早各说各话，见 §4.1 那次 47 对 40 的口径分叉）
- **一屏到底** —— 主区不滚，会长的那块（表格 / 列表）在卡片内部吃掉剩余高度
- **样式只有一个翻译层** —— `src/styles/tokens.css` 把权威源译成 CSS 变量，不在这里新增颜色
- **时间只有一种口径** —— 「今天」是本地日历日的 anchor、时间戳的 UTC 分量就是墙上时刻，
  一律走 `data/time.ts`，不要用 `Date.now()` 参与日期运算
- **改动留下痕迹** —— 行为变更同步 DESIGN.md / TODO.md，并有 e2e 断言钉住

<details>
<summary>已归档的 Python 版架构（只在 <code>archive/pyversion</code> 分支上有效）</summary>

四层：`src/ui/` → `src/services/` → `src/models/` → SQLite，模块间通过 `SignalBus` Qt 信号解耦通信。
核心原则：**raw_md 是规范数据源**、**Design Tokens 统一配色**（`design_tokens.py`）、**配置驱动**。
PEP8：模块 `snake_case`，类 `PascalCase`，函数/变量 `snake_case`，常量 `UPPER_SNAKE_CASE`，
私有 `_prefix`，Qt 信号过去式动词。

</details>

## 通用准则

- **复用优先**：检索开源、可靠、可复用的组件，避免重复造轮子
- **主题适配**：桌面端配色一律走 `src/styles/tokens.css` 的 CSS 变量，亮/暗双主题同时适配
  （权威源与「不要新增颜色」的规矩见 [desktop/README.md](desktop/README.md) 的「设计来源」）
- **环境隔离**：开发/生产使用不同数据库和配置
- **文档同步**：功能变更后及时更新 [DESIGN.md](DESIGN.md) 与 [desktop/README.md](desktop/README.md)，
  流水记 [TODO.md](TODO.md)（参见上方「工作流程」）。
  `resources/help/manual.html` 是 Py 版的产物，本分支上不存在
