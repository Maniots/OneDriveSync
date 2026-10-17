<#
.SYNOPSIS
    One-time setup script that registers a Windows Scheduled Task to run the
    OneDrivePCSync shutdown monitor at logon.

.DESCRIPTION
    Run this script once to create a scheduled task that starts the shutdown
    monitor when the user logs on. The monitor runs in the background and
    waits for a Windows shutdown signal to trigger an upload sync.

    The task runs hidden (no console window) and uses the project's Python
    interpreter (preferring the virtual environment's pythonw.exe).

    IMPORTANT: This script does NOT modify the existing startup or shutdown
    sync tasks (those are managed by Setup-ScheduledTasks.ps1). It only adds
    a new task for the shutdown monitor.

    The script is idempotent: re-running it safely replaces any previously
    registered monitor task.

.PARAMETER Uninstall
    Removes the OneDrivePCSync shutdown monitor scheduled task instead of
    creating it.

.EXAMPLE
    Right-click this file in Explorer -> "Run with PowerShell".

.EXAMPLE
    From a PowerShell prompt in the project folder:
        powershell -ExecutionPolicy Bypass -File .\Setup-ShutdownMonitor.ps1

.EXAMPLE
    Remove the task later:
        powershell -ExecutionPolicy Bypass -File .\Setup-ShutdownMonitor.ps1 -Uninstall
#>

[CmdletBinding()]
param(
    [switch]$Uninstall,
    [string]$ApplicationExe,
    [ValidatePattern('^\\[^\\].+')]
    [string]$TaskFolderPath = "\OneDrivePCSync"
)

$ErrorActionPreference = "Stop"

# --- Constants ----------------------------------------------------------------
$ProjectRoot      = $PSScriptRoot
$MonitorTaskName  = "OneDrivePCSync - Shutdown Monitor"
$MonitorTaskDescription = "Runs the EverySync shutdown monitor at logon to catch Windows session-ending notifications (shutdown, restart, logoff) and trigger an upload sync."

# Task Scheduler COM API constants.
$TASK_TRIGGER_LOGON                 = 9
$TASK_ACTION_EXEC                   = 0
$TASK_LOGON_INTERACTIVE_TOKEN       = 3
$TASK_RUNLEVEL_LUA                  = 0    # least-privilege - no admin rights needed
$TASK_CREATE_OR_UPDATE              = 6
$TASK_INSTANCES_IGNORE_NEW          = 2    # skip a run if the previous one is still going

function Write-Info($msg) { Write-Host "[i] $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "[OK] $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "[!] $msg" -ForegroundColor Yellow }
function Write-Err($msg)  { Write-Host "[X] $msg" -ForegroundColor Red }

$TaskService = New-Object -ComObject Schedule.Service
$TaskService.Connect()

function Remove-ExistingTask {
    param([string]$Name)
    try {
        $folder = $TaskService.GetFolder($TaskFolderPath)
        if ($ApplicationExe) {
            $task = $folder.GetTask($Name)
            if ($task.Definition.Actions.Item(1).Path -ine $ApplicationExe) {
                Write-Info "Preserving task owned by another installation: $Name"
                return
            }
            $task.Stop(0)
        }
        $folder.DeleteTask($Name, 0)
        Write-Info "Removed existing task: $Name"
    } catch {
        # Folder or task did not exist yet - nothing to remove, not an error.
    }
}

function Get-OrCreateTaskFolder {
    try {
        return $TaskService.GetFolder($TaskFolderPath)
    } catch {
        $root = $TaskService.GetFolder("\")
        return $root.CreateFolder($TaskFolderPath.Trim("\"))
    }
}

# --- Uninstall path -------------------------------------------------------
if ($Uninstall) {
    Write-Info "Uninstalling EverySync shutdown monitor scheduled task..."
    Remove-ExistingTask -Name $MonitorTaskName
    Write-Ok "Uninstall complete."
    return
}

# --- Install path -----------------------------------------------------------
Write-Info "Project root detected as: $ProjectRoot"

if ($ApplicationExe) {
    $ApplicationExe = [System.IO.Path]::GetFullPath($ApplicationExe)
    if (-not (Test-Path -LiteralPath $ApplicationExe -PathType Leaf)) {
        throw "Application executable not found: $ApplicationExe"
    }
    $ProjectRoot = Split-Path -Parent $ApplicationExe
    Write-Ok "Using installed executable: $ApplicationExe"
} else {

# Locate a Python interpreter. Preference order:
#   1. Project-local virtual environment (pythonw.exe - no console flash)
#   2. Project-local virtual environment (python.exe)
#   3. pythonw.exe / python.exe on PATH
$CandidatePythons = @(
    (Join-Path $ProjectRoot ".venv\Scripts\pythonw.exe"),
    (Join-Path $ProjectRoot ".venv\Scripts\python.exe"),
    "pythonw.exe",
    "python.exe"
)

$PythonExe = $null
foreach ($candidate in $CandidatePythons) {
    if (Test-Path $candidate -PathType Leaf) {
        $PythonExe = (Resolve-Path $candidate).Path
        break
    }
    $resolved = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($resolved) {
        $PythonExe = $resolved.Source
        break
    }
}

if (-not $PythonExe) {
    Write-Err "Could not find a Python interpreter (checked .venv\Scripts and PATH)."
    Write-Err "Install Python or create a virtual environment first, then re-run this script."
    exit 1
}

# If we ended up with python.exe (console-allocating) rather than pythonw.exe
# (no console window), check whether a pythonw.exe sibling exists right next
# to it and prefer that instead - this avoids a console window flashing on
# screen every time a task runs.
if ((Split-Path $PythonExe -Leaf) -ieq "python.exe") {
    $SiblingPythonw = Join-Path (Split-Path $PythonExe -Parent) "pythonw.exe"
    if (Test-Path $SiblingPythonw -PathType Leaf) {
        Write-Info "Found pythonw.exe next to python.exe - using it to avoid console window flashes."
        $PythonExe = (Resolve-Path $SiblingPythonw).Path
    } else {
        Write-Warn "No pythonw.exe found next to python.exe - a console window may briefly"
        Write-Warn "flash each time a task runs. To fix: ensure pythonw.exe exists at"
        Write-Warn "$(Split-Path $PythonExe -Parent), then re-run this script."
    }
}
Write-Ok "Using Python interpreter: $PythonExe"

$MonitorScript = Join-Path $ProjectRoot "src\shutdown_monitor.py"
if (-not (Test-Path $MonitorScript -PathType Leaf)) {
    Write-Err "shutdown_monitor.py not found at: $MonitorScript"
    Write-Err "Run this script from inside the EverySync project folder."
    exit 1
}

# --- Generate the hidden-run wrapper (reuse RunHidden.vbs if exists) ---------
# We can reuse the existing RunHidden.vbs from the main setup script.
$RunHiddenVbsPath = Join-Path $ProjectRoot "RunHidden.vbs"
if (-not (Test-Path $RunHiddenVbsPath -PathType Leaf)) {
    Write-Err "RunHidden.vbs not found. Run Setup-ScheduledTasks.ps1 first to generate it."
    exit 1
}
Write-Ok "Using hidden-run wrapper: $RunHiddenVbsPath"

$WscriptExe = (Get-Command wscript.exe -ErrorAction SilentlyContinue).Source
if (-not $WscriptExe) {
    $WscriptExe = Join-Path $env:SystemRoot "System32\wscript.exe"
}
}

$Folder = Get-OrCreateTaskFolder
Remove-ExistingTask -Name $MonitorTaskName

$UserId = "$env:USERDOMAIN\$env:USERNAME"

function New-OneDrivePCSyncMonitorTask {
    param(
        [string]$Name
    )

    $TaskDef = $TaskService.NewTask(0)
    $TaskDef.RegistrationInfo.Description = $MonitorTaskDescription

    $TaskDef.Settings.Enabled = $true
    $TaskDef.Settings.Hidden = $true
    $TaskDef.Settings.DisallowStartIfOnBatteries = $false
    $TaskDef.Settings.StopIfGoingOnBatteries = $false
    $TaskDef.Settings.ExecutionTimeLimit = "PT0S"  # No time limit; the monitor should run until logoff/shutdown.
    $TaskDef.Settings.MultipleInstances = $TASK_INSTANCES_IGNORE_NEW   # Allow multiple? We rely on the monitor's internal lock.

    $Trigger = $TaskDef.Triggers.Create($TASK_TRIGGER_LOGON)
    $Trigger.Enabled = $true
    $Trigger.UserId = $UserId
    # No delay; start as soon as logon occurs.

    $Action = $TaskDef.Actions.Create($TASK_ACTION_EXEC)
    if ($ApplicationExe) {
        $Action.Path = $ApplicationExe
        $Action.Arguments = "--monitor"
    } else {
        $Action.Path = $WscriptExe
        $Action.Arguments = "`"$RunHiddenVbsPath`" `"$PythonExe`" `"$MonitorScript`" `"$ProjectRoot`""
    }
    $Action.WorkingDirectory = $ProjectRoot

    $Principal = $TaskDef.Principal
    $Principal.UserId = $UserId
    $Principal.LogonType = $TASK_LOGON_INTERACTIVE_TOKEN
    $Principal.RunLevel = $TASK_RUNLEVEL_LUA

    $Folder.RegisterTaskDefinition(
        $Name,
        $TaskDef,
        $TASK_CREATE_OR_UPDATE,
        $UserId,
        $null,
        $TASK_LOGON_INTERACTIVE_TOKEN
    ) | Out-Null

    Write-Ok "Registered task: $Name"
}

New-OneDrivePCSyncMonitorTask -Name $MonitorTaskName

Write-Host ""
Write-Ok "Setup complete. EverySync shutdown monitor will now run at logon:"
Write-Host "    - At logon: starts the shutdown monitor (hidden)"
Write-Host "    - The monitor waits for Windows session-ending notifications"
Write-Host "      (shutdown, restart, or logoff) and triggers an upload sync."
Write-Host ""
Write-Warn "Note: Windows gives interactive applications a limited time (default"
Write-Warn "5 seconds, registry-tunable) to complete shutdown processing before"
Write-Warn "forcefully terminating the process. If your shutdown sync regularly"
Write-Warn "exceeds this window, consider increasing the timeout via:"
Write-Host "    HKLM\SYSTEM\CurrentControlSet\Control\WaitToKillServiceTimeout"
Write-Host " (requires reboot and affects all services)."
Write-Host ""
Write-Info "View or manage this task in Task Scheduler under: Task Scheduler Library > OneDrivePCSync"
Write-Info "Logs are written to: $(Join-Path $ProjectRoot 'logs\onedrive_pcsync.log')"
Write-Info "To remove this task later, run: .\Setup-ShutdownMonitor.ps1 -Uninstall"
