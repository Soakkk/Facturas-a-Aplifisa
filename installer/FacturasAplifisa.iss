; Instalador de "Facturas a Aplifisa".
; Requiere haber compilado antes con PyInstaller (carpeta dist\FacturasAplifisa).
; Compilar con: ISCC.exe FacturasAplifisa.iss

#define MyAppName "Facturas a Aplifisa"
#ifndef MyAppVersion
  #define MyAppVersion "1.4.0"
#endif
#define MyAppPublisher "Asesoria E. Marin"
#define MyAppExeName "FacturasAplifisa.exe"

[Setup]
AppId={{7D3C9E51-4B2F-4A86-B1D4-FACTAPLIF15A}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\FacturasAplifisa
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist_installer
OutputBaseFilename=FacturasAplifisa_Setup_{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=yes
PrivilegesRequired=lowest
SetupIconFile=..\assets\app.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el Escritorio"; GroupDescription: "Accesos directos:"

[Files]
Source: "..\dist\FacturasAplifisa\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir {#MyAppName}"; Flags: nowait postinstall skipifsilent
Filename: "{app}\{#MyAppExeName}"; Flags: nowait skipifnotsilent
