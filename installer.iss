; Tadado Windows 安装脚本
; 使用方法:
;   1. 先执行 build.bat (PyInstaller)
;   2. 打开 Inno Setup Compiler，加载此 .iss 文件，点击 Compile

#define MyAppName "Tadado"
#define MyAppVersion "0.2.1"
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
OutputDir=dist\windows
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

[Files]
Source: "dist\windows\Tadado\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent
