# CLAUDE.md

Tadado 项目指导文件。详细设计文档见 [DESIGN.md](DESIGN.md)，更新日志见 [CHANGELOG.md](CHANGELOG.md)。

## 项目概览

Tadado — Windows 桌面任务管理工具，Python 3.10 + PySide6，Markdown 语法定义任务，SQLite + FTS5 存储，配备日历热力图。

## 发布流程

每次发版按以下步骤执行：

```bash
# 1. 更新版本号
#    编辑 src/version.py，修改 __version__ 为新版本号

# 2. 更新 changelog
#    编辑 CHANGELOG.md，在顶部新增版本条目（Added / Changed / Fixed / Removed）

# 3. 提交版本变更
git add src/version.py CHANGELOG.md
git commit -m "release: vX.Y.Z.W"

# 4. 执行发布脚本（编译 + 打包 + tag + push）
powershell -File release.ps1 v0.1.2.3

# 5. 在浏览器打开的 GitHub Release 页面拖入 dist/ 下的文件，点击 Publish
```

注意事项：
- **installer.iss 必须 UTF-8 with BOM** — `release.ps1` 已通过 .NET `UTF8Encoding($true)` 保证，手动编辑后需确认编码
- `release.ps1` 会强制更新 tag 到 HEAD、push main + tag，无需手动 git push
- 如果 GitHub Release 对比为空，检查 tag 是否指向最新 commit：`git rev-list -1 vX.Y.Z.W`

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

# 打包：执行 build.bat（PyInstaller standalone），安装版额外用 Inno Setup 编译 installer.iss
```

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
- **文档同步**：代码变更后及时更新 DESIGN.md 和 CHANGELOG
