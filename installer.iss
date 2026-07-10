; ============================================================================
; StemTube Desktop — Inno Setup Script
; ============================================================================
; Creates a Windows installer (.exe) for StemTube Desktop.
;
; Prerequisites:
;   1. Run `python build_windows.py --portable` first to create the
;      distributable package in dist/StemTube_Desktop_Portable/
;   2. Install Inno Setup 6+ from https://jrsoftware.org/isinfo.php
;   3. Open this file in Inno Setup Compiler and click Build
;
; The installer will:
;   - Copy all application files + bundled Python venv
;   - Create Start Menu and Desktop shortcuts
;   - Register an uninstaller
;   - Optionally install Node.js if not present
;   - Set up file associations (future)
;
; Output: dist/StemTube_Pro_Setup.exe
; ============================================================================

[Setup]
AppName=StemTube Desktop
AppVersion=1.0.0
AppPublisher=StemTube
AppPublisherURL=https://github.com/your-repo/stemtube-desktop
DefaultDirName={autopf}\StemTube Desktop
DefaultGroupName=StemTube Desktop
OutputDir=dist
OutputBaseFilename=StemTube_Pro_Setup
; Uncomment and set path to your icon file:
; SetupIconFile=static\icons\icon-512x512.ico
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DisableProgramGroupPage=yes
LicenseFile=LICENSE
UninstallDisplayIcon={app}\static\icons\icon-512x512.png
; Minimum Windows 10
MinVersion=10.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Types]
Name: "full"; Description: "Full installation (recommended)"
Name: "compact"; Description: "Compact installation (download models later)"
Name: "custom"; Description: "Custom installation"; Flags: iscustom

[Components]
Name: "main"; Description: "StemTube Desktop Application"; Types: full compact custom; Flags: fixed
Name: "models"; Description: "Pre-download AI models (~4GB)"; Types: full

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Application files from the portable build
Source: "dist\StemTube_Pro_Portable\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\StemTube Desktop"; Filename: "{app}\StemTube Desktop.bat"; IconFilename: "{app}\static\icons\icon-512x512.png"; Comment: "Launch StemTube Desktop"
Name: "{group}\Uninstall StemTube Desktop"; Filename: "{uninstallexe}"
Name: "{autodesktop}\StemTube Desktop"; Filename: "{app}\StemTube Desktop.bat"; IconFilename: "{app}\static\icons\icon-512x512.png"; Tasks: desktopicon

[Run]
; Post-install: download models if selected
Filename: "{app}\venv\Scripts\python.exe"; Parameters: "-c ""from demucs.pretrained import get_model; get_model('htdemucs_6s')"""; StatusMsg: "Downloading Demucs AI model..."; Components: models; Flags: runhidden
Filename: "{app}\venv\Scripts\python.exe"; Parameters: "-c ""from faster_whisper import WhisperModel; WhisperModel('medium', device='cpu', compute_type='int8')"""; StatusMsg: "Downloading Whisper AI model..."; Components: models; Flags: runhidden

; Launch after install
Filename: "{app}\StemTube Desktop.bat"; Description: "Launch StemTube Desktop"; Flags: nowait postinstall skipifsilent shellexec

[UninstallDelete]
; Clean up generated files
Type: filesandordirs; Name: "{app}\flask_session"
Type: filesandordirs; Name: "{app}\logs"
Type: filesandordirs; Name: "{app}\core\downloads"
Type: files; Name: "{app}\stemtubes.db"
Type: files; Name: "{app}\.secret_key"
Type: filesandordirs; Name: "{app}\__pycache__"

[Code]
// Check for Node.js and warn if missing
function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
begin
  Result := True;

  // Check Node.js
  if not Exec('node', '--version', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
  begin
    if MsgBox(
      'Node.js was not found on your system.' + #13#10 +
      'Node.js 20+ may be required for some features.' + #13#10 + #13#10 +
      'You can install it later from https://nodejs.org/' + #13#10 + #13#10 +
      'Continue installation without Node.js?',
      mbConfirmation, MB_YESNO) = IDNO then
    begin
      Result := False;
    end;
  end;
end;
