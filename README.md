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

<p align="center">
  <a href="#tadado-是什么">是什么</a> ·
  <a href="#-快速上手">快速上手</a> ·
  <a href="#-界面导览">界面导览</a> ·
  <a href="#-功能详解">功能详解</a> ·
  <a href="#-安装">安装</a> ·
  <a href="#-常见问题">FAQ</a> ·
  <a href="#-技术栈">技术栈</a>
</p>

---

## Tadado 是什么？

Tadado 是一款 **Windows 桌面任务管理工具**。你用简单的 Markdown 语法写任务，它帮你组织、追踪、回顾。所有数据存本地，无需联网，无需注册。

### Markdown 语法速查

| 优先级 | 方括号 | 示例（一行写完） |
|:--:|:--:|------|
| 🔴 紧急 | `[***]` | `- [***] <2026-06-15 14:30> 修复登录并发Bug #工作 #后端` |
| 🟠 重要 | `[** ]` | `- [** ] <2026-06-20> 准备周五组会演示文稿 #工作 #团队` |
| 🟢 关注 | `[*  ]` | `- [*  ] <2026-06-12> 读《重构》第 8 章 #学习 #阅读` |
| 🔵 普通 | `[   ]` | `- [   ] <2026-06-30> 每周三次有氧运动 #健康 #运动` |

> **方括号不是复选框，是优先级** — `*` 的数量决定紧急程度（最多 3 个）。任务状态（待办/进行中/已完成/逾期）由软件自动管理，无需在 Markdown 中手动标记。日期、时间、标签均为可选。

---

## 🚀 快速上手

<table>
<tr>
<td width="25%" align="center"><b>✍ 写任务</b></td>
<td width="25%" align="center"><b>🔀 三视图</b></td>
<td width="25%" align="center"><b>🎁 演示空间</b></td>
<td width="25%" align="center"><b>🖱 右键操作</b></td>
</tr>
<tr>
<td valign="top"><sub>输入 <code>- [***] &lt;日期&gt; 标题 #标签</code>，Enter 一键创建</sub></td>
<td valign="top"><sub>标题栏按钮切换：编辑视图 · 活动分析 · 批量管理</sub></td>
<td valign="top"><sub>首次启动内置 15 个演示任务，覆盖全部功能，开箱即体验</sub></td>
<td valign="top"><sub>任务列表右键 → 改状态 / 改优先级 / 复制 Markdown / 批量管理</sub></td>
</tr>
</table>

> 💡 **演示空间**：首次启动内置 15 个演示任务，覆盖 4 级优先级（紧急/重要/关注/普通）、全部状态（待办/进行中/已完成/逾期）、循环任务、活动时间线等高级特性。切换到「演示空间」分区即可体验全部功能，无需从零开始创建数据。

<p align="right"><sub><a href="#">↑ 返回顶部</a></sub></p>

---

## 📸 界面导览

<table>
<tr>
<td width="50%">
<p align="center">
  <img src="https://raw.githubusercontent.com/HananxR/Tadado/main/resources/screenshots/task-view.png" width="100%" alt="任务视图">
</p>
<p align="center"><sub>▲ 任务视图：9 列表格 + 编辑面板 + 状态栏，优先级整行红/橙/绿/蓝渲染</sub></p>
</td>
<td width="50%">
<p align="center">
  <img src="https://raw.githubusercontent.com/HananxR/Tadado/main/resources/screenshots/task-input.png" width="100%" alt="Markdown 输入">
</p>
<p align="center"><sub>▲ 输入框支持完整 Markdown 语法：优先级 + 日期 + 标题 + 标签，一行搞定</sub></p>
</td>
</tr>
<tr>
<td width="50%">
<p align="center">
  <img src="https://raw.githubusercontent.com/HananxR/Tadado/main/resources/screenshots/heatmap.png" width="100%" alt="日历热力图">
</p>
<p align="center"><sub>▲ 12 月 × 7 天 × 5 周矩阵，12px 深蓝→青色渐变，悬浮显示活动详情</sub></p>
</td>
<td width="50%">
<p align="center">
  <img src="https://raw.githubusercontent.com/HananxR/Tadado/main/resources/screenshots/batch-view.png" width="100%" alt="批量管理控制台">
</p>
<p align="center"><sub>▲ 全宽表格 + 批量工具栏 + 标签管理面板，支持批量操作和标签重命名/合并</sub></p>
</td>
</tr>
<tr>
<td colspan="2">
<p align="center">
  <img src="https://raw.githubusercontent.com/HananxR/Tadado/main/resources/screenshots/demo-space.png" width="60%" alt="演示空间">
</p>
<p align="center"><sub>▲ 切换到「演示空间」分区，15 个预置任务覆盖全部核心功能，开箱即体验</sub></p>
</td>
</tr>
</table>

<p align="right"><sub><a href="#">↑ 返回顶部</a></sub></p>

---

## ✨ 功能详解

<p align="center"><sub>◆ ◆ ◆</sub></p>

### 📝 任务管理

<p>
  <img src="https://img.shields.io/badge/FTS5-全文搜索-6366F1" alt="FTS5">
  <img src="https://img.shields.io/badge/9列-表格视图-success" alt="9列">
  <img src="https://img.shields.io/badge/优先级-四级渲染-orange" alt="优先级">
</p>

**🆕 新建任务**

- **单任务** — 输入框输入 Markdown 后按 `Enter`，或点击标题栏「新建单任务」
- **多任务** — 点击标题栏「新建多任务」，编辑器生成 3 行模板，快速拆解工作
- **草稿模式** — 新建时输入框蓝色高亮，未保存草稿显示提醒横幅

**📋 任务列表（9 列）**

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
- **暂停任务** — 透明度 45%
- **分页** — 20 / 50 / 100 条可选

**✏ 编辑任务**

点击任务行，右侧弹出编辑面板：

- **Markdown 源码编辑** — 直接编辑原始 Markdown，下方实时 HTML 预览
- **截止日期** — 日历选择器 + 时间选择器 + 快速计算器
- **活动时间线** — 任务进展历程，可追加新进度记录
- **优先级下拉** — 紧急 / 重要 / 关注 / 普通 四档切换

**🔍 筛选与排序**

- **全文搜索** — SQLite FTS5 驱动，输入即搜，响应 < 50ms
- **状态过滤** — 待办 / 进行中 / 已完成 / 逾期
- **排序** — 优先级 → 截止日期 → 创建时间

**📊 统计组件**

- **状态徽章条** — 4 个可点击计数徽章（逾期/待办/进行中/已完成），点击切换筛选
- **速览栏** — 昨天/今天/上周/本周/上月/本月 6 个预设 + 自动轮播（每 5 秒切换）
- **进度动态栏** — 6 个时段按钮，显示最近活跃任务的最新进展

<p align="right"><sub><a href="#">↑ 返回顶部</a></sub></p>

---

### 📊 活动分析

<p>
  <img src="https://img.shields.io/badge/热力图-12月×7天×5周-8b5cf6" alt="热力图">
  <img src="https://img.shields.io/badge/渐变-深蓝→青色-yellow" alt="渐变">
  <img src="https://img.shields.io/badge/导出-MD%20|%20Excel%20|%20TXT-blue" alt="导出">
</p>

**🗓 日历热力图**

- 12 个月 × 7 天 × 5 周紧凑矩阵，12px 单元格
- 深蓝→青色 8 级渐变（accent 单色插值），图例 0–7+
- 悬浮单元格查看：日期、活动条目数、涉及任务、标签分布
- 顶部 `◀ 年份 ▶` 切换年份，下拉筛选特定标签

**☁ 标签云导航**

- 左侧胶囊标签云，按使用次数排列
- 点击勾选标签，右侧联动显示对应活动内容
- 顶部搜索框实时过滤 + 导航栏 ◀ ▶ 循环切换标签队列

**📤 报告导出**

按勾选标签全量导出 Markdown / Excel / TXT。Excel 分列（序号/任务/状态/进度/活动），文件名含分区 + 日期范围 + 标签数。

<p align="right"><sub><a href="#">↑ 返回顶部</a></sub></p>

---

### 🔧 批量管理控制台

点击标题栏「任务管理」进入，三栏布局：左侧筛选面板（180px）+ 中间全宽表格 + 右侧标签管理（30%）。

**📦 批量操作**

工具栏提供：全选 / 更改状态 / 更改优先级 / 删除 / 中止 / 重启 / 延后处理 / 导出 / 已选计数

**🏷 标签管理**

- **重命名** — 选中标签 → 输入新名 → 全局自动更新所有关联任务
- **合并** — 多选标签 → 选择合并目标 → 源标签替换为目标后删除

> ⚠ 标签合并不可撤销，操作前请确认。

**🗄 归档管理**

- **手动归档** — 立即归档当前分区所有已完成任务（不依赖阈值）
- **清除已归档** — 永久删除已归档任务（需二次确认）

<p align="right"><sub><a href="#">↑ 返回顶部</a></sub></p>

---

### 🔒 分区与安全

默认提供 **工作** · **学习** · **个人** · **演示空间** 四个分区，数据互不干扰。

- **🔀 切换分区** — 状态栏左侧分区名 → 下拉菜单选择，当前分区 ✓ 标记
- **🔑 密码保护** — 每分区独立设密码，切换即锁定，解锁仅内存保持
- **⏱ 自动锁定** — 按分区独立设定空闲超时（1/5/10/30/60 分钟）
- **📝 分区管理** — 设置中新建/重命名/设密码/删除（至少保留一个分区）

<p align="right"><sub><a href="#">↑ 返回顶部</a></sub></p>

---

### ⏰ 系统托盘与提醒

**托盘菜单** — 右键：显示/隐藏 · 新建单任务 · 新建多任务 · 退出。双击切换可见性。

**任务提醒** — 每分钟检查到期/逾期任务，多任务合并为一条 Windows 通知（最多 5 个标题）。默认关闭，需在设置中开启。

**免打扰** — 安静时段（默认 22:00–08:00）内不弹通知。

**循环任务** — 任务完成后自动创建下一实例（+1天/+1周/+1月/+1年），继承标题、标签、优先级。

<p align="right"><sub><a href="#">↑ 返回顶部</a></sub></p>

---

### ⚙ 设置

单页滚动布局：

| 区块 | 配置项 |
|------|--------|
| 🎨 外观 | 亮色/暗色主题、最小化到托盘 |
| 📋 任务列表 | 每页条数、默认排序、热力图起始年份 |
| 🔔 提醒 | 启用提醒、间隔分钟、安静时段 |
| 🔒 分区管理 | 名称/默认/可见/归档阈值/自动锁定/密码（7 列表格） |
| 💬 激励语 | 4 条自定义语录，状态栏循环显示 |

<p align="right"><sub><a href="#">↑ 返回顶部</a></sub></p>

<p align="center"><sub>◆ ◆ ◆</sub></p>

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

<p align="right"><sub><a href="#">↑ 返回顶部</a></sub></p>

---

## 🛠 技术栈

| 层面 | 技术 |
|------|------|
| 语言 | Python 3.10+ |
| GUI | PySide6 ≥ 6.5 |
| 数据库 | SQLite 3 + FTS5 全文索引 |
| 定时 | APScheduler ≥ 3.10 |
| 打包 | Nuitka + Inno Setup |

<p align="right"><sub><a href="#">↑ 返回顶部</a></sub></p>

---

## ❓ 常见问题

<details>
<summary>🖥 <b>窗口显示异常（空白、错位、无法拖动或贴靠失效）</b></summary>
<br>

1. 关闭并重启应用
2. 切换全屏再退出（标题栏右侧 ⛶ 按钮），窗口会重置到屏幕中央
3. 若贴靠（Snap）功能失效，可点击全屏按钮再还原，刷新窗口样式状态
</details>

<details>
<summary>🔍 <b>搜索不到任务</b></summary>
<br>

1. 确认当前所在分区（状态栏左侧分区名）
2. 检查筛选条件是否过严
3. 确认任务未被归档（归档任务在编辑视图不显示）
</details>

<details>
<summary>🔔 <b>提醒不生效</b></summary>
<br>

1. 确认设置中"启用提醒"已勾选（默认关闭）
2. 检查是否在免打扰时段内
3. 确认当前分区有到期/逾期任务
4. Windows 设置 → 通知 → 确认 Tadado 权限已开启
</details>

<details>
<summary>💾 <b>如何备份数据</b></summary>
<br>

1. 关闭 Tadado
2. 复制 `resources/tadado.data` 到安全位置
3. 恢复时将备份文件覆盖同名文件
</details>

<details>
<summary>🚫 <b>程序无法启动</b></summary>
<br>

1. 确认系统为 Windows 10 或更高
2. 检查杀毒软件是否拦截
3. 重新安装最新版本（覆盖安装不丢失数据）
</details>

<p align="right"><sub><a href="#">↑ 返回顶部</a></sub></p>

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
