; Installateur Windows de Wealfy — compile par Inno Setup 6.
;
;   ISCC.exe installer.iss           (build_exe.py s'en charge)
;
; La version est passee par build_exe.py depuis app/version.py, source unique :
; ISCC /DMyAppVersion=1.0.0. La valeur ci-dessous n'est qu'un repli si le
; fichier est compile a la main.

#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif

#define MyAppName      "Wealfy"
#define MyAppPublisher "Wealfy"
#define MyAppExeName   "Wealfy.exe"

[Setup]
; GUID propre a cette application : c'est lui qui permet a Windows de
; reconnaitre une mise a jour au lieu d'installer un second exemplaire.
; NE JAMAIS le changer entre deux versions — pas meme au changement de nom :
; c'est ce GUID inchange qui fait de Wealfy une mise a jour de l'installation
; existante, et non un second logiciel installe a cote du premier.
AppId={{7F3C2A64-9E1B-4D58-A0C7-2B5E8F14D390}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
VersionInfoVersion={#MyAppVersion}

DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
; Application mono-utilisateur : si l'installation par machine n'est pas
; possible sans elevation, Inno bascule seul vers une installation par
; utilisateur au lieu d'echouer sur une demande d'admin.
PrivilegesRequiredOverridesAllowed=dialog
DisableProgramGroupPage=yes

OutputDir=dist
OutputBaseFilename=Setup_{#MyAppName}
SetupIconFile=app\static\img\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; \
  GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}";           Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Desinstaller {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}";     Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; \
  Description: "{cm:LaunchProgram,{#MyAppName}}"; \
  Flags: nowait postinstall skipifsilent

; Rien dans [UninstallDelete] : la desinstallation retire le programme, jamais
; les donnees. La base et les sauvegardes vivent dans %LOCALAPPDATA%\Patrimoine
; et doivent survivre a une reinstallation ou a une mise a jour.
