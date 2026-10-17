<# Test the detached updater with isolated installs, data and scheduled tasks. #>
[CmdletBinding()]
param([Parameter(Mandatory)][string]$BaselineInstaller,
      [Parameter(Mandatory)][string]$UpdateInstaller,
      [Parameter(Mandatory)][string]$ExpectedVersion)
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BaselineInstaller = (Resolve-Path -LiteralPath $BaselineInstaller).Path
$UpdateInstaller = (Resolve-Path -LiteralPath $UpdateInstaller).Path
$TestRoot = Join-Path $ProjectRoot ('build\update-install-' + [guid]::NewGuid().ToString('N'))
$InstallDirectory = Join-Path $TestRoot 'app'
$env:LOCALAPPDATA = Join-Path $TestRoot 'user'
$DataDirectory = Join-Path $env:LOCALAPPDATA 'OneDrivePCSync'
$TaskFolderPath = '\OneDrivePCSyncUpdateValidation_' + [guid]::NewGuid().ToString('N')
$ApplicationExe = Join-Path $InstallDirectory 'OneDrivePCSync.exe'
$TaskService = New-Object -ComObject Schedule.Service
$TaskService.Connect()
$LockStream = $null
function Invoke-CheckedProcess([string]$File, [string[]]$Arguments) {
    $process = Start-Process $File -ArgumentList $Arguments -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw "Process failed: $File, exit=$($process.ExitCode)" }
}
function Invoke-TaskSetup([string]$Name, [switch]$Uninstall) {
    $arguments = @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"' + (Join-Path $ProjectRoot $Name) + '"'),'-ApplicationExe',('"' + $ApplicationExe + '"'),'-TaskFolderPath',$TaskFolderPath)
    if ($Uninstall) { $arguments += '-Uninstall' }
    Invoke-CheckedProcess 'powershell.exe' $arguments
}
try {
    New-Item -ItemType Directory -Path $DataDirectory -Force | Out-Null
    Invoke-CheckedProcess $BaselineInstaller @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/TASKS=',('/DIR="' + $InstallDirectory + '"'))
    $ConfigPath = Join-Path $DataDirectory 'config.json'
    Copy-Item -LiteralPath (Join-Path $ProjectRoot 'packaging/default-config.json') -Destination $ConfigPath
    $config = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
    $config.general.dry_run = $true
    [IO.File]::WriteAllText($ConfigPath, ($config | ConvertTo-Json -Depth 10), (New-Object Text.UTF8Encoding($false)))
    $OriginalConfiguration = [Convert]::ToBase64String([IO.File]::ReadAllBytes($ConfigPath))
    Invoke-TaskSetup 'Setup-ScheduledTasks.ps1'
    Invoke-TaskSetup 'Setup-ShutdownMonitor.ps1'
    $folder = $TaskService.GetFolder($TaskFolderPath)
    $StartupTask = $folder.GetTask('OneDrivePCSync - Startup (Download)')
    $StartupTask.Enabled = $false
    # Do not run scheduler actions: they inherit the real user's environment,
    # not this script's isolated LOCALAPPDATA. Frozen monitor behavior is
    # exercised separately by verify_windows_bundle.py with isolated data.
    $StageDirectory = Join-Path $DataDirectory 'updates/staged-validation'
    New-Item -ItemType Directory -Path $StageDirectory -Force | Out-Null
    $StagedInstaller = Join-Path $StageDirectory 'setup.exe'
    Copy-Item -LiteralPath $UpdateInstaller -Destination $StagedInstaller
    $Hash = (Get-FileHash -LiteralPath $StagedInstaller -Algorithm SHA256).Hash.ToLower()
    $HelperArguments = @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"' + (Join-Path $ProjectRoot 'packaging/Apply-Update.ps1') + '"'),'-Installer',('"' + $StagedInstaller + '"'),'-ApplicationExe',('"' + $ApplicationExe + '"'),'-ParentPid','0','-ExpectedHash',$Hash,'-ExpectedVersion',$ExpectedVersion,'-DataDirectory',('"' + $DataDirectory + '"'),'-TaskFolderPath',$TaskFolderPath,'-NoRestart','-WaitSeconds','60')
    $LockPath = Join-Path $DataDirectory 'onedrive_pcsync.lock'
    $LockStream = [IO.File]::Open($LockPath, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::ReadWrite)
    $LockStream.Lock(0, 1)
    $helper = Start-Process powershell.exe -ArgumentList $HelperArguments -WindowStyle Hidden -PassThru
    Start-Sleep -Milliseconds 2000
    if ($helper.HasExited -or (Test-Path -LiteralPath (Join-Path $DataDirectory 'updates/setup.log'))) { throw 'Updater did not wait for synchronization lock' }
    $LockStream.Unlock(0, 1)
    $LockStream.Dispose()
    $LockStream = $null
    if (-not $helper.WaitForExit(60000)) { throw 'Detached updater did not finish' }
    if ($helper.ExitCode -ne 0) {
        Get-Content -LiteralPath (Join-Path $DataDirectory 'updates/install.log')
        throw "Detached updater failed: $($helper.ExitCode)"
    }
    $result = Get-Content -LiteralPath (Join-Path $DataDirectory 'updates/result.json') -Raw | ConvertFrom-Json
    if ($result.status -ne 'installed' -or $result.version -ne $ExpectedVersion) { throw 'Wrong update result' }
    if ([Convert]::ToBase64String([IO.File]::ReadAllBytes($ConfigPath)) -ne $OriginalConfiguration) { throw 'Update replaced user configuration' }
    if ($folder.GetTask('OneDrivePCSync - Startup (Download)').Enabled) { throw 'Update enabled a previously disabled task' }
    if (-not $folder.GetTask('OneDrivePCSync - Periodic Upload').Enabled) { throw 'Update disabled an enabled task' }
    if (-not $folder.GetTask('OneDrivePCSync - Shutdown Monitor').Enabled) { throw 'Update disabled the monitor task' }
    if (Test-Path -LiteralPath $StagedInstaller) { throw 'Successful update left the large staged download' }
    Write-Output "PASS: detached install; sync lock wait; config preservation; four task enabled states; staged cleanup ($TestRoot)"
} finally {
    if ($LockStream) { $LockStream.Unlock(0,1); $LockStream.Dispose() }
    if (Test-Path -LiteralPath $ApplicationExe) {
        Invoke-TaskSetup 'Setup-ShutdownMonitor.ps1' -Uninstall
        Invoke-TaskSetup 'Setup-ScheduledTasks.ps1' -Uninstall
    }
    try { $TaskService.GetFolder('\').DeleteFolder($TaskFolderPath.TrimStart('\'),0) } catch { }
    $uninstaller = Join-Path $InstallDirectory 'unins000.exe'
    if (Test-Path -LiteralPath $uninstaller) { Invoke-CheckedProcess $uninstaller @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART') }
}
