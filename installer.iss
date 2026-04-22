[Setup]
AppId={{A7F3E1C2-4B8D-4A5F-9C3E-2D6B1F8E0A4B}}
AppName=Media Utilities
AppVersion={#AppVersion}
AppPublisher=Omniclouds
DefaultDirName={autopf}\media-utilities
DefaultGroupName=Media Utilities
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\MediaUtility.exe
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=yes
VersionInfoVersion={#AppVersion}
VersionInfoTextVersion={#AppVersion}
VersionInfoCompany=Omniclouds
VersionInfoProductName=Media Utilities
OutputBaseFilename=MediaUtility_Setup

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\MediaUtility\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Media Utilities"; Filename: "{app}\MediaUtility.exe"; IconFilename: "{app}\MediaUtility.exe"
Name: "{group}\{cm:UninstallProgram,Media Utilities}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Media Utilities"; Filename: "{app}\MediaUtility.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\MediaUtility.exe"; Description: "{cm:LaunchProgram,Media Utilities}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
; NOTE: {userappdata}\media-utilities is intentionally NOT listed — user data preserved
