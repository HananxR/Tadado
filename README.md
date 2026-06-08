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
- [***] <2026-06-15> 完成产品需求文档 #工作 #产品      ← 紧急任务
- [** ] <2026-06-20> 读《系统设计》第 5 章 #学习        ← 重要任务
- [x] <2026-06-10> 提交 Q3 预算报告 #工作 #财务          ← 已完成
```

## ✨ 功能

<table>
<tr>
<td width="50%">

### 📝 任务管理
- **Markdown 语法** — 一行写完任务、优先级、截止时间、标签
- **全文搜索** — SQLite FTS5 驱动，输入即搜
- **9 列表格** — 复选框、序号、时间、进度、状态一目了然
- **优先级渲染** — 整行红/橙/绿/蓝背景，一眼分清轻重缓急

### 📊 活动分析
- **日历热力图** — 12 月 × 7 天 × 5 周矩阵，GitHub 风格
- **活动时间线** — 每条任务的进展历程可回溯
- **报告导出** — Markdown / Excel，一步导出

</td>
<td width="50%">

### 🔧 高效操作
- **批量管理** — 全选、右键菜单批量改状态、延后、中止、删除
- **多任务创建** — 一次性创建 3 条任务，快速拆解工作
- **标签系统** — 重命名、合并，全局自动同步

### 🔒 分区 & 安全
- **多分区隔离** — 工作 / 学习 / 个人，互不干扰
- **密码保护** — 敏感分区单独设密码
- **自动锁定** — 闲置超时自动锁定，离开工位不担心

### ⏰ 智能提醒
- 到期通知托盘弹窗
- 安静时段免打扰
- 多个任务合并为一条消息

</td>
</tr>
</table>

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
