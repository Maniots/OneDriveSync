<# Validate install, upgrade and uninstall with a separate validation AppId. #>
[CmdletBinding()]
param([string]$Installer)
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
if (-not $Installer) { $Installer = Join-Path $ProjectRoot 'dist\installer\OneDrivePCSync-Validation-Setup.exe' }
$Installer = (Resolve-Path -LiteralPath $Installer).Path
$TestDirectory = Join-Path $ProjectRoot ('build\installer-check-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $TestDirectory | Out-Null
$SetupArguments = @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/TASKS=',('/DIR="' + $TestDirectory + '"'))
function Invoke-CheckedInstaller([string]$File, [string[]]$Arguments) {
    $process = Start-Process -FilePath $File -ArgumentList $Arguments -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw "Installer operation failed: $($process.ExitCode)" }
}
Invoke-CheckedInstaller $Installer $SetupArguments
$InstalledExe = Join-Path $TestDirectory 'OneDrivePCSync.exe'
$ConfigPath = Join-Path $TestDirectory 'validation-data\config.json'
if (-not (Test-Path -LiteralPath $InstalledExe)) { throw 'Installed EXE missing' }
$config = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
if ($config.folders.Count -ne 0) { throw 'Installer embedded personal folders' }
$config.general.dry_run = $true
$config | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $ConfigPath -Encoding UTF8
$OriginalConfig = [System.IO.File]::ReadAllBytes($ConfigPath)
Invoke-CheckedInstaller $Installer $SetupArguments
if ([Convert]::ToBase64String([System.IO.File]::ReadAllBytes($ConfigPath)) -ne [Convert]::ToBase64String($OriginalConfig)) { throw 'Upgrade replaced configuration' }
$env:LOCALAPPDATA = Join-Path $TestDirectory 'test-user'
$ReportPath = Join-Path $TestDirectory 'installed-ui.json'
Invoke-CheckedInstaller $InstalledExe @('--smoke-test', ('"' + $ReportPath + '"'))
$Report = Get-Content -LiteralPath $ReportPath -Raw | ConvertFrom-Json
if (-not $Report.ui_rendered) { throw 'Installed UI did not render' }
Invoke-CheckedInstaller (Join-Path $TestDirectory 'unins000.exe') @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART')
if (Test-Path -LiteralPath $InstalledExe) { throw 'Uninstall left the EXE' }
if ([Convert]::ToBase64String([System.IO.File]::ReadAllBytes($ConfigPath)) -ne [Convert]::ToBase64String($OriginalConfig)) { throw 'Uninstall removed configuration' }
Write-Output "PASS: install, installed UI, upgrade preservation and uninstall preservation ($TestDirectory)"
