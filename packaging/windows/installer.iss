#define AppName "Student Placement Planner"
#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif
#ifndef AppNumericVersion
  #define AppNumericVersion "0.1.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\..\dist\Student Placement Planner"
#endif

[Setup]
AppId={{EE420FA1-5BB2-5AA2-88A7-7FFB44163C3D}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Nathan Klisch
AppPublisherURL=https://github.com/nklisch/student-placement-planner
AppSupportURL=https://github.com/nklisch/student-placement-planner/issues
AppUpdatesURL=https://github.com/nklisch/student-placement-planner/releases
DefaultDirName={localappdata}\Programs\Student Placement Planner
DefaultGroupName=Student Placement Planner
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..\release
OutputBaseFilename=Student-Placement-Planner-{#AppVersion}-Windows-x64-Setup
SetupIconFile=..\..\assets\app-icon.ico
UninstallDisplayIcon={app}\Student Placement Planner.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ChangesAssociations=yes
LicenseFile=..\..\LICENSE
VersionInfoCompany=Nathan Klisch
VersionInfoDescription=Student Placement Planner installer
VersionInfoProductName={#AppName}
VersionInfoVersion={#AppNumericVersion}
VersionInfoProductVersion={#AppNumericVersion}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Student Placement Planner"; Filename: "{app}\Student Placement Planner.exe"
Name: "{autodesktop}\Student Placement Planner"; Filename: "{app}\Student Placement Planner.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Classes\.spp"; ValueType: string; ValueName: ""; ValueData: "StudentPlacementPlanner.Project"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\StudentPlacementPlanner.Project"; ValueType: string; ValueName: ""; ValueData: "Student Placement Planner project"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\StudentPlacementPlanner.Project\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\Student Placement Planner.exe,0"
Root: HKCU; Subkey: "Software\Classes\StudentPlacementPlanner.Project\shell\open\command"; ValueType: string; ValueName: ""; ValueData: "\"{app}\Student Placement Planner.exe\" \"%1\""

[Run]
Filename: "{app}\Student Placement Planner.exe"; Description: "Launch Student Placement Planner"; Flags: nowait postinstall skipifsilent
