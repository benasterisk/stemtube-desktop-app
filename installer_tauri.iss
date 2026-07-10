; StemTube Desktop — Tauri Edition Installer
; Inno Setup 6+ script
; Bundles: Tauri shell (stemtube-desktop.exe) + PyInstaller backend (stemtube-backend/)

#define MyAppName "StemTube Desktop"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "StemTube"
#define MyAppExeName "stemtube-desktop.exe"

[Setup]
AppId={{B7E2F8A1-4C3D-4E5F-9A2B-1D3C5E7F9A2B}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename=StemTube_Pro_Setup
Compression=lzma2/ultra64
SolidCompression=yes
LZMANumBlockThreads=4
SetupIconFile=src-tauri\icons\icon.ico
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DiskSpanning=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Tauri shell
Source: "src-tauri\target\release\stemtube-desktop.exe"; DestDir: "{app}"; Flags: ignoreversion

; Backend (PyInstaller output)
Source: "dist\stemtube-backend\*"; DestDir: "{app}\stemtube-backend"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch StemTube Desktop"; Flags: nowait postinstall skipifsilent
