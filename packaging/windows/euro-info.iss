; Euro Info for Windows: per-user installer (no administrator rights needed).
; Built by build-windows.ps1:  ISCC.exe /DAppVersion=4.0.0 /DSourceDir=dist\euro-info packaging\windows\euro-info.iss

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\..\dist\euro-info"
#endif
#ifndef OutputDir
  #define OutputDir "..\..\dist"
#endif

[Setup]
AppId={{8C1E5B9E-6F3A-4C3D-9E2B-4E5552494E46}
AppName=Euro Info
AppVersion={#AppVersion}
AppVerName=Euro Info {#AppVersion}
AppPublisher=Alex Petre
AppPublisherURL=https://github.com/zmardanian/euro-info
DefaultDirName={localappdata}\Programs\Euro Info
DefaultGroupName=Euro Info
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir={#OutputDir}
OutputBaseFilename=Euro-Info-{#AppVersion}-windows-x64-setup
SetupIconFile=..\..\assets\euro-info.ico
UninstallDisplayIcon={app}\euro-info.exe
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "polish"; MessagesFile: "compiler:Languages\Polish.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Euro Info"; Filename: "{app}\euro-info.exe"
Name: "{group}\{cm:UninstallProgram,Euro Info}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Euro Info"; Filename: "{app}\euro-info.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\euro-info.exe"; Description: "{cm:LaunchProgram,Euro Info}"; Flags: nowait postinstall skipifsilent

; Your library and settings in %APPDATA%\Euro Info and %LOCALAPPDATA%\Euro Info are kept on uninstall.
