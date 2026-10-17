<# Validate install, upgrade and uninstall with a separate validation AppId. #>
[CmdletBinding()]
param([string]$Installer, [string]$BaselineInstaller, [string]$PythonExe)
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
if (-not $Installer) { $Installer = Join-Path $ProjectRoot 'dist\installer\EverySync-Validation-Setup.exe' }
$Installer = (Resolve-Path -LiteralPath $Installer).Path
if ($BaselineInstaller) { $BaselineInstaller = (Resolve-Path -LiteralPath $BaselineInstaller).Path }
else { $BaselineInstaller = $Installer }
if (-not $PythonExe) { $PythonExe = Join-Path $ProjectRoot '.venv\Scripts\python.exe' }
$PythonExe = (Resolve-Path -LiteralPath $PythonExe).Path
$TestDirectory = Join-Path $ProjectRoot ('build\installer-check-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $TestDirectory | Out-Null
$SetupArguments = @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/TASKS=',('/DIR="' + $TestDirectory + '"'))
function Invoke-CheckedInstaller([string]$File, [string[]]$Arguments) {
    $process = Start-Process -FilePath $File -ArgumentList $Arguments -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw "Installer operation failed: $($process.ExitCode)" }
}
Invoke-CheckedInstaller $BaselineInstaller $SetupArguments
$InstalledExe = Join-Path $TestDirectory 'OneDrivePCSync.exe'
$ConfigPath = Join-Path $TestDirectory 'validation-data\config.json'
if (-not (Test-Path -LiteralPath $InstalledExe)) { throw 'Installed EXE missing' }
$UninstallKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{4B0E3CEC-590C-44E8-A819-FDA7F10DDAF8}_is1'
$StartMenu = Join-Path $TestDirectory 'validation-shortcuts\Start Menu'
$Desktop = Join-Path $TestDirectory 'validation-shortcuts\Desktop'
if (Test-Path -LiteralPath (Join-Path $Desktop 'EverySync.lnk')) { throw 'Unrequested desktop shortcut created' }
# Old validation installers excluded shortcuts. Simulate the known legacy
# production links in validation-only locations to check the same migration.
$LegacyGroup = Join-Path $StartMenu 'OneDrive PC Sync'
New-Item -ItemType Directory -Force $LegacyGroup,$Desktop | Out-Null
$Shell = New-Object -ComObject WScript.Shell
foreach ($Link in @(
    @((Join-Path $LegacyGroup 'OneDrive PC Sync.lnk'), $InstalledExe),
    @((Join-Path $LegacyGroup 'Configurazione.lnk'), $ConfigPath),
    @((Join-Path $LegacyGroup 'Disinstalla.lnk'), (Join-Path $TestDirectory 'unins000.exe')),
    @((Join-Path $Desktop 'OneDrive PC Sync.lnk'), $InstalledExe)
)) {
    $Shortcut = $Shell.CreateShortcut($Link[0])
    $Shortcut.TargetPath = $Link[1]
    $Shortcut.Save()
}
$UnrelatedShortcut = Join-Path $LegacyGroup 'user-owned.txt'
Set-Content -LiteralPath $UnrelatedShortcut -Value 'Preserve user files'
$HistoryPath = Join-Path $TestDirectory 'validation-data\updates\history.sqlite3'
if (-not (Test-Path -LiteralPath $HistoryPath)) { throw 'Installer did not record installation history' }
$config = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
if ($config.folders.Count -ne 0) { throw 'Installer embedded personal folders' }
$config.general.dry_run = $true
$config | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $ConfigPath -Encoding UTF8
$OriginalConfig = [System.IO.File]::ReadAllBytes($ConfigPath)
$RunKey = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey('Software\Microsoft\Windows\CurrentVersion\Run')
$StartupValue = 'OneDrivePCSync-Validation'
$StartupCommand = '"' + $InstalledExe + '"'
if ($null -ne $RunKey.GetValue($StartupValue)) { $RunKey.Dispose(); throw 'A validation startup entry already exists' }
try {
$RunKey.SetValue($StartupValue, $StartupCommand, [Microsoft.Win32.RegistryValueKind]::String)
Invoke-CheckedInstaller $Installer $SetupArguments
$VersionInfo = (Get-Item -LiteralPath $InstalledExe).VersionInfo
if ($VersionInfo.ProductName -cne 'EverySync' -or $VersionInfo.FileDescription -cne 'EverySync') { throw 'Installed EXE has incorrect product branding' }
if ((Get-ItemProperty -LiteralPath $UninstallKey).DisplayName -notlike 'EverySync*') { throw 'Uninstall entry has incorrect product branding' }
if (-not (Test-Path -LiteralPath (Join-Path $StartMenu 'EverySync\EverySync.lnk'))) { throw 'EverySync Start menu shortcut missing' }
if (-not (Test-Path -LiteralPath (Join-Path $Desktop 'EverySync.lnk'))) { throw 'Upgrade lost the existing desktop shortcut choice' }
if (Test-Path -LiteralPath (Join-Path $Desktop 'OneDrive PC Sync.lnk')) { throw 'Upgrade left the legacy desktop shortcut' }
foreach ($Name in @('OneDrive PC Sync.lnk','Configurazione.lnk','Disinstalla.lnk')) {
    if (Test-Path -LiteralPath (Join-Path $LegacyGroup $Name)) { throw "Upgrade left legacy shortcut $Name" }
}
if ((Get-Content -LiteralPath $UnrelatedShortcut -Raw).Trim() -cne 'Preserve user files') { throw 'Upgrade removed unrelated Start menu content' }
if ([Convert]::ToBase64String([System.IO.File]::ReadAllBytes($ConfigPath)) -ne [Convert]::ToBase64String($OriginalConfig)) { throw 'Upgrade replaced configuration' }
if ($RunKey.GetValue($StartupValue) -cne $StartupCommand) { throw 'Upgrade changed startup registration' }
& $PythonExe -c "import sqlite3,sys; db=sqlite3.connect(sys.argv[1]); rows=db.execute('SELECT previous_version,version,changes FROM installations ORDER BY id').fetchall(); assert len(rows)==2 and rows[1][0]==rows[0][1] and rows[1][2], rows" $HistoryPath
if ($LASTEXITCODE -ne 0) { throw 'Upgrade did not append installation history' }
$env:LOCALAPPDATA = Join-Path $TestDirectory 'test-user'
$ReportPath = Join-Path $TestDirectory 'installed-ui.json'
Invoke-CheckedInstaller $InstalledExe @('--smoke-test', ('"' + $ReportPath + '"'))
$Report = Get-Content -LiteralPath $ReportPath -Raw | ConvertFrom-Json
if (-not $Report.ui_rendered) { throw 'Installed UI did not render' }
Invoke-CheckedInstaller (Join-Path $TestDirectory 'unins000.exe') @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART')
if (Test-Path -LiteralPath $InstalledExe) { throw 'Uninstall left the EXE' }
if (Test-Path -LiteralPath (Join-Path $Desktop 'EverySync.lnk')) { throw 'Uninstall left the desktop shortcut' }
if (Test-Path -LiteralPath (Join-Path $StartMenu 'EverySync\EverySync.lnk')) { throw 'Uninstall left the Start menu shortcut' }
if ($null -ne $RunKey.GetValue($StartupValue)) { throw 'Uninstall left startup registration' }
if (-not (Test-Path -LiteralPath $HistoryPath)) { throw 'Uninstall removed installation history' }
if ([Convert]::ToBase64String([System.IO.File]::ReadAllBytes($ConfigPath)) -ne [Convert]::ToBase64String($OriginalConfig)) { throw 'Uninstall removed configuration' }
Write-Output "PASS: EverySync branding; legacy shortcut migration; desktop choice; installed UI; config/startup upgrade preservation; uninstall cleanup ($TestDirectory)"
} finally {
    if ($RunKey.GetValue($StartupValue) -ceq $StartupCommand) { $RunKey.DeleteValue($StartupValue, $false) }
    $RunKey.Dispose()
}
