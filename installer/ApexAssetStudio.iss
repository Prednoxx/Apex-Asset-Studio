#define MyAppName "Apex Asset Studio"
#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"  ; set by build
#endif
#ifndef StageDir
  #define StageDir "..\build\stage\ApexAssetStudio"  ; set by build
#endif
#define MyAppPublisher "Prednoxx"
#define MyAppExeName "ApexAssetStudio.exe"

[Setup]
AppId={{9D73F9C2-45E2-4CBE-A702-5FA8A4F515D1}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\Apex Asset Studio
PrivilegesRequired=lowest
DefaultGroupName={#MyAppName}
OutputDir=..\..
OutputBaseFilename=ApexAssetStudio_Setup_{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "{#StageDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Apex Asset Studio"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Apex Asset Studio"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Apex Asset Studio"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Remove caches only
Type: filesandordirs; Name: "{localappdata}\ApexAssetStudio\decoded_cache"
Type: filesandordirs; Name: "{localappdata}\ApexAssetStudio\preview_textures_v2"
Type: filesandordirs; Name: "{localappdata}\ApexAssetStudio\preview_textures"
