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
| **2. 三视图** | `Ctrl+1` 编辑视图 · `Ctrl+2` 活动分析 · `Ctrl+3` 批量管理 |
| **3. 演示空间** | 首次启动内置 15 个演示任务，覆盖全部功能，开箱即体验 |
| **4. 右键操作** | 任务列表右键 → 改状态 / 改优先级 / 复制 Markdown / 批量管理 |

## ✨ 功能

<table>
<tr>
<td width="50%">

### 📝 任务管理
- **Markdown 语法** — 一行写完优先级（`[***]`）、截止日期、标签，方括号是优先级不是复选框
- **9 列表格** — 复选框、序号、创建时间、任务内容、截止时间、进度、状态徽章、标签、归档状态
- **优先级整行渲染** — 红（紧急）/ 橙（重要）/ 绿（关注）/ 蓝（普通）整行背景
- **全文搜索** — SQLite FTS5 驱动，输入即搜，响应 < 50ms
- **排序与分页** — 按优先级/截止日/创建时间排序，20/50/100 条每页可选

### 📊 活动分析
- **日历热力图** — 12 月 × 7 天 × 5 周矩阵，12px 单元格，深蓝→青色渐变，悬浮显示当天详情
- **活动时间线** — 每条任务可追加进展记录，完整回溯状态变更和进度推进
- **标签云导航** — 胶囊标签按使用次数排列，点击勾选联动内容区
- **报告导出** — 按标签全量导出 Markdown / Excel / TXT

</td>
<td width="50%">

### 🔧 高效操作
- **批量管理** — 全选、右键菜单批量改状态、改优先级、延后、中止、重启、删除
- **多任务创建** — 一次性输入 3 条任务，快速拆解工作，自动带标签模板
- **速览栏** — 昨天/今天/上周/本周/上月/本月 6 个预设，一键切换，自动轮播
- **标签系统** — 重命名、合并，全局自动同步

### 🔒 分区 & 安全
- **多分区隔离** — 工作 / 学习 / 个人 / 演示空间，数据互不干扰
- **密码保护** — 敏感分区单独设密码，切换即锁定
- **自动锁定** — 闲置超时自动锁定，按分区独立配置时长
- **手动归档** — 批量管理控制台一键归档已完成、清除已归档

### ⏰ 智能提醒
- 到期任务托盘弹窗通知
- 安静时段免打扰（默认 22:00–08:00）
- 多个提醒合并为一条消息
- 循环任务：完成后自动创建下一实例（+1天/周/月/年）

</td>
</tr>
</table>

> 💡 **演示空间**：首次启动时内置 15 个演示任务，覆盖 4 级优先级（紧急/重要/关注/普通）、全部状态（待办/进行中/已完成/逾期）、循环任务、活动时间线等高级特性。切换到「演示空间」分区即可体验全部功能，无需从零开始创建数据。

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

## 📖 文档

- 完整使用手册 **内置于软件中**（帮助 → 帮助文档）
- 技术设计文档 → [DESIGN.md](DESIGN.md)
- 贡献指南 → [CONTRIBUTING.md](CONTRIBUTING.md)

## 💡 灵感

[Obsidian Calendar](https://github.com/liamcain/obsidian-calendar-plugin) · [Obsidian Dataview](https://github.com/blacksmithgu/obsidian-dataview) · [Heatmap Tracker](https://github.com/mokkiebear/heatmap-tracker)

## 📄 许可

[MIT License](LICENSE) — 自由使用、修改、分发，包括商业用途。

<p align="center">
  <sub>Made with ❤️ by <a href="mailto:hanxy8413@gmail.com">HananxR</a></sub>
</p>
