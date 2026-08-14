# CLAUDE.md

Tadado 项目指导文件。详细设计文档见 [DESIGN.md](DESIGN.md)，更新日志见 [CHANGELOG.md](CHANGELOG.md)。

## 项目概览

Tadado — Windows 桌面任务管理工具，Python 3.10 + PySide6，Markdown 语法定义任务，SQLite + FTS5 存储，配备日历热力图。

## 工作流程

### 功能优化 → 文档同步

软件功能优化/新增/修改后，**必须**同步更新以下关联文档，确保与软件实际功能一致、术语使用一致：

| 文件 | 说明 |
|------|------|
| [DESIGN.md](DESIGN.md) | 详细设计说明，记录功能模块需求与实现方案 |
| [CLAUDE.md](CLAUDE.md) | 项目指导文件（本文件），运行时 AI 指令 |
| [resources/help/manual.html](resources/help/manual.html) | 用户帮助手册，面向最终用户 |

**提交流程**：文档更新完成后自动执行 `git add` + `git commit`（commit message 以 `docs:` 开头）。

### version.py 动态修改判定

[src/version.py](src/version.py) 是公开 API，数据已拆到 [src/_version_data.py](src/_version_data.py)：
- **数据文件** `_version_data.py`：`__version__` 值、`_RELEASE_HIGHLIGHTS` 字典 — 发版时由 `generate_db.bat` 更新
- **逻辑文件** `version.py`：`get_version()`、`parse_version()`、`get_release_highlights()` 等函数 — 不再因发版而被修改

**规则**：
- 仅数据变更（如改版本号、增删 highlights 条目）→ **不自动 commit**，留给发版流程统一提交
- 逻辑变更（如新增/修改函数、调整解析规则）→ 自动 commit

### CHANGELOG.md 更新规则

- **触发条件**：仅在用户明确要求"发版"或"发布新版本"时才更新 CHANGELOG.md
- **提交流程**：更新后**不自动 commit**，等待用户确认后再提交
- 日常功能优化不更新 CHANGELOG.md，只需更新 DESIGN.md 和 manual.html

---

## 常用命令

```bash
# 环境
uv venv --python 3.10 .venv && uv sync --dev

# 运行
uv run python main.py                              # GUI
uv run python main.py --cli list                   # CLI（详见 src/cli/ 与 .claude/skills/tadado/SKILL.md）

# 测试
uv run pytest                                      # 全部用例（当前 131+）
uv run pytest -k "round_trip"                      # 关键字匹配

# 代码质量
uv run black src/ tests/ && uv run ruff check src/ tests/
```

### CLI 通道（v0.2.7+）

- `tadado-cli.exe`（打包版）/ `uv run python main.py --cli`（开发版）提供 12 个命令：
  `list / today / add / edit / done / rm / tags / partitions / archive / recurrence / reminder / export`
- GUI 运行时 CLI 经本地管道转发（单一写者），未运行时 headless 直写
- Claude Code skill 位于 `.claude/skills/tadado/SKILL.md`，是 CLI 的 AI 操作手册
- `src/cli/commands.py` 是命令执行核心，GUI 管道处理（`src/app.py`）与 headless 共用

## 架构摘要

四层：`src/ui/` → `src/services/` → `src/models/` → SQLite，模块间通过 `SignalBus`（[src/utils/signal_bus.py](src/utils/signal_bus.py)）Qt 信号解耦通信。

核心原则：
- **raw_md 是规范数据源** — 结构化字段从 Markdown 解析派生，`MarkdownTaskFormatter.format()` 保证往返稳定
- **Design Tokens 统一配色** — `design_tokens.py` 的 `get_tokens()` 提供语义颜色，暗/亮主题同时适配
- **配置驱动** — `AppConfig`（JSON）集中管理设置，`config_changed` 信号通知热重载

PEP8：模块 `snake_case`，类 `PascalCase`，函数/变量 `snake_case`，常量 `UPPER_SNAKE_CASE`，私有 `_prefix`，Qt 信号过去式动词。

## 通用准则

- **复用优先**：检索开源、可靠、可复用的组件，避免重复造轮子
- **主题适配**：UI 交互、配色严格遵循 `design_tokens.py` 的 `get_tokens()` 令牌体系，亮/暗双主题必须同时适配
- **环境隔离**：开发/生产使用不同数据库和配置
- **文档同步**：功能变更后及时更新 [DESIGN.md](DESIGN.md) 和 [resources/help/manual.html](resources/help/manual.html)（参见上方「工作流程」章节）
