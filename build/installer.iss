; Inno Setup-skript for UDIM Tiler. Bygges av GitHub Actions.
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{676DA81E-4981-461C-BF75-3A6A7AE41FF5}
AppName=UDIM Tiler
AppVersion={#AppVersion}
AppPublisher=highres
DefaultDirName={localappdata}\Programs\UDIM Tiler
DefaultGroupName=UDIM Tiler
DisableProgramGroupPage=yes
; Installeres per bruker, så oppdateringer ikke trenger administrator
PrivilegesRequired=lowest
OutputDir=out
OutputBaseFilename=UDIM-Tiler-Setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\UDIM Tiler.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=force
RestartApplications=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "norwegian"; MessagesFile: "compiler:Languages\Norwegian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\UDIM Tiler\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\UDIM Tiler"; Filename: "{app}\UDIM Tiler.exe"
Name: "{autodesktop}\UDIM Tiler"; Filename: "{app}\UDIM Tiler.exe"; Tasks: desktopicon

[Run]
; Starter appen etter installasjon, også etter stille oppdatering
Filename: "{app}\UDIM Tiler.exe"; Description: "Start UDIM Tiler"; Flags: nowait postinstall
