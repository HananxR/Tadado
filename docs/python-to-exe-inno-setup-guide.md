# Python 项目打包 EXE + Inno Setup 安装程序完整教程

## 一、概述

当你用 Python 开发了一个桌面应用（GUI 或 CLI），最终用户往往没有 Python 环境。你需要把它打包成 `.exe`，再封装为安装程序，用户才能像安装普通 Windows 软件一样使用。

**工具链**：

```
Python 源码 ──[PyInstaller]──▶ .exe + 依赖 ──[Inno Setup]──▶ Setup.exe 安装包
```

**两种分发形态**：

| 形态 | 产物 | 适用场景 |
|------|------|---------|
| 便携版 | `.zip` | 免安装、U 盘携带、绿色软件 |
| 安装版 | `.exe` 安装程序 | 正式分发、开始菜单快捷方式、卸载入口 |

本文基于真实项目的打包经验，涵盖 PyInstaller 配置、Inno Setup 脚本编写、自动化编排，以及常见陷阱的应对方案。

---

## 二、PyInstaller：Python → EXE

### 2.1 安装与基本使用

```bash
pip install pyinstaller
```

最简单的用法：

```bash
pyinstaller main.py
```

这会在 `dist/main/` 目录下生成一个包含 `main.exe` 及所有依赖的文件夹——这就是 `--onedir` 模式（默认）。

#### `--onedir` vs `--onefile`

| 特性 | `--onedir`（推荐） | `--onefile` |
|------|-------------------|-------------|
| 产物 | 一个文件夹，内含 exe + dll + 资源 | 单个 exe 文件 |
| 启动速度 | 快（直接加载） | 慢（每次启动解压到临时目录） |
| 更新友好 | 高（可单独替换文件） | 低（需重新打包整包） |
| 杀软误报 | 较少 | 较多（自解压行为可疑） |
| 分发便利 | 需要 ZIP 打包 | 单文件即用 |

> **推荐**：始终使用 `--onedir`，再通过 Inno Setup 封装为单个安装程序。`--onefile` 仅适合极简单的 CLI 小工具。

---

### 2.2 关键参数详解

#### 控制台窗口

```bash
# GUI 应用（无黑框）
--noconsole

# CLI 工具（保留终端输出）
--console
```

> **注意**：`--noconsole` 会隐藏 `stdout`/`stderr`。务必在代码中做好日志文件记录，否则错误无法被看到。

#### 输出命名与路径

```bash
--name=MyApp                              # exe 文件名
--workpath=build/windows                   # 构建中间文件路径
--distpath=dist/windows                    # 最终产物路径
```

> **实践**：将不同平台的 `workpath` 和 `distpath` 分开（如 `build/windows/`、`build/linux/`），避免交叉污染。

#### 应用图标

```bash
--icon=resources/app.ico                  # Windows：必须 .ico
--icon=resources/app.png                  # Linux/macOS：可用 .png
```

> **注意**：`.ico` 文件应包含多种尺寸（16×16、32×32、48×48、256×256），否则在资源管理器中缩放显示时模糊。

#### 数据文件打包

```bash
# Windows — 分号分隔
--add-data="resources;resources"

# Linux/macOS — 冒号分隔
--add-data="resources:resources"
```

格式为 `"源路径;目标路径"`（Windows）或 `"源路径:目标路径"`（Linux）。目标路径决定了运行时在包内的相对位置。

> **关键**：打包后，数据文件不在原路径下。需要用 `sys._MEIPASS` 定位——细节见 2.4 节。

#### 隐式导入（Hidden Import）

```bash
--hidden-import=PySide6.QtSvg
--hidden-import=src.version
```

PyInstaller 通过静态分析追踪依赖，但某些动态导入（`__import__()`、插件系统、`importlib`）无法被检测到。这些模块需要手动声明。

> **实践**：首次构建后，检查 `build/<name>/warn-<name>.txt`，搜索 `missing module` 关键字。不是所有警告都致命——只关注实际运行时报 `ModuleNotFoundError` 的模块。

#### 清理缓存

```bash
--clean
```

清理 PyInstaller 的缓存（`build/` 目录下的分析结果）。**建议每次发布构建都加上**，避免上次构建的脏状态导致诡异问题。

---

### 2.3 `.spec` 文件 —— 核心配置文件

执行一次 `pyinstaller main.py` 后，PyInstaller 会自动生成 `main.spec`。这个文件是**可编辑的 Python 脚本**，定义了完整的构建规则。

#### 四阶段模型

```
Analysis ──▶ PYZ ──▶ EXE ──▶ COLLECT
  (分析)     (压缩)   (入口)    (收集)
```

```python
# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['main.py'],                           # 入口脚本
    pathex=[],
    binaries=[],
    datas=[('resources', 'resources')],    # 数据文件：(源, 目标)
    hiddenimports=['PySide6.QtSvg', 'src.version'],  # 隐式导入
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],                           # 排除模块（减小体积）
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)                          # 纯 Python 模块压缩

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,                 # DLL 先排除，由 COLLECT 收集
    name='MyApp',
    debug=False,
    strip=False,
    upx=True,                              # 启用 UPX 压缩
    console=False,                         # False = GUI
    icon=['resources/app.ico'],
)

coll = COLLECT(
    exe,
    a.binaries,                            # 动态库
    a.datas,                               # 数据文件
    strip=False,
    upx=True,
    name='MyApp',
)
```

#### spec 文件 vs CLI 参数

| 场景 | 推荐方式 |
|------|---------|
| 一次性试用 | CLI 参数 |
| 项目构建 | **`.spec` 文件（纳入版本控制）** |
| CI/CD 构建 | `.spec` 文件 + CLI 覆盖关键参数 |

`.spec` 文件一旦写好，执行方式为：

```bash
pyinstaller MyApp.spec
```

> **实践**：将 `.spec` 文件纳入 Git，团队成员和 CI 可直接构建，无需记住复杂的 CLI 参数。

---

### 2.4 常见陷阱与解决方案

#### 陷阱一：隐式导入缺失 → `ModuleNotFoundError`

**原因**：PyInstaller 无法检测动态导入、延迟导入、插件系统加载的模块。

**排查**：

```bash
# 查看警告文件
cat build/<name>/warn-<name>.txt | grep "missing module"
```

**解决**：在 `.spec` 的 `hiddenimports` 中显式声明。例如 Qt 的 SVG 支持：

```python
hiddenimports=['PySide6.QtSvg']
```

#### 陷阱二：Qt 插件 DLL 缺失

**症状**：程序启动时报 `Cannot load platform plugin "windows"`。

**原因**：Qt 的平台插件（`qwindows.dll`）、图像格式插件等未被自动收集。

**解决**：手动复制插件目录到输出：

```bash
# Windows
cp -r .venv/Lib/site-packages/PySide6/plugins/platforms dist/MyApp/_internal/PySide6/plugins/
cp -r .venv/Lib/site-packages/PySide6/plugins/imageformats dist/MyApp/_internal/PySide6/plugins/
```

或在 spec 的 `binaries` 中显式添加：

```python
binaries=[
    ('path/to/plugins/platforms/*.dll', 'PySide6/plugins/platforms'),
    ('path/to/plugins/imageformats/*.dll', 'PySide6/plugins/imageformats'),
]
```

#### 陷阱三：资源文件路径错误

**症状**：开发时正常，打包后 `FileNotFoundError`。

**原因**：打包后资源文件被解压到临时目录，不在脚本所在路径。

**解决**：使用 `sys._MEIPASS` 判断运行环境：

```python
import sys
import os

def resource_path(relative_path: str) -> str:
    """获取资源文件的真实路径（兼容开发与打包环境）"""
    if getattr(sys, 'frozen', False):
        # 打包后：资源在 _MEIPASS 临时目录
        base_path = sys._MEIPASS
    else:
        # 开发中：资源在项目根目录
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# 使用
icon_path = resource_path("resources/icons/app.ico")
```

> **关键**：`sys.frozen` 是 PyInstaller 在运行时设置的标志，存在即表示处于打包环境。`sys._MEIPASS` 是资源解压后的临时目录路径。

#### 陷阱四：平台路径分隔符

在 `.spec` 中 `datas` 使用元组：

```python
datas=[('resources', 'resources')]
```

CLI 中则需区分平台：

```bash
# Windows（分号）
--add-data="resources;resources"

# Linux/macOS（冒号）
--add-data="resources:resources"
```

> 建议：统一使用 `.spec` 文件避免分隔符问题。

#### 陷阱五：UPX 压缩导致杀软误报

启用 UPX 压缩能减小 30%~50% 体积，但某些杀毒软件会将 UPX 压缩的 exe 判为可疑。

**折中方案**：

- 发布版不开 UPX（牺牲体积换信任）
- 或关闭 UPX 仅对关键的 exe，保持 DLL 压缩：
  ```python
  exe = EXE(..., upx=False, ...)    # 主 exe 不压缩
  coll = COLLECT(..., upx=True, ...) # DLL 仍可压缩
  ```
- 对构建产物做代码签名（需要购买 EV 证书）

---

### 2.5 完整构建命令示例

```bash
# Windows — 一个真实可用的完整命令
pyinstaller \
    --noconsole \                         # GUI 应用，无黑框
    --name=MyApp \                        # 产物名称
    --workpath=build/windows \            # 中间文件
    --distpath=dist/windows \             # 最终产物
    --add-data="resources;resources" \    # 打包资源文件
    --icon=resources/app.ico \            # 应用图标
    --hidden-import=PySide6.QtSvg \       # 隐式依赖
    --clean \                             # 清理缓存
    main.py                               # 入口
```

---

## 三、Inno Setup：EXE → Windows 安装程序

PyInstaller 产出的是一整个文件夹。Inno Setup 将它封装成一个 `.exe` 安装程序，提供安装向导、桌面快捷方式、开始菜单、卸载入口。

### 3.1 安装工具

从 [jrsoftware.org](https://jrsoftware.org/isdl.php) 下载安装 **Inno Setup**。

推荐同时安装 **Inno Script Studio**（独立的可视化编辑器），可以在 UI 中编辑脚本并实时预览安装界面。

`.iss` 文件由多个 `[Section]` 构成，核心段如下：

| Section | 作用 |
|---------|------|
| `[Setup]` | 安装程序全局配置 |
| `[Languages]` | 安装界面语言 |
| `[Tasks]` | 可选安装任务（勾选框） |
| `[Files]` | 要安装的文件清单 |
| `[Icons]` | 快捷方式 |
| `[Run]` | 安装完成后执行的操作 |
| `[Code]` | Pascal 脚本，用于自定义逻辑 |
| `[Registry]` | 注册表操作 |

### 3.2 `[Setup]` 段 —— 关键配置

```ini
[Setup]
; 唯一标识符 — 用于升级检测，一旦发布切勿修改
AppId={{B8F3A2D1-5E7C-4A9F-B2D3-6E8F1A4C5D7B}}

AppName=MyApp
AppVersion=1.0.0
AppPublisher=YourName

; 安装路径：{autopf} = C:\Program Files，用户可修改
DefaultDirName={autopf}\MyApp

; 开始菜单程序组名
DefaultGroupName=MyApp

; 最低权限 — 无需管理员即可安装（推荐）
PrivilegesRequired=lowest

; 压缩算法 — lzma 是最高压缩率
Compression=lzma
SolidCompression=yes

; 现代向导样式（比经典样式好看很多）
WizardStyle=modern

; 控制面板 → 程序和功能 中的图标
UninstallDisplayIcon={app}\MyApp.exe

; 输出控制
OutputDir=..\dist
OutputBaseFilename=MyApp_setup_v1.0.0
```

**关键点说明**：

- **`AppId`**：GUID，安装程序用它判断是否已安装过。**一旦发布就不要再改**，否则升级安装会变成并排安装两个版本。
- **`PrivilegesRequired=lowest`**：安装到用户目录时不弹 UAC 提权框。如果必须写 `Program Files`，用户会手动选路径，安装程序会自动请求提权。
- **`SolidCompression=yes`**：将所有文件合并为一个压缩块，显著提升压缩率，但会略微增加安装时的解压时间。
- **`WizardStyle=modern`**：启用现代安装向导，视觉效果更好，支持更大的欢迎页面图片。

### 3.3 `[Files]` 段 —— 文件部署与用户数据保护

这是最核心的段，决定哪些文件被安装到哪里。

#### 基础用法

```ini
[Files]
; 将 PyInstaller 产物全部安装到 {app}
Source: "..\dist\windows\MyApp\*"; \
    DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs
```

**Flags 说明**：

| Flag | 含义 |
|------|------|
| `ignoreversion` | 不比较文件版本，始终覆盖（构建产物无版本资源时必需） |
| `recursesubdirs` | 递归复制子目录 |
| `createallsubdirs` | 自动创建目标所需的子目录 |

#### 用户数据保护 —— 关键技巧

PyInstaller 打包后，用户运行程序会产生数据文件（如 SQLite 数据库、配置文件）。升级安装时**不能静默覆盖这些文件**。

**方案**：将数据文件从批量复制中排除，单独声明并加 `confirmoverwrite`：

```ini
[Files]
; 主程序 — 排除用户数据文件
Source: "..\dist\windows\MyApp\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs; \
    Excludes: "userdata.db,config.json"

; 用户数据 — 提示确认后再覆盖
Source: "..\dist\windows\MyApp\_internal\resources\userdata.db"; \
    DestDir: "{app}\_internal\resources"; \
    Flags: confirmoverwrite recursesubdirs createallsubdirs

Source: "..\dist\windows\MyApp\_internal\resources\config.json"; \
    DestDir: "{app}\_internal\resources"; \
    Flags: confirmoverwrite recursesubdirs createallsubdirs
```

> **原理**：`Excludes` 支持逗号分隔的文件名列表（不含路径）。被排除的文件不会在批量复制时写入。然后单独声明这些文件，加 `confirmoverwrite` 标志——当目标已存在时，安装程序弹出对话框让用户确认是否覆盖。

#### PyInstaller `--onedir` 目录结构映射

PyInstaller 产物结构：

```
dist/windows/MyApp/
├── MyApp.exe                  → {app}\MyApp.exe
├── _internal/
│   ├── python3.dll            → {app}\_internal\python3.dll
│   ├── PySide6/               → {app}\_internal\PySide6/
│   ├── ... (所有 DLL、.pyc)
│   └── resources/             → {app}\_internal\resources/
│       ├── userdata.db        → 单独处理（confirmoverwrite）
│       └── ...
└── ...
```

Inno Setup 的 `recursesubdirs` 会自动保持这个目录结构。

### 3.4 `[Icons]` 段 —— 快捷方式

```ini
[Icons]
; 开始菜单程序组中的快捷方式
Name: "{group}\MyApp"; \
    Filename: "{app}\MyApp.exe"

; 卸载入口（放在同一程序组里）
Name: "{group}\卸载 MyApp"; \
    Filename: "{uninstallexe}"

; 桌面快捷方式（由 Tasks 勾选控制）
Name: "{autodesktop}\MyApp"; \
    Filename: "{app}\MyApp.exe"; \
    Tasks: desktopicon
```

**常量说明**：

| 常量 | 实际路径 |
|------|---------|
| `{group}` | 开始菜单 → 程序 → MyApp |
| `{autodesktop}` | 当前用户的桌面 |
| `{app}` | 用户选择的安装目录 |
| `{uninstallexe}` | 卸载程序路径（自动生成） |

### 3.5 `[Tasks]` 段 —— 可选安装任务

配合 `[Icons]` 中的 `Tasks` 条件：

```ini
[Tasks]
Name: "desktopicon"; \
    Description: "创建桌面快捷方式"; \
    GroupDescription: "附加快捷方式:"
```

安装向导中会显示一个带勾选框的页面，用户可以取消桌面快捷方式的创建。

### 3.6 `[Run]` 段 —— 安装后启动

```ini
[Run]
Filename: "{app}\MyApp.exe"; \
    Description: "启动 MyApp"; \
    Flags: nowait postinstall skipifsilent
```

**Flags 说明**：

| Flag | 含义 |
|------|------|
| `nowait` | 不等待程序退出，继续安装流程 |
| `postinstall` | 在安装完成页面显示一个勾选框 |
| `skipifsilent` | 静默安装时跳过（`/VERYSILENT`） |

### 3.7 `[Languages]` 段 —— 多语言

```ini
[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
```

Inno Setup 自带了多种语言的翻译文件。`compiler:` 前缀指向 Inno Setup 安装目录下的语言文件。如果需要非官方语言，可以下载第三方 `.isl` 文件放到 `compiler:Languages\` 目录下。

### 3.8 完整 `.iss` 脚本模板

```ini
#define MyAppName "MyApp"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "YourName"
#define MyAppExeName "MyApp.exe"

[Setup]
AppId={{E7D8A3F1-2B4C-4F5A-9C1D-8E2F6B7A3D5C}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=..\dist
OutputBaseFilename={#MyAppName}_setup_v{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
PrivilegesRequired=lowest
; 架构支持
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; \
    GroupDescription: "Additional shortcuts:"

[Files]
; 主程序（排除用户数据文件）
Source: "..\dist\windows\{#MyAppName}\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs; \
    Excludes: "userdata.db"

; 用户数据 — 提示确认覆盖
Source: "..\dist\windows\{#MyAppName}\_internal\resources\userdata.db"; \
    DestDir: "{app}\_internal\resources"; \
    Flags: confirmoverwrite recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; \
    Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; \
    Description: "Launch {#MyAppName}"; \
    Flags: nowait postinstall skipifsilent
```

> **使用方式**：用 Inno Setup Compiler（`ISCC.exe`）编译：
>
> ```bash
> ISCC.exe installer.iss
> ```

---

## 四、自动化脚本编排

手动一步步执行容易出错，建议用脚本编排整个发布流程。

### 4.1 完整发布流程

```
版本号写入 → PyInstaller 构建 → ZIP 便携版打包 → Inno Setup 安装程序编译 → Git Tag → 发布
```

### 4.2 PowerShell 自动化要点

以下是一个真实可用的发布脚本骨架（基于实际项目简化）：

```powershell
$ErrorActionPreference = "Stop"

# 1. 读取版本号
$Version = (Select-String -Path src\version.py `
    -Pattern '__version__\s*=\s*"([^"]*)"').Matches.Groups[1].Value
$Tag = "v$Version"

# 2. 清理旧产物
Remove-Item -Recurse -Force build\windows, dist\windows -ErrorAction SilentlyContinue

# 3. PyInstaller 构建
uv run pyinstaller `
    --noconsole `
    --name=MyApp `
    --workpath=build\windows `
    --distpath=dist\windows `
    --add-data="resources;resources" `
    --icon=resources/app.ico `
    --hidden-import=PySide6.QtSvg `
    --clean `
    main.py

# 4. ZIP 便携版
$PortableZip = "dist\MyApp_${Tag}_portable.zip"
Compress-Archive -Path dist\windows\MyApp\* -DestinationPath $PortableZip -Force

# 5. Inno Setup 安装程序（自动检测 ISCC.exe 路径）
$IsccPaths = @(
    "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
)
$Iscc = $IsccPaths | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($Iscc) {
    # 动态替换 .iss 中的版本号
    $iss = [System.IO.File]::ReadAllText("installer.iss")
    $iss = $iss -replace '#define MyAppVersion ".*"', `
        "#define MyAppVersion ""$Version"""
    [System.IO.File]::WriteAllText("installer.iss", $iss)

    # 编译
    cmd /c "`"$Iscc`" installer.iss"
    Write-Host "Installer: dist\MyApp_setup_v${Version}.exe"
} else {
    Write-Host "Inno Setup not found, skipping installer"
}

# 6. Git Tag
git tag -f $Tag HEAD
git push origin HEAD:main
git push -f origin $Tag

Write-Host "Done! Upload dist/* to GitHub Release:"
Write-Host "  https://github.com/user/repo/releases/new?tag=$Tag"
```

### 4.3 关键技术点

**动态读取版本号**：不要在脚本中硬编码版本号。从 `version.py`、`pyproject.toml` 或 `package.json` 等单一来源读取。

```powershell
# 从 version.py 正则提取
$VerNum = (Select-String -Path src\version.py `
    -Pattern '__version__\s*=\s*"([^"]*)"').Matches.Groups[1].Value
```

**动态替换 `.iss` 版本**：避免每次发版手动改 `.iss`，改为脚本自动替换：

```powershell
$issContent = $issContent -replace `
    '#define MyAppVersion ".*"', "#define MyAppVersion ""$VerNum"""
```

**检测 Inno Setup 安装路径**：不同机器可能装了不同版本（6/7），安装在 `Program Files` 或 `Program Files (x86)`：

```powershell
$IsccPaths = @(
    "${env:ProgramFiles}\Inno Setup 7\ISCC.exe"
    "${env:ProgramFiles(x86)}\Inno Setup 7\ISCC.exe"
    "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
)
```

---

## 五、最佳实践总结

### 1. 版本号单一来源

版本号只在一处定义（如 `src/version.py`），所有地方从它读取。脚本动态注入到 `.iss`，避免手动改多处导致不一致。

### 2. 构建产物按平台隔离

```
build/
├── windows/     # Windows PyInstaller 中间文件
└── linux/       # Linux 中间文件
dist/
├── windows/     # .exe + .zip + 安装程序
└── linux/       # .tar.gz
```

避免不同平台的中间文件互相污染。

### 3. 用户数据保护

安装程序中**必须**排除用户运行时数据文件，或标记为 `confirmoverwrite`。静默覆盖用户数据是不可接受的。

### 4. `.spec` 文件纳入版本控制

`.spec` 随代码一起维护。CI 和新成员可以直接 `pyinstaller MyApp.spec` 构建，无需低效传递 CLI 参数。

### 5. CI 中至少做构建验证

即使不自动发布，CI 也应该跑一次 PyInstaller 构建，确保代码不会因为新的动态导入而打包失败。

### 6. 杀软误报处理

- 关闭主 exe 的 UPX 压缩可降低误报概率
- 提交到 [Microsoft Defender 误报提交](https://www.microsoft.com/en-us/wdsi/filesubmission) 申请白名单
- 代码签名证书（EV Code Signing）是最彻底的解决方案

### 7. 运行时日志

`--noconsole` 会吞掉所有 stdout/stderr。务必在应用启动早期配置日志文件，否则用户遇到问题你什么都排查不了。

---

## 附：工具速查

| 工具 | 用途 | 链接 |
|------|------|------|
| PyInstaller | Python → EXE | `pip install pyinstaller` |
| Inno Setup | EXE → 安装程序 | [jrsoftware.org/isdl.php](https://jrsoftware.org/isdl.php) |
| Inno Script Studio | ISS 可视化编辑器 | 安装 Inno Setup 时可选安装 |
| Resource Hacker | 编辑 exe 资源（图标、版本信息） | [angusj.com/resourcehacker](http://www.angusj.com/resourcehacker/) |
