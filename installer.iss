[Setup]
AppId={{A7F3E1C2-4B8D-4A5F-9C3E-2D6B1F8E0A4B}}
AppName=Videl
AppVersion={#AppVersion}
AppPublisher=videl
DefaultDirName={autopf}\Videl
DefaultGroupName=Videl
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\Videl.exe
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
; Detect running instance and close it before upgrade
AppMutex=VidelAppMutex
CloseApplications=yes
CloseApplicationsFilter=Videl.exe
RestartApplications=no
VersionInfoVersion={#AppVersion}
VersionInfoTextVersion={#AppVersion}
VersionInfoCompany=videl
VersionInfoProductName=Videl
OutputBaseFilename=Videl_Setup

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; recursesubdirs covers runtime\ and manifests\ shipped under dist\Videl\_internal\.
; AI packages are installed at runtime into %LOCALAPPDATA%\Videl\ai_packages — no Dirs entry needed.
Source: "dist\Videl\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Browser extension shipped at the install root so users can find it next to
; Videl.exe and load it unpacked in their browser.
Source: "browser_extension\*"; DestDir: "{app}\browser_extension"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Videl"; Filename: "{app}\Videl.exe"; IconFilename: "{app}\Videl.exe"
Name: "{group}\{cm:UninstallProgram,Videl}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Videl"; Filename: "{app}\Videl.exe"; Tasks: desktopicon
Name: "{group}\Browser Extension Folder"; Filename: "{app}\browser_extension"; IconFilename: "{app}\Videl.exe"; Comment: "Open the Videl browser extension folder"

[Run]
Filename: "{app}\Videl.exe"; Description: "{cm:LaunchProgram,Videl}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
; NOTE: {userappdata}\media-utilities is intentionally NOT listed — user data preserved
