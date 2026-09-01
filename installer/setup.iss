; setup.iss â€” Inno Setup script para Asistente C3D
; Genera un instalador Ãºnico que copia:
;   1. Asistente C3D.exe (app Python) en Program Files\Asistente C3D
;   2. AsistenteC3D.bundle (plugin Civil 3D) en
;      Program Files\Autodesk\ApplicationPlugins\AsistenteC3D.bundle
;      (ruta "trusted" por defecto de AutoCAD â€” el plugin carga sin fricciÃ³n
;      aunque SECURELOAD estÃ© en 1 o 2).
;
; Requisito: ejecutar build_plugin.bat ANTES de compilar este .iss
; Compilar: abrir este archivo en Inno Setup Compiler y dar Build.

#define MyAppName "Asistente C3D"
#define MyAppVersion "1.0.1"
#define MyAppPublisher "GVR Engineering"
#define MyAppExeName "Asistente C3D.exe"
#define MyAppBundle "AsistenteC3D.bundle"

[Setup]
AppId={{B8F3A1C2-7D4E-4F5A-9E6B-1C2D3E4F5A6B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=AsistenteC3D-Setup-{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64
; admin es OBLIGATORIO para escribir en Program Files\Autodesk\ApplicationPlugins
PrivilegesRequired=admin
UninstallDisplayName={#MyAppName}
CloseApplications=force
CloseApplicationsFilter=acad.exe

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el Escritorio"; GroupDescription: "Iconos adicionales:"; Flags: unchecked

[Files]
; --- App Python (exe standalone) ---
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

; --- Plugin Civil 3D (bundle completo) ---
; Se instala en Program Files\Autodesk\ApplicationPlugins â€” ruta confiable de
; AutoCAD, se carga automÃ¡ticamente sin necesidad de tocar TRUSTEDPATHS.
Source: "{#MyAppBundle}\PackageContents.xml"; DestDir: "{commonpf64}\Autodesk\ApplicationPlugins\{#MyAppBundle}"; Flags: ignoreversion
Source: "{#MyAppBundle}\Contents\*"; DestDir: "{commonpf64}\Autodesk\ApplicationPlugins\{#MyAppBundle}\Contents"; Flags: ignoreversion recursesubdirs

; Script de diagnÃ³stico (opcional): permite al usuario correr `diagnostico.ps1` si el plugin no carga
Source: "{#MyAppBundle}\diagnostico.ps1"; DestDir: "{commonpf64}\Autodesk\ApplicationPlugins\{#MyAppBundle}"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; Asociar la extensiÃ³n .digproj a Asistente C3D. Con esto:
;  Â· doble clic sobre un .digproj abre la app pasÃ¡ndole la ruta (main.py lo lee de sys.argv[1])
;  Â· el Explorador muestra el archivo con nombre "Proyecto Asistente C3D" e Ã­cono del exe
;  Â· deja de ser detectado como .zip en el navegador (registra MIME propio)
Root: HKCR; Subkey: ".digproj"; ValueType: string; ValueName: ""; ValueData: "AsistenteC3D.Project"; Flags: uninsdeletevalue
Root: HKCR; Subkey: ".digproj"; ValueType: string; ValueName: "Content Type"; ValueData: "application/x-asistentec3d-project"; Flags: uninsdeletevalue
Root: HKCR; Subkey: "AsistenteC3D.Project"; ValueType: string; ValueName: ""; ValueData: "Proyecto Asistente C3D"; Flags: uninsdeletekey
Root: HKCR; Subkey: "AsistenteC3D.Project\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"
Root: HKCR; Subkey: "AsistenteC3D.Project\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""

[UninstallDelete]
Type: files; Name: "{commonpf64}\Autodesk\ApplicationPlugins\{#MyAppBundle}\Contents\*"
Type: dirifempty; Name: "{commonpf64}\Autodesk\ApplicationPlugins\{#MyAppBundle}\Contents"
Type: files; Name: "{commonpf64}\Autodesk\ApplicationPlugins\{#MyAppBundle}\*"
Type: dirifempty; Name: "{commonpf64}\Autodesk\ApplicationPlugins\{#MyAppBundle}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Code]
function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
begin
  Result := True;
  if Exec('tasklist', '/FI "IMAGENAME eq acad.exe" /NH', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
  begin
    // tasklist siempre retorna 0; la detecciÃ³n real usa CloseApplications arriba.
    // Este bloque es un aviso extra por si CloseApplications no alcanza.
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  // Inno Setup 6 con CloseApplications=force cerrarÃ¡ acad.exe automÃ¡ticamente.
  // Si el usuario cancela el cierre, Inno Setup aborta la instalaciÃ³n.
end;
