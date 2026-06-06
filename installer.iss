; Tadado Windows 安装脚本
; 使用方法:
;   1. 先执行: build.bat (PyInstaller)
;   2. 打开 Inno Setup Compiler，加载此 .iss 文件，点击 Compile

#define MyAppName "Tadado"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "Han.X.Yun"
#define MyAppExeName "Tadado.exe"

[Setup]
AppId={{B8F3A2D1-5E7C-4A9F-B2D3-6E8F1A4C5D7B}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=dist
OutputBaseFilename=Tadado_Setup_v{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
PrivilegesRequired=lowest

[Languages]
; 默认英文（始终可用）。如需中文安装界面，从 Inno Setup 官网下载 ChineseSimplified.isl
; 放入 Inno Setup 安装目录的 Languages 文件夹，然后取消下面注释：
; Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加快捷方式:"

[Files]
Source: "dist\Tadado\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent
