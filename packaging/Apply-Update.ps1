<# Detached update installer. Config, history and backups remain user data. #>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Installer,
    [Parameter(Mandatory)][string]$ApplicationExe,
    [Parameter(Mandatory)][int]$ParentPid,
    [Parameter(Mandatory)][ValidatePattern('^[a-f0-9]{64}$')][string]$ExpectedHash,
    [Parameter(Mandatory)][string]$ExpectedVersion,
    [Parameter(Mandatory)][string]$DataDirectory,
    [ValidatePattern('^\\[^\\].+')][string]$TaskFolderPath = '\OneDrivePCSync',
    [switch]$NoRestart,
    [int]$WaitSeconds = 600
)
$ErrorActionPreference = 'Stop'
$ApplicationExe = [IO.Path]::GetFullPath($ApplicationExe)
$InstallDirectory = Split-Path -Parent $ApplicationExe
$UpdateDirectory = Join-Path $DataDirectory 'updates'
New-Item -ItemType Directory -Path $UpdateDirectory -Force | Out-Null
$LogPath = Join-Path $UpdateDirectory 'install.log'
$SavedTasks = @()
$LockStream = $null
$Succeeded = $false

function Write-UpdateLog([string]$Message) {
    [IO.File]::AppendAllText($LogPath, (Get-Date -Format o) + ' ' + $Message + [Environment]::NewLine)
}
function Write-UpdateResult([string]$Status, [string]$Message) {
    $result = @{status=$Status; version=$ExpectedVersion; message=$Message; time=(Get-Date -Format o)} | ConvertTo-Json
    [IO.File]::WriteAllText((Join-Path $UpdateDirectory 'result.json'), $result, (New-Object Text.UTF8Encoding($false)))
}

try {
    if ((Get-FileHash -LiteralPath $Installer -Algorithm SHA256).Hash -ine $ExpectedHash) { throw 'Installer checksum does not match.' }
    Write-UpdateLog "Waiting for application process $ParentPid to exit."
    if ($ParentPid -gt 0) {
        $ParentProcess = Get-Process -Id $ParentPid -ErrorAction SilentlyContinue
        if ($ParentProcess -and -not $ParentProcess.WaitForExit($WaitSeconds * 1000)) { throw 'Application did not exit in time.' }
    }

    $Deadline = (Get-Date).AddSeconds($WaitSeconds)
    $LockPath = Join-Path $DataDirectory 'onedrive_pcsync.lock'
    while (-not $LockStream) {
        $candidate = $null
        try {
            $candidate = [IO.File]::Open($LockPath, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::ReadWrite)
            $candidate.Lock(0, 1)
            $LockStream = $candidate
        } catch {
            if ($candidate) { $candidate.Dispose() }
            if ((Get-Date) -ge $Deadline) { throw 'Synchronization did not finish in time. Please retry the update.' }
            Start-Sleep -Milliseconds 250
        }
    }
    Write-UpdateLog 'Synchronization lock acquired.'
    $TaskService = New-Object -ComObject Schedule.Service
    $TaskService.Connect()
    $TaskFolder = $null
    try { $TaskFolder = $TaskService.GetFolder($TaskFolderPath) } catch {
        if ($_.Exception.HResult -ne -2147024893) { throw } # Folder missing: 0x80070003.
    }
    if ($TaskFolder) {
        foreach ($task in $TaskFolder.GetTasks(1)) {
            if ($task.Definition.Actions.Count -eq 1 -and $task.Definition.Actions.Item(1).Path -ieq $ApplicationExe) {
                $isMonitor = $task.Definition.Actions.Item(1).Arguments -eq '--monitor'
                $SavedTasks += [pscustomobject]@{Task=$task; Enabled=$task.Enabled; Restart=($isMonitor -and $task.State -eq 4)}
                $task.Enabled = $false
                if ($isMonitor) { $task.Stop(0) }
            }
        }
    }
    Write-UpdateLog 'Running the verified installer.'
    $setup = Start-Process -FilePath $Installer -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/TASKS=',('/DIR="' + $InstallDirectory + '"'),('/LOG="' + (Join-Path $UpdateDirectory 'setup.log') + '"')) -WindowStyle Hidden -Wait -PassThru
    if ($setup.ExitCode -ne 0) { throw "Installer failed with exit code $($setup.ExitCode)." }
    $ReportPath = Join-Path $UpdateDirectory 'installed.json'
    $check = Start-Process -FilePath $ApplicationExe -ArgumentList @('--diagnostics',('"' + $ReportPath + '"')) -WindowStyle Hidden -Wait -PassThru
    if ($check.ExitCode -ne 0) { throw 'The installed application failed validation.' }
    $report = Get-Content -LiteralPath $ReportPath -Raw | ConvertFrom-Json
    if ($report.version -ne $ExpectedVersion) { throw 'Installed version does not match the requested update.' }
    Write-UpdateResult 'installed' 'Update installed successfully.'
    # Delete only the verified download staged under this user's updates root.
    $StagedPath = [IO.Path]::GetFullPath($Installer)
    $StagingRoot = [IO.Path]::GetFullPath($UpdateDirectory).TrimEnd('\') + '\'
    if ($StagedPath.StartsWith($StagingRoot, [StringComparison]::OrdinalIgnoreCase)) {
        try { Remove-Item -LiteralPath $StagedPath -Force } catch { Write-UpdateLog ('Could not remove download: ' + $_.Exception.Message) }
    }
    $Succeeded = $true
} catch {
    $FailureMessage = $_.Exception.Message
    Write-UpdateLog $FailureMessage
    Write-UpdateResult 'failed' $FailureMessage
    # Avoid unattended restart/download loops after a failed automatic install.
    [IO.File]::WriteAllText((Join-Path $UpdateDirectory 'preferences.json'), '{"automatic":false}', (New-Object Text.UTF8Encoding($false)))
} finally {
    if ($LockStream) { $LockStream.Unlock(0, 1); $LockStream.Dispose() }
    foreach ($saved in $SavedTasks) {
        try {
            $saved.Task.Enabled = $saved.Enabled
            if ($saved.Restart) { $saved.Task.Run($null) | Out-Null }
        } catch { Write-UpdateLog ('Could not restore task: ' + $_.Exception.Message) }
    }
    if (-not $NoRestart -and (Test-Path -LiteralPath $ApplicationExe -PathType Leaf)) {
        Start-Process -FilePath $ApplicationExe -WorkingDirectory $InstallDirectory -WindowStyle Hidden | Out-Null
    }
}
if (-not $Succeeded) { exit 1 }
