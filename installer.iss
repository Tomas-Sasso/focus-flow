; Instalador de Focus Flow (Inno Setup 6).
;
; No se compila a mano: lo arma `build.py flow --dist`, que pasa la versión y las
; rutas con /D. Para compilarlo suelto:
;
;     ISCC.exe /DAppVersion=1.1.0 /DSourceDir=. /DOutputDir=.\entregas installer.iss
;
; Es una instalación por usuario: va a %LOCALAPPDATA%\Programs\Focus Flow y no
; pide permisos de administrador. Para mandarle el programa a alguien, eso es lo
; que hace la diferencia entre "doble clic y listo" y "pedile la contraseña de
; administrador a quien te prestó la computadora".

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "."
#endif
#ifndef OutputDir
  #define OutputDir "entregas"
#endif

#define AppName "Focus Flow"
#define AppExe "Focus Flow.exe"

[Setup]
; Este identificador no se cambia nunca más: es lo que hace que la próxima
; versión se instale encima de ésta en vez de al lado.
AppId={{4807FE0D-A7AD-4229-9BCA-A71FB19DA074}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppName}
VersionInfoVersion={#AppVersion}

DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

OutputDir={#OutputDir}
OutputBaseFilename={#AppName} {#AppVersion} Setup
SetupIconFile={#SourceDir}\focusflow.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern

; Si Focus Flow está abierto, que lo cierre solo en vez de fallar al copiar.
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; \
    GroupDescription: "Accesos directos:"

[Files]
; Un solo archivo: las tipografías y los sonidos viajan adentro del ejecutable.
; Ojo con agregar acá `portable.txt`: eso mandaría el historial a la carpeta de
; instalación, que es justo la que se borra al desinstalar.
Source: "{#SourceDir}\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Abrir {#AppName}"; \
    Flags: nowait postinstall skipifsilent

; Al desinstalar se borra el programa y nada más. El historial, los ajustes y la
; sesión a medio terminar viven en %LOCALAPPDATA%\Focus Flow y quedan donde
; están: desinstalar para reinstalar más adelante, o para pasar a otra versión,
; no tiene por qué costarte lo que llevás medido.
