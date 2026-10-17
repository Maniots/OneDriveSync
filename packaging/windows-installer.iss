#define AppName "OneDrive PC Sync"
#include "build-version.iss"
#define AppExe "OneDrivePCSync.exe"
#ifdef ValidationBuild
  #define InstallerAppId "{{4B0E3CEC-590C-44E8-A819-FDA7F10DDAF8}"
  #define DataDirectory "{app}\validation-data"
  #define StartupValueName "OneDrivePCSync-Validation"
#else
  #define InstallerAppId "{{B7E79167-2292-4B36-9AF7-678418DA1C5D}"
  #define DataDirectory "{localappdata}\OneDrivePCSync"
  #define StartupValueName "OneDrivePCSync"
#endif

[Setup]
AppId={#InstallerAppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=OneDrive PC Sync
DefaultDirName={localappdata}\Programs\OneDrivePCSync
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist\installer
#ifdef ValidationBuild
OutputBaseFilename=OneDrivePCSync-Validation-Setup
#else
OutputBaseFilename=OneDrivePCSync-Setup-{#AppVersion}
#endif
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableWelcomePage=no
DisableDirPage=no
UninstallDisplayIcon={app}\{#AppExe}
CloseApplications=yes
RestartApplications=no
SetupLogging=yes

[Languages]
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:DesktopShortcut}"; Flags: unchecked
Name: "automation"; Description: "{cm:SyncAutomation}"; Flags: unchecked

[CustomMessages]
italian.DesktopShortcut=Crea un collegamento sul desktop
english.DesktopShortcut=Create a desktop shortcut
italian.SyncAutomation=Abilita sincronizzazione all'accesso, al blocco, ogni 15 minuti e allo spegnimento
english.SyncAutomation=Enable synchronization at sign-in, on lock, every 15 minutes and at shutdown
italian.LaunchApplication=Avvia %1
english.LaunchApplication=Launch %1

[Files]
Source: "..\dist\OneDrivePCSync\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "default-config.json"; DestDir: "{#DataDirectory}"; DestName: "config.json"; Flags: onlyifdoesntexist uninsneveruninstall

#ifndef ValidationBuild
[Icons]
Name: "{userprograms}\{#AppName}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"
Name: "{userprograms}\{#AppName}\Configurazione"; Filename: "{localappdata}\OneDrivePCSync\config.json"
Name: "{userprograms}\{#AppName}\Disinstalla"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Tasks: desktopicon
#endif

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchApplication,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\Setup-ShutdownMonitor.ps1"" -Uninstall -ApplicationExe ""{app}\{#AppExe}"""; Flags: runhidden waituntilterminated; RunOnceId: "RemoveMonitor"
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\Setup-ScheduledTasks.ps1"" -Uninstall -ApplicationExe ""{app}\{#AppExe}"""; Flags: runhidden waituntilterminated; RunOnceId: "RemoveSyncTasks"

[Code]
procedure RegisterAutomationScript(ScriptName: String);
var
  ResultCode: Integer;
  Parameters: String;
begin
  Parameters := '-NoProfile -ExecutionPolicy Bypass -File "' +
    ExpandConstant('{app}\') + ScriptName + '" -ApplicationExe "' +
    ExpandConstant('{app}\{#AppExe}') + '"';
  if not Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    Parameters, ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    RaiseException('Impossibile avviare la configurazione delle attivita automatiche.');
  if ResultCode <> 0 then
    RaiseException('Configurazione delle attivita automatiche non riuscita. Eseguire ' +
      ScriptName + ' dalla cartella di installazione per vedere i dettagli.');
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  StartupCommand: String;
begin
  if (CurUninstallStep = usUninstall) and
     RegQueryStringValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run',
                         '{#StartupValueName}', StartupCommand) then begin
    if CompareText(StartupCommand, '"' + ExpandConstant('{app}\{#AppExe}') + '"') = 0 then
      RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', '{#StartupValueName}');
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if (CurStep = ssPostInstall) and WizardIsTaskSelected('automation') then begin
    RegisterAutomationScript('Setup-ScheduledTasks.ps1');
    RegisterAutomationScript('Setup-ShutdownMonitor.ps1');
  end;
  if CurStep = ssPostInstall then begin
    if not Exec(ExpandConstant('{app}\{#AppExe}'),
                '--record-install "' + ExpandConstant('{#DataDirectory}') + '"',
                ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ResultCode) then
      RaiseException('Impossibile registrare lo storico aggiornamenti.');
    if ResultCode <> 0 then
      RaiseException('Registrazione dello storico aggiornamenti non riuscita.');
  end;
end;
