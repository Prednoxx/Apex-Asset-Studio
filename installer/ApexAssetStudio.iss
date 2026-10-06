#define MyAppName "Apex Asset Studio"
#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"  ; build_windows.bat passes the real version
#endif
#define MyAppPublisher "Apex Asset Studio"
#define MyAppExeName "ApexAssetStudio.exe"

[Setup]
AppId={{9D73F9C2-45E2-4CBE-A702-5FA8A4F515D1}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\Apex Asset Studio
PrivilegesRequired=lowest
DefaultGroupName={#MyAppName}
OutputDir=..\dist\installer
OutputBaseFilename=ApexAssetStudio_Setup_{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "..\dist\native-preview\ApexAssetStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Apex Asset Studio"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Apex Asset Studio"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Apex Asset Studio"; Flags: nowait postinstall skipifsilent
