<p align="center">
  <img src="resources/icons/app.png" width="96" alt="Tadado">
</p>

<h1 align="center">Tadado</h1>

<p align="center">
  <b>Less Noise, More Done.</b><br>
  用 Markdown 管理你的每一天。
</p>

<p align="center">
  <a href="https://github.com/HananxR/Tadado/releases"><img src="https://img.shields.io/github/v/release/HananxR/Tadado?color=6366F1"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green"></a>
  <a href="#"><img src="https://img.shields.io/badge/python-3.10+-blue"></a>
  <a href="#"><img src="https://img.shields.io/badge/platform-Windows_Linux-0078D6"></a>
</p>

---

Tadado 是一款本地优先的桌面任务管理工具：用 Markdown 一行写完一个任务，其余交给软件——组织、追踪、提醒、回顾。数据全部存储在本地 SQLite，无需联网、无需注册。

> 名字由来：**Tadado** = **"Tada!"** + **"do"** —— 完成任务那一刻的欢呼 + 行动与执行。

## ✨ 核心特性

- **Markdown 驱动** — 一行定义任务：`- [***] <2026-06-15 14:30> 修复登录Bug #工作 #后端`
- **活动分析** — 日历热力图（4 套配色）、活动时间线、标签浏览、活动报告
- **批量管理** — 全选/批量状态变更/延后/中止/删除、标签重命名与合并、智能归档
- **分区管理** — 多分区隔离、密码保护、自动锁定
- **周报 / 月报摘要** — 一键生成可直接粘贴进汇报的摘要（分区优先、标签分组）
- **AI 助手** — 托盘一键启动专属 Claude Code / Codex 会话，自动续接上下文；亦提供 `tadado-cli` 命令行（14 个命令）与 Claude Code skill
- **暖灰双主题** — 设计令牌驱动的亮/暗主题，卡片分层、统一视觉规范

## 📝 Markdown 语法速查

| 优先级 | 方括号 | 示例 |
|:--:|:--:|------|
| 🔴 紧急 | `[***]` | `- [***] <2026-06-15 14:30> 修复登录并发Bug #工作 #后端` |
| 🟠 重要 | `[** ]` | `- [** ] <2026-06-20> 准备周五组会演示文稿 #工作 #团队` |
| 🟢 关注 | `[*  ]` | `- [*  ] <2026-06-12> 读《重构》第 8 章 #学习 #阅读` |
| 🔵 普通 | `[   ]` | `- [   ] <2026-06-30> 每周三次有氧运动 #健康 #运动` |

> 方括号里是**优先级**而非复选框——`*` 越多越紧急。状态（待办/进行中/已完成/逾期）由软件自动管理；日期、时间、标签均可选。

## 📦 安装

| 方式 | 说明 |
|------|------|
| Windows 安装包 | GitHub Releases 下载 `Tadado_setup_v*.exe` |
| 便携包 | Windows `.zip` / Linux `tar.gz`，解压即用 |
| 从源码运行 | `uv venv --python 3.10 .venv && uv sync --dev && uv run python main.py` |

## 📖 文档

- 使用手册：程序内 `设置 → 关于 → 帮助文档`，或直接打开 `resources/help/manual.html`
- 详细设计：[DESIGN.md](DESIGN.md)
- 更新日志：[CHANGELOG.md](CHANGELOG.md)
- AI 通道说明：`.claude/skills/tadado/SKILL.md`（CLI 命令手册与工作流规则）

## 🛠 技术栈

Python 3.10 · PySide6 · SQLite + FTS5 · APScheduler · PyInstaller + Inno Setup

## 📄 许可

MIT License © HananxR
