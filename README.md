<p align="center">
  <img src="https://img.shields.io/badge/version-v1.0.0-blue" alt="version">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="license">
  <img src="https://img.shields.io/badge/python-3.10-blue" alt="python">
</p>

# DeskTodoSeq

基于 Markdown 的 Windows 桌面任务管理工具 — 开源、离线、高效的个人任务管理。

> 🚀 本项目由 **Claude + Claude Code + DeepSeek** 辅助开发。

## ✨ 功能特性

| | | |
|---|---|---|
| 📝 **任务管理** | Markdown 语法创建，状态流转（待办/进行中/已完成/已逾期），全文搜索 |
| 📊 **活动分析** | 日历热力图，活动统计，标签云浏览 |
| 🔧 **批量操作** | 状态变更、挂起、延后处理，Markdown / Excel 导出 |
| 🏷 **标签管理** | 重命名、合并、搜索，全局自动同步 |
| 🔒 **分区管理** | 多分区隔离，密码保护，自动锁定 |
| ⏰ **智能提醒** | 到期通知，免打扰，循环任务 |
| 🎨 **双主题** | 亮色 / 暗色，一键跟随系统 |

## 🚀 快速开始

```bash
uv venv --python 3.10 .venv
uv sync --dev
uv run python main.py
```

## 📖 文档

完整使用手册已内置在软件中：点击标题栏 **帮助 → 帮助文档** 即可在浏览器中打开。也可直接查看 [resources/help/manual.html](resources/help/manual.html)。

## 🛠 技术栈

Python 3.10 · PySide6 (Qt) · SQLite + FTS5 · APScheduler

## 💡 灵感来源

- [Obsidian Calendar Plugin](https://github.com/liamcain/obsidian-calendar-plugin) — 日历热力图
- [Obsidian Dataview](https://github.com/blacksmithgu/obsidian-dataview) — 任务筛选与数据查询
- [Heatmap Tracker](https://github.com/mokkiebear/heatmap-tracker) — 活动热力图可视化
- Obsidian、OneNote 等笔记软件

## 📄 许可

DeskTodoSeq 对个人用户**免费**使用。如需商用，请联系作者获取授权。

MIT License · [Hanxy](mailto:hanxy8413@gmail.com) · [github.com/HananxR/DeskTodoSeq](https://github.com/HananxR/DeskTodoSeq)
