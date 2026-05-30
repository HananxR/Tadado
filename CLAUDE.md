# CLAUDE.md

本文件为 Claude Code 在 DeskTodoSeq 仓库中工作时提供指导。详细设计文档见 [详设说明.md](详设说明.md)，开发进度见 [项目进度.md](项目进度.md)。

## 项目概览

DeskTodoSeq — Windows 桌面任务管理工具，Python 3.10 + PySide6，Markdown 语法定义任务，SQLite + FTS5 存储，配备日历热力图。

## 常用命令

```bash
# 环境
uv venv --python 3.10 .venv && uv sync --dev

# 运行
uv run python main.py

# 测试
uv run pytest                                      # 全部 57 用例
uv run pytest -k "round_trip"                      # 关键字匹配

# 代码质量
uv run black src/ tests/ && uv run ruff check src/ tests/

# 打包：执行 build.bat（Nuitka standalone），安装版额外用 Inno Setup 编译 installer.iss
```

## 架构摘要

四层：`src/ui/` → `src/services/` → `src/models/` → SQLite，模块间通过 `SignalBus`（[src/utils/signal_bus.py](src/utils/signal_bus.py)）Qt 信号解耦通信。

核心原则：
- **raw_md 是规范数据源** — 结构化字段从 Markdown 解析派生，`MarkdownTaskFormatter.format()` 保证往返稳定
- **Design Tokens 统一配色** — `design_tokens.py` 的 `get_tokens()` 提供语义颜色，暗/亮主题同时适配
- **配置驱动** — `AppConfig`（JSON）集中管理设置，`config_changed` 信号通知热重载

PEP8：模块 `snake_case`，类 `PascalCase`，函数/变量 `snake_case`，常量 `UPPER_SNAKE_CASE`，私有 `_prefix`，Qt 信号过去式动词。

## 工作流程规则

### 1. 新功能开发

1. 先检索 [详设说明.md](详设说明.md)，确认是否已有相关模块
2. **无匹配**：按「需求 → 预览效果（含布局标注）→ 详细实现方案」编写设计文档，让用户确认效果后再开发
3. **有匹配**：标注为功能优化，走规则 2

### 2. 功能优化

功能优化需慎重评估，避免单一模块改动导致关联功能失效：

1. **明确标注**：时间线、优化功能、与历史需求的冲突点、推荐实现方案
2. **评估影响**：列出所有关联模块，逐一检查兼容性，有争议或不确定时让用户确认
3. **确认后执行**：
   - 先更新 [详设说明.md](详设说明.md)（设计文档先行）
   - 开发 → 自测（`timeout 5 uv run python main.py` 启动 + 功能验证）
   - 用户测试确认 → 总结优化内容 → `git commit` 备份
   - 更新 [项目进度.md](项目进度.md)（记录优化时间、原因、影响范围）

### 3. 通用准则

- **复用优先**：检索开源、可靠、可复用的组件，避免重复造轮子；推荐成熟设计方案，兼顾全局扩展性
- **主题适配**：UI 交互、配色严格遵循 `design_tokens.py` 的 `get_tokens()` 令牌体系，亮/暗双主题必须同时适配
- **全局一致**：Config 相关配置验证全局生效，需求不明主动向用户确认
- **环境隔离**：生产环境仅「功能演示分区」，打包以生产环境为准；开发/生产使用不同数据库和配置
- **文档同步**：[CLAUDE.md](CLAUDE.md)、[详设说明.md](详设说明.md)、[项目进度.md](项目进度.md) 任何变更后必须及时更新并 `git commit` 备份，确保三份文档始终反映项目最新状态

### 4. 测试与备份

1. 自测通过后告知用户"自测完成"，由用户测试确认
2. 用户确认问题已解决后，**必须先 `git commit` 提交代码作为备份**，再进行下一个任务
