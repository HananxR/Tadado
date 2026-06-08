<p align="center">
  <img src="resources/icons/app.svg" width="96" alt="Tadado">
</p>

<h1 align="center">Tadado</h1>

<p align="center">
  <b>Less Noise, More Done.</b><br>
  用 Markdown 管理你的每一天。
</p>

<p align="center">
  <a href="https://github.com/HananxR/Tadado/releases"><img src="https://img.shields.io/github/v/release/HananxR/Tadado?color=6366F1&label=最新版本"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green"></a>
  <a href="#"><img src="https://img.shields.io/badge/python-3.10+-blue"></a>
  <a href="#"><img src="https://img.shields.io/badge/platform-Windows%2010%2F11-0078D6"></a>
  <a href="https://github.com/HananxR/Tadado/actions"><img src="https://github.com/HananxR/Tadado/actions/workflows/test.yml/badge.svg"></a>
</p>

---

<p align="center">
  <img src="https://raw.githubusercontent.com/HananxR/Tadado/main/resources/welcome_bg.jpg" width="720" alt="Tadado 界面截图" style="border-radius: 12px; box-shadow: 0 4px 24px rgba(0,0,0,0.15);">
</p>

<p align="center"><sub>⚠ 图片来源于网络，忘记出处，侵权请联系删除</sub></p>

---

## Tadado 是什么？

Tadado 是一款 **Windows 桌面任务管理工具**。你用简单的 Markdown 语法写任务，它帮你组织、追踪、回顾。所有数据存本地，无需联网，无需注册。

```
- [***] <2026-06-15 14:30> 修复用户登录模块并发Bug #工作 #后端    ← 紧急 (3 星)
- [** ] <2026-06-20> 准备周五组会演示文稿 #工作 #团队              ← 重要 (2 星)
- [*  ] <2026-06-12> 读《重构》第 8 章 #学习 #阅读                ← 关注 (1 星)
- [   ] <2026-06-30> 每周三次有氧运动 #健康 #运动                  ← 普通 (0 星)
```

> **方括号不是复选框，是优先级** — `*` 的数量决定紧急程度（最多 3 个）。任务状态（待办/进行中/已完成/逾期）由软件自动管理，无需在 Markdown 中手动标记。

## 🚀 快速上手

| 步骤 | 操作 |
|------|------|
| **1. 写任务** | 输入 `- [***] <日期> 任务标题 #标签`，Enter 一键创建 |
| **2. 三视图** | 标题栏按钮切换：编辑视图 · 活动分析 · 批量管理 |
| **3. 演示空间** | 首次启动内置 15 个演示任务，覆盖全部功能，开箱即体验 |
| **4. 右键操作** | 任务列表右键 → 改状态 / 改优先级 / 复制 Markdown / 批量管理 |

> 💡 **演示空间**：首次启动时内置 15 个演示任务，覆盖 4 级优先级（紧急/重要/关注/普通）、全部状态（待办/进行中/已完成/逾期）、循环任务、活动时间线等高级特性。切换到「演示空间」分区即可体验全部功能，无需从零开始创建数据。

---

## 📸 界面导览

### 任务视图 — 日常编辑与管理

<p align="center">
  <img src="https://raw.githubusercontent.com/HananxR/Tadado/main/resources/screenshots/task-view.png" width="720" alt="任务视图全貌">
</p>
<p align="center"><sub>▲ 任务视图：左侧 9 列表格 + 右侧编辑面板 + 底部状态栏。整行红/橙/绿/蓝背景区分优先级，一眼看清轻重缓急。</sub></p>

<p align="center">
  <img src="https://raw.githubusercontent.com/HananxR/Tadado/main/resources/screenshots/task-input.png" width="720" alt="Markdown 任务输入">
</p>
<p align="center"><sub>▲ 输入框支持完整 Markdown 语法：优先级 + 日期 + 标题 + 标签，一行搞定。Enter 创建。</sub></p>

### 活动分析 — 日历热力图

<p align="center">
  <img src="https://raw.githubusercontent.com/HananxR/Tadado/main/resources/screenshots/heatmap.png" width="720" alt="日历热力图">
</p>
<p align="center"><sub>▲ 12 月 × 7 天 × 5 周紧凑矩阵，12px 单元格深蓝→青色渐变。悬浮显示当天活动详情，左侧标签云联动过滤。</sub></p>

### 批量管理控制台

<p align="center">
  <img src="https://raw.githubusercontent.com/HananxR/Tadado/main/resources/screenshots/batch-view.png" width="720" alt="批量管理控制台">
</p>
<p align="center"><sub>▲ 全宽表格 + 批量工具栏 + 右侧标签管理面板。支持全选、批量改状态/优先级、延后处理、导出，以及标签重命名/合并。</sub></p>

### 演示空间

<p align="center">
  <img src="https://raw.githubusercontent.com/HananxR/Tadado/main/resources/screenshots/demo-space.png" width="720" alt="演示空间">
</p>
<p align="center"><sub>▲ 切换到「演示空间」分区，15 个预置任务覆盖全部核心功能，开箱即体验，无需从零创建数据。</sub></p>

---

## ✨ 功能详解

### 📝 任务管理

**新建任务**

- **单任务** — 输入框输入 Markdown 后按 `Enter`，或点击标题栏「新建单任务」
- **多任务** — 点击标题栏「新建多任务」，编辑器生成 3 行模板，快速拆解工作
- **草稿模式** — 新建时输入框蓝色高亮，未保存草稿显示提醒横幅

**任务列表（9 列）**

| 列 | 说明 |
|----|------|
| ☐ 复选框 | 圆形勾选，支持全选/多选 |
| # 序号 | 自动编号 |
| 创建时间 | `YYYY-MM-DD HH:MM` |
| 任务内容 | 标题 + 标签，凸显任务红色加粗 |
| 截止时间 | 日期 + 可选时间 |
| 进度 | 0–100% |
| 状态 | 待办 / 进行中 / 已完成 / 逾期（彩色徽章） |
| 标签 | 彩色胶囊标签 |
| 归档 | 已归档 / 未归档 / — |

- **优先级整行渲染** — 红（紧急）→ 橙（重要）→ 绿（关注）→ 淡蓝（普通），整行背景色区分
- **暂停任务** — 透明度 45%，与其他视觉系统叠加
- **分页** — 每页 20 / 50 / 100 条可选

**编辑任务**

点击任务行，右侧弹出编辑面板：

- **Markdown 源码编辑** — 直接编辑原始 Markdown，下方实时 HTML 预览
- **截止日期** — 日历选择器 + 时间选择器 + 快速计算器
- **活动时间线** — 任务进展历程，可追加新进度记录（状态变更、进度推进）
- **优先级下拉** — 紧急 / 重要 / 关注 / 普通 四档切换
- **操作按钮** — 编辑 / 保存 / 删除

**筛选与排序**

- **全文搜索** — SQLite FTS5 驱动，输入即搜，响应 < 50ms
- **优先级过滤** — 紧急 / 重要 / 关注 / 普通
- **状态过滤** — 待办 / 进行中 / 已完成 / 逾期
- **排序** — 优先级 → 截止日期（NULL 最后）→ 创建时间

**右键菜单**

任务行右键可快速：更改状态 / 更改优先级 / 调整分区 / 延后处理（+1/+2/+5/+7/+10 天）/ 中止 / 重启 / 删除 / 复制 Markdown。支持多选批量操作。

**统计组件**

- **状态徽章条** — 4 个可点击计数徽章（逾期/待办/进行中/已完成），点击切换激活筛选
- **进度动态栏** — 6 个时段按钮（昨天/今天/上周/本周/上月/本月），显示最近活跃任务的最新进展
- **速览栏** — 6 个预设按钮 + 自动轮播任务卡片（每 5 秒切换，每组 3 个任务）

---

### 📊 活动分析

**日历热力图**

- 12 个月 × 7 天 × 5 周紧凑日历矩阵
- 12px 单元格，深蓝→青色 8 级渐变（accent 单色插值）
- 悬浮单元格查看：日期、活动条目数、涉及任务、标签分布
- 顶部 `◀ 年份 ▶` 切换年份，下拉筛选特定标签
- 图例 0–7+ 级色阶

**标签云导航**

- 左侧胶囊标签云，按使用次数排列
- 点击勾选标签，右侧联动显示对应活动内容
- 搜索框实时过滤标签
- 导航栏 ◀ ▶ 循环切换被勾选的标签队列

**活动报告导出**

按勾选标签全量导出 Markdown / Excel / TXT。Excel 分列（序号/任务/状态/进度/活动），文件名含分区 + 日期范围 + 标签数。

---

### 🔧 批量管理控制台

点击标题栏「任务管理」进入，三栏布局：左侧筛选面板（180px）+ 中间全宽表格 + 右侧标签管理（30%）。

**批量操作**

工具栏提供：全选 / 更改状态 / 更改优先级 / 删除 / 中止 / 重启 / 延后处理 / 导出（MD/Excel）/ 已选计数。

**标签管理**

右侧面板展示当前分区所有标签及其使用次数（降序）：

- **重命名** — 选中标签 → 输入新名 → 全局自动更新所有关联任务
- **合并** — 多选标签（Ctrl+Click）→ 选择合并目标 → 源标签替换为目标后删除
- **搜索** — 实时过滤标签列表

> ⚠ 标签合并不可撤销，操作前请确认。

**归档管理**

- **手动归档** — 立即归档当前分区所有 DONE 任务（不依赖 `archive_days` 阈值）
- **清除已归档** — 永久删除所有已归档任务（需二次确认）

---

### 🔒 分区与安全

**分区概念**

分区是独立的任务空间，不同分区的任务、标签互不影响。默认提供：**工作**、**学习**、**个人**、**演示空间**。

**切换分区**

点击状态栏最左侧分区名称 → 下拉菜单选择目标分区。当前分区以 ✓ 标记，锁定分区以 🔒 标记。

**密码保护**

- 设置中为每个分区单独设置密码
- 锁定分区后，切换需输入密码解锁
- 解锁状态仅内存保持，关闭程序后重置
- **自动锁定** — 按分区独立设定空闲超时（1/5/10/30/60 分钟），闲置自动锁定

**分区管理**

设置对话框分区表格中：新建 / 重命名 / 设密码 / 删除（分区内有任务时不可删除，至少保留一个分区）。

---

### ⏰ 系统托盘与提醒

**托盘操作**

- 右键菜单：显示/隐藏窗口、新建单任务、新建多任务、退出
- 双击图标：切换窗口显示/隐藏
- 最小化到托盘：开启后最小化隐藏到托盘而非任务栏

**任务提醒**

- 后台每分钟检查当前分区到期和逾期任务
- 多个提醒合并为一条 Windows 通知（最多显示 5 个任务标题）
- 默认关闭，需在设置中手动开启
- 安静时段免打扰（默认 22:00–08:00）

**循环任务**

任务完成（DONE）时，根据循环规则（+1天/+1周/+1月/+1年）自动创建下一实例，继承标题、标签、优先级。

---

### ⚙ 设置

单页滚动布局，6 个功能区块：

| 区块 | 配置项 |
|------|--------|
| 外观 | 亮色/暗色主题、最小化到托盘 |
| 任务列表 | 每页条数（20/50/100）、默认排序、热力图起始年份 |
| 提醒 | 启用提醒、间隔分钟、安静时段起止 |
| 分区管理 | 7 列表格：名称/默认分区/可见/自动归档/归档阈值/自动锁定/密码 |
| 激励语 | 4 条自定义励志语录，状态栏循环显示 |

---

## 📥 安装

### 方式一：下载安装包（推荐）

从 [Releases](https://github.com/HananxR/Tadado/releases) 下载最新版安装包，一键安装。

### 方式二：从源码运行

```bash
# Python 3.10+
uv venv --python 3.10 .venv
uv sync --dev
uv run python main.py
```

## 🛠 技术栈

| 层面 | 技术 |
|------|------|
| 语言 | Python 3.10+ |
| GUI | PySide6 ≥ 6.5 (Qt) |
| 数据库 | SQLite 3 + FTS5 全文索引 |
| 定时 | APScheduler ≥ 3.10 |
| 打包 | PyInstaller + Inno Setup |

---

## ❓ 常见问题

<details>
<summary><b>Q: 窗口显示异常（空白、错位、无法拖动或贴靠失效）</b></summary>

1. 关闭并重启应用
2. 切换全屏再退出（标题栏右侧 ⛶ 按钮），窗口会重置到屏幕中央
3. 若贴靠（Snap）功能失效，可点击全屏按钮再还原，刷新窗口样式状态
</details>

<details>
<summary><b>Q: 搜索不到任务</b></summary>

1. 确认当前所在分区（状态栏左侧分区名）
2. 检查筛选条件是否过严
3. 确认任务未被归档（归档任务在编辑视图不显示）
</details>

<details>
<summary><b>Q: 提醒不生效</b></summary>

1. 确认设置中"启用提醒"已勾选（默认关闭）
2. 检查是否在免打扰时段内
3. 确认当前分区有到期/逾期任务
4. Windows 设置 → 通知 → 确认 Tadado 权限已开启
</details>

<details>
<summary><b>Q: 如何备份数据</b></summary>

1. 关闭 Tadado
2. 复制 `resources/tadado.data` 到安全位置
3. 恢复时将备份文件覆盖同名文件
</details>

<details>
<summary><b>Q: 程序无法启动</b></summary>

1. 确认系统为 Windows 10 或更高
2. 检查杀毒软件是否拦截
3. 重新安装最新版本（覆盖安装不丢失数据）
</details>

---

## 📖 文档

- **本文档即完整使用手册** — 涵盖全部功能说明和常见问题
- 技术设计文档 → [DESIGN.md](DESIGN.md)
- 贡献指南 → [CONTRIBUTING.md](CONTRIBUTING.md)

## 💡 灵感

[Obsidian Calendar](https://github.com/liamcain/obsidian-calendar-plugin) · [Obsidian Dataview](https://github.com/blacksmithgu/obsidian-dataview) · [Heatmap Tracker](https://github.com/mokkiebear/heatmap-tracker)

## 📄 许可

[MIT License](LICENSE) — 自由使用、修改、分发，包括商业用途。

<p align="center">
  <sub>Made with ❤️ by <a href="mailto:hanxy8413@gmail.com">HananxR</a></sub>
</p>
