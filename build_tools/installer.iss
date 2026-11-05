; Inno Setup 6.5+ script -> dist\RepoBrain-Windows-Setup.exe
; Build: ISCC /DAppVersion=1.2.3 build_tools\installer.iss
#ifndef AppVersion
  #define AppVersion "1.0.7"
#endif
#define AppName "Repo Brain"
#define AppExe "RepoBrain.exe"
#define AppURL "https://github.com/madara1150/repo-brain"

[Setup]
AppId={{4C1B7E2A-9D3F-4E61-8A57-2F0B6C9D1E84}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Tanathip
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
DefaultDirName={autopf}\Repo Brain
DefaultGroupName=Repo Brain
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=RepoBrain-Windows-Setup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/ultra64
SolidCompression=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
WizardStyle=modern
VersionInfoVersion={#AppVersion}
VersionInfoCompany=Tanathip
VersionInfoDescription={#AppName} Setup
VersionInfoProductName={#AppName}
VersionInfoCopyright=Copyright (c) 2026 Tanathip

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "thai"; MessagesFile: "compiler:Languages\Thai.isl"

[Messages]
english.WelcomeLabel2=Give Claude Desktop your team's code and shared knowledge.%n%n  •  Index GitHub repositories (Odoo aware)%n  •  Update only when you press the button%n  •  Shared team notes everyone can add to%n%nSetup will install [name/ver] on your computer.
thai.WelcomeLabel2=ให้ Claude Desktop รู้จักโค้ดและข้อมูลของทีมคุณ%n%n  •  อ่านโค้ดจาก GitHub (เข้าใจโครงสร้าง Odoo)%n  •  อัปเดตเมื่อกดปุ่มเท่านั้น%n  •  ข้อมูลทีมที่ทุกคนเพิ่มได้และเห็นร่วมกัน%n%nโปรแกรมจะติดตั้ง [name/ver] ลงในเครื่องของคุณ

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\RepoBrain\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\Repo Brain"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\Repo Brain"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
; started by the in-app updater (/SILENT): reopen the app when the update is done
Filename: "{app}\{#AppExe}"; Flags: nowait skipifnotsilent
