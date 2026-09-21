# 贡献指南

感谢你对 Tadado 的关注！

## 如何贡献

### 报告 Bug

请在 [Issues](https://github.com/HananxR/Tadado/issues) 中提交，包含：

- 操作系统版本（Windows 10/11）
- 应用版本与分支（`main` = Tauri 桌面端；`archive/pyversion` = 旧 PySide6 版）
- 错误信息或截图
- 复现步骤

### 提交代码

1. Fork 本仓库
2. 创建功能分支：`git checkout -b feature/my-feature`
3. 确保构建与冒烟都通过：`cd desktop && npm run build && npm run e2e`（CI 跑的就是这两条）
4. 桌面端还没有 lint / format / 测试脚本，改完请对着 `resources/ui-mockup/tadado-2.0.html` 核一遍视觉差异
5. 提交并推送，创建 Pull Request

### 开发环境

```bash
cd desktop
npm install
npm run dev          # 纯前端预览
npm run tauri dev    # 真实窗口（首次需编译 Rust，约 1–2 分钟）
```

### 代码规范

- TypeScript：函数与变量 `camelCase`，类型 `PascalCase`，常量 `UPPER_SNAKE_CASE`
- 不引框架：建节点一律走 `src/shell/dom.ts` 的 `el()`
- 颜色与几何不从零发明 —— 色值取自 `src/styles/tokens.css`，几何对齐 `resources/ui-mockup/tadado-2.0.html`
- 旧 Python 版（`archive/pyversion` 分支）的规范见该分支上的本文件

详见 [CLAUDE.md](CLAUDE.md) 技术架构摘要。
