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
ChangesAssociations=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\UDIM Tiler\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\UDIM Tiler"; Filename: "{app}\UDIM Tiler.exe"
Name: "{autodesktop}\UDIM Tiler"; Filename: "{app}\UDIM Tiler.exe"; Tasks: desktopicon

[Registry]
; Prosjektfiler (.udimt) åpnes i UDIM Tiler ved dobbeltklikk
Root: HKCU; Subkey: "Software\Classes\.udimt"; ValueType: string; ValueName: ""; ValueData: "UDIMTiler.Project"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\UDIMTiler.Project"; ValueType: string; ValueName: ""; ValueData: "UDIM Tiler project"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\UDIMTiler.Project\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\UDIM Tiler.exe,0"
Root: HKCU; Subkey: "Software\Classes\UDIMTiler.Project\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\UDIM Tiler.exe"" ""%1"""

[Run]
; Starter appen etter installasjon, også etter stille oppdatering
Filename: "{app}\UDIM Tiler.exe"; Description: "Launch UDIM Tiler"; Flags: nowait postinstall
