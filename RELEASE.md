# 打包与发布指南

## 目录

- [前置条件](#前置条件)
- [方式一：本地打包 + 手动发布](#方式一本地方打包--手动发布)
- [方式二：GitHub Actions 自动发布（推荐）](#方式二github-actions-自动发布推荐)
- [本地 Inno Setup 编译（可选）](#本地-inno-setup-编译可选)
- [版本号更新清单](#版本号更新清单)

---

## 前置条件

```bash
# 环境准备
uv venv --python 3.10 .venv
uv sync --dev

# 确认测试全部通过
uv run pytest
```

---

## 方式一：本地打包 + 手动发布

### 1. 本地打包

```bash
.\build.bat
```

`build.bat` 自动完成：

1. 清理旧的 build/dist 目录
2. 备份开发数据库（`resources/tadado.data`、`config.json`）
3. 运行 `scripts/create_package_db.py` 生成预制演示数据
4. 调用 PyInstaller 打包为 `dist/Tadado/Tadado.exe`
5. 恢复开发数据库

### 2. 手动创建 GitHub Release

1. 打开仓库 → **Releases** → **Create a new release**
2. 填写信息：

| 字段 | 内容 |
|------|------|
| Tag | `v1.0.0`（版本号） |
| Title | `Tadado v1.0.0` |
| Description | 贴入 [CHANGELOG.md](CHANGELOG.md) 中对应版本的内容 |

3. 上传文件：
   - `dist/Tadado/` 压缩为 ZIP
   - 如有 Inno Setup 编译的 `.exe`，一并上传
4. 点击 **Publish release**

---

## 方式二：GitHub Actions 自动发布（推荐）

### 触发机制

推送 `v` 开头的 tag 即可，无需本地打包：

```bash
git push origin main
git tag v1.0.0
git push origin v1.0.0    # ← 推送 tag 即触发 CI
```

### CI 自动执行流程

```
┌─────────────────────────────────────────────┐
│ ① Checkout 代码                              │
│ ② Setup Python 3.10 + uv                     │
│ ③ uv sync 安装依赖                           │
│ ④ pytest 运行全部测试                        │
│ ⑤ 生成预制 package 数据库                    │
│ ⑥ PyInstaller 打包为 Tadado.exe              │
│ ⑦ choco 安装 Inno Setup                      │
│ ⑧ 编译 Tadado_setup_vX.X.X.exe 安装包       │
│ ⑨ 压缩便携版 ZIP                             │
│ ⑩ 创建 Release + 上传安装包 + ZIP            │
└─────────────────────────────────────────────┘
```

### 发布产物

每次打 tag 后，Release 页面自动包含两个下载项：

| 文件 | 说明 |
|------|------|
| `Tadado_setup_vX.X.X.exe` | Inno Setup 安装包（开始菜单、桌面快捷方式、卸载入口） |
| `Tadado_vX.X.X_portable.zip` | 便携版，解压即用 |

### CI 配置文件

- [`.github/workflows/test.yml`](.github/workflows/test.yml) — 每次 push/PR 自动 lint + 测试
- [`.github/workflows/release.yml`](.github/workflows/release.yml) — tag 推送时自动构建 + 发布（含 Inno Setup）

### 发布后检查

1. 打开仓库 → **Actions** 确认 workflow 运行成功
2. 打开仓库 → **Releases** 确认安装包和便携版均可下载
3. 下载安装包 + 便携版分别验证功能

---

## 本地 Inno Setup 编译（可选）

CI 已自动编译安装包，以下仅用于本地调试安装包效果。

1. 下载安装 [Inno Setup](https://jrsoftware.org/isinfo.php)（免费）
2. 先执行 `build.bat` 生成 `dist/Tadado/`
3. 命令行编译：

```bash
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
```

或打开 Inno Setup Compiler → 加载 `installer.iss` → **Compile**。输出：`dist/Tadado_setup_vX.X.X.exe`

---

## 版本号更新清单

发布新版本前，确保以下文件的版本号一致：

| 文件 | 位置 | 当前版本 |
|------|------|----------|
| `installer.iss` | `#define MyAppVersion "0.1.0"` | 0.1.0 |
| [README.md](README.md) | Badge `version-v1.0.0-blue` | v1.0.0 |
| [resources/help/manual.html](resources/help/manual.html) | `<p>v1.0.0 &mdash; ...` | v1.0.0 |
| [src/ui/dialogs/about_dialog.py](src/ui/dialogs/about_dialog.py) | `ver = QLabel("v1.0.0 ...")` | v1.0.0 |
| `pyproject.toml` | `version = "0.1.0"` | 0.1.0 |
| [CHANGELOG.md](CHANGELOG.md) | 新增版本条目 | — |

> 提示：后续可以用脚本自动同步版本号，避免手动多处修改。
