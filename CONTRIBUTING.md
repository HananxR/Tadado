# 贡献指南

感谢你对 Tadado 的关注！

## 如何贡献

### 报告 Bug

请在 [Issues](https://github.com/HananxR/Tadado/issues) 中提交，包含：

- 操作系统版本（Windows 10/11）
- Python 版本（3.10+）
- 错误信息或截图
- 复现步骤

### 提交代码

1. Fork 本仓库
2. 创建功能分支：`git checkout -b feature/my-feature`
3. 确保测试通过：`uv run pytest`
4. 确保代码格式正确：`uv run black src/ tests/ && uv run ruff check src/ tests/`
5. 提交并推送，创建 Pull Request

### 开发环境

```bash
uv venv --python 3.10 .venv
uv sync --dev
uv run python main.py
```

### 代码规范

- Python 3.10+，遵循 PEP 8
- 模块 `snake_case`，类 `PascalCase`，函数/变量 `snake_case`
- 常量 `UPPER_SNAKE_CASE`，私有 `_prefix`
- Qt 信号使用过去式动词
- UI 配色通过 `design_tokens.py` 的 `get_tokens()` 引用

详见 [CLAUDE.md](CLAUDE.md) 技术架构摘要。
