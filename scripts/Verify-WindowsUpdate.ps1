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
$env:EVERYSYNC_VALIDATION_INSTANCE = [guid]::NewGuid().ToString('N')
$DataDirectory = Join-Path $env:LOCALAPPDATA 'OneDrivePCSync'
$TaskFolderPath = '\OneDrivePCSyncUpdateValidation_' + [guid]::NewGuid().ToString('N')
$ApplicationExe = Join-Path $InstallDirectory 'OneDrivePCSync.exe'
$TaskService = New-Object -ComObject Schedule.Service
$TaskService.Connect()
. (Join-Path $PSScriptRoot 'Validation-TaskIsolation.ps1')
$LockStream = $null
$helper = $null
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class UpdateWindowValidation {
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr window);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr window, int command);
}
'@
function Get-TestApplication {
    @(Get-Process -Name OneDrivePCSync -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $ApplicationExe })
}
function Wait-VisibleApplication {
    $deadline = (Get-Date).AddSeconds(30)
    do {
        $applications = @(Get-TestApplication)
        foreach ($application in $applications) {
            if ($application.MainWindowHandle -ne [IntPtr]::Zero -and [UpdateWindowValidation]::IsWindowVisible($application.MainWindowHandle)) { return $application }
        }
        Start-Sleep -Milliseconds 100
    } while ((Get-Date) -lt $deadline)
    throw 'Updated application did not open a visible window'
}
function Invoke-CheckedProcess([string]$File, [string[]]$Arguments) {
    $process = Start-Process $File -ArgumentList $Arguments -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw "Process failed: $File, exit=$($process.ExitCode)" }
}
function Invoke-TaskSetup([string]$Name, [switch]$Uninstall) {
    $arguments = @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"' + (Join-Path $ProjectRoot $Name) + '"'),'-ApplicationExe',('"' + $ApplicationExe + '"'),'-TaskFolderPath',$TaskFolderPath)
    if ($Uninstall) { $arguments += '-Uninstall' }
    Invoke-CheckedProcess 'powershell.exe' $arguments
    if (-not $Uninstall) {
        Disable-ValidationTaskTriggers $TaskService $TaskFolderPath $ApplicationExe
    }
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
    $HelperArguments = @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"' + (Join-Path $ProjectRoot 'packaging/Apply-Update.ps1') + '"'),'-Installer',('"' + $StagedInstaller + '"'),'-ApplicationExe',('"' + $ApplicationExe + '"'),'-ParentPid','0','-ExpectedHash',$Hash,'-ExpectedVersion',$ExpectedVersion,'-DataDirectory',('"' + $DataDirectory + '"'),'-TaskFolderPath',$TaskFolderPath,'-WaitSeconds','60')
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
    $VersionInfo = (Get-Item -LiteralPath $ApplicationExe).VersionInfo
    if ($VersionInfo.ProductName -cne 'EverySync' -or $VersionInfo.FileDescription -cne 'EverySync') { throw 'Updated EXE has incorrect product branding' }
    if ($VersionInfo.ProductVersion -cne $ExpectedVersion) { throw 'Updated EXE has incorrect product version' }
    if ([Convert]::ToBase64String([IO.File]::ReadAllBytes($ConfigPath)) -ne $OriginalConfiguration) { throw 'Update replaced user configuration' }
    if ($folder.GetTask('OneDrivePCSync - Startup (Download)').Enabled) { throw 'Update enabled a previously disabled task' }
    if (-not $folder.GetTask('OneDrivePCSync - Periodic Upload').Enabled) { throw 'Update disabled an enabled task' }
    if (-not $folder.GetTask('OneDrivePCSync - Shutdown Monitor').Enabled) { throw 'Update disabled the monitor task' }
    if (Test-Path -LiteralPath $StagedInstaller) { throw 'Successful update left the large staged download' }
    $application = Wait-VisibleApplication
    $applicationId = $application.Id
    [UpdateWindowValidation]::ShowWindow($application.MainWindowHandle, 0) | Out-Null
    if ([UpdateWindowValidation]::IsWindowVisible($application.MainWindowHandle)) { throw 'Could not reproduce hidden native window' }
    # A second launch must reactivate the existing GUI, even with SW_HIDE.
    $activation = Start-Process -FilePath $ApplicationExe -WindowStyle Hidden -PassThru
    if (-not $activation.WaitForExit(30000)) { throw 'Second launch did not activate the existing instance' }
    $restored = Wait-VisibleApplication
    if ($restored.Id -ne $applicationId -or @(Get-TestApplication).Count -ne 1) { throw 'Activation replaced or duplicated the running instance' }
    Stop-Process -Id $applicationId -Force
    $restored.WaitForExit()
    # The first update still uses the helper shipped in the older installation.
    $legacyRestart = Start-Process -FilePath $ApplicationExe -WindowStyle Hidden -PassThru
    $legacyVisible = Wait-VisibleApplication
    if ($legacyVisible.Id -ne $legacyRestart.Id) { throw 'Legacy hidden launch did not recover its window' }
    Write-Output "PASS: detached install; sync lock wait; visible restart; hidden-window reactivation; legacy hidden launch; single instance; config preservation; four task enabled states; staged cleanup ($TestRoot)"
} finally {
    if ($LockStream) { $LockStream.Unlock(0,1); $LockStream.Dispose() }
    if ($helper -and -not $helper.HasExited -and -not $helper.WaitForExit(30000)) {
        # This process and its installer children belong only to this fixture.
        # Stop them before uninstall so they cannot install/restart afterwards.
        & taskkill.exe /PID $helper.Id /T /F | Out-Null
        $helper.WaitForExit()
    }
    # Only this fixture's executable, with empty dry-run config, may be stopped.
    Get-TestApplication | Stop-Process -Force
    if (Test-Path -LiteralPath $ApplicationExe) {
        Invoke-TaskSetup 'Setup-ShutdownMonitor.ps1' -Uninstall
        Invoke-TaskSetup 'Setup-ScheduledTasks.ps1' -Uninstall
    }
    try { $TaskService.GetFolder('\').DeleteFolder($TaskFolderPath.TrimStart('\'),0) } catch { }
    $uninstaller = Join-Path $InstallDirectory 'unins000.exe'
    if (Test-Path -LiteralPath $uninstaller) { Invoke-CheckedProcess $uninstaller @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART') }
}
