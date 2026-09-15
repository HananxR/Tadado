; Tadado Windows 安装脚本
; 使用方法:
;   1. 先执行 build.bat (PyInstaller)
;   2. 打开 Inno Setup Compiler，加载此 .iss 文件，点击 Compile

#define MyAppName "Tadado"
#define MyAppVersion "0.2.7"
#define MyAppPublisher "HananxR"
#define MyAppExeName "Tadado.exe"

[Setup]
AppId={{B8F3A2D1-5E7C-4A9F-B2D3-6E8F1A4C5D7B}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=..\dist\windows
OutputBaseFilename=Tadado_setup_v{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
PrivilegesRequired=lowest

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加快捷方式:"
Name: "keepdata"; Description: "保留现有用户数据（推荐）"; GroupDescription: "数据选项:"

[Files]
; 主程序（排除 tadado.data；内置字体仅 Linux 需要，Windows 安装包剔除 -27MB）
Source: "..\dist\windows\Tadado\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "tadado.data,fonts\NotoSansCJKsc-Regular.otf,fonts\NotoColorEmoji.ttf"

; 保留用户数据 → 仅首次安装时写入
Source: "..\dist\windows\Tadado\_internal\resources\tadado.data"; DestDir: "{app}\_internal\resources"; Flags: onlyifdoesntexist; Check: IsTaskSelected('keepdata')

; 不保留用户数据 → 始终覆盖
Source: "..\dist\windows\Tadado\_internal\resources\tadado.data"; DestDir: "{app}\_internal\resources"; Flags: ignoreversion; Check: not IsTaskSelected('keepdata')

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent
