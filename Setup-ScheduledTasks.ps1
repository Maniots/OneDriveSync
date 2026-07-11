<#
.SYNOPSIS
    One-time setup script that registers Windows Scheduled Tasks for
    OneDrivePCSync: download on logon, upload on workstation lock.

.DESCRIPTION
    Run this script once (see instructions below) and OneDrivePCSync will
    run automatically from then on, with no further action required:

        - "OneDrivePCSync - Startup (Download)"  fires when you log on.
        - "OneDrivePCSync - Shutdown (Upload)"    fires when you lock your
          workstation (Win+L, or automatic idle lock).

    Windows Task Scheduler has no native "log off" trigger, so "workstation
    lock" is used instead - it reliably fires whenever you step away or are
    about to shut down/restart (Windows locks the session first in both
    cases), without requiring elevated audit policy changes.

    This script is idempotent: re-running it safely replaces any previously
    registered OneDrivePCSync tasks rather than duplicating them. This is
    also how you "reinstall" the tasks after moving the project folder or
    switching Python interpreters - just run it again.

.PARAMETER Uninstall
    Removes the OneDrivePCSync scheduled tasks instead of creating them.

.EXAMPLE
    Right-click this file in Explorer -> "Run with PowerShell".

.EXAMPLE
    From a PowerShell prompt in the project folder:
        powershell -ExecutionPolicy Bypass -File .\Setup-ScheduledTasks.ps1

.EXAMPLE
    Remove the tasks later:
        powershell -ExecutionPolicy Bypass -File .\Setup-ScheduledTasks.ps1 -Uninstall
#>

[CmdletBinding()]
param(
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"

# --- Constants ----------------------------------------------------------------
$ProjectRoot      = $PSScriptRoot
$TaskFolderPath   = "\OneDrivePCSync"
$StartupTaskName  = "OneDrivePCSync - Startup (Download)"
$ShutdownTaskName = "OneDrivePCSync - Shutdown (Upload)"

# Task Scheduler COM API constants (see Microsoft's Task Scheduler Schema docs).
$TASK_TRIGGER_LOGON                 = 9
$TASK_TRIGGER_SESSION_STATE_CHANGE  = 11
$TASK_SESSION_LOCK                  = 7
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
    Write-Info "Uninstalling OneDrivePCSync scheduled tasks..."
    Remove-ExistingTask -Name $StartupTaskName
    Remove-ExistingTask -Name $ShutdownTaskName
    Write-Ok "Uninstall complete. Nothing else was changed (config.json, logs, etc. are untouched)."
    return
}

# --- Install path -----------------------------------------------------------
Write-Info "Project root detected as: $ProjectRoot"

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
Write-Ok "Using Python interpreter: $PythonExe"

$MainScript = Join-Path $ProjectRoot "main.py"
if (-not (Test-Path $MainScript -PathType Leaf)) {
    Write-Err "main.py not found at: $MainScript"
    Write-Err "Run this script from inside the OneDrivePCSync project folder."
    exit 1
}

$ConfigFile = Join-Path $ProjectRoot "config.json"
if (-not (Test-Path $ConfigFile -PathType Leaf)) {
    Write-Warn "config.json not found at: $ConfigFile"
    Write-Warn "The scheduled tasks will be created, but syncing will fail until config.json exists."
}

$Folder = Get-OrCreateTaskFolder
Remove-ExistingTask -Name $StartupTaskName
Remove-ExistingTask -Name $ShutdownTaskName

$UserId = "$env:USERDOMAIN\$env:USERNAME"

function New-OneDrivePCSyncTask {
    param(
        [string]$Name,
        [string]$Mode,
        [int]$TriggerType
    )

    $TaskDef = $TaskService.NewTask(0)
    $TaskDef.RegistrationInfo.Description =
        "Runs 'python main.py --mode $Mode' for OneDrivePCSync. " +
        "Managed by Setup-ScheduledTasks.ps1 - re-run that script to change or reinstall this task rather than editing it by hand."

    $TaskDef.Settings.Enabled = $true
    $TaskDef.Settings.Hidden = $false
    $TaskDef.Settings.DisallowStartIfOnBatteries = $false
    $TaskDef.Settings.StopIfGoingOnBatteries = $false
    $TaskDef.Settings.ExecutionTimeLimit = "PT10M"                     # safety cap: kill after 10 minutes
    $TaskDef.Settings.MultipleInstances = $TASK_INSTANCES_IGNORE_NEW   # never run two syncs at once

    $Trigger = $TaskDef.Triggers.Create($TriggerType)
    $Trigger.Enabled = $true
    if ($TriggerType -eq $TASK_TRIGGER_SESSION_STATE_CHANGE) {
        $Trigger.StateChange = $TASK_SESSION_LOCK
        $Trigger.UserId = $UserId
    } elseif ($TriggerType -eq $TASK_TRIGGER_LOGON) {
        $Trigger.UserId = $UserId
    }

    $Action = $TaskDef.Actions.Create($TASK_ACTION_EXEC)
    $Action.Path = $PythonExe
    $Action.Arguments = "`"$MainScript`" --mode $Mode"
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

New-OneDrivePCSyncTask -Name $StartupTaskName  -Mode "startup"  -TriggerType $TASK_TRIGGER_LOGON
New-OneDrivePCSyncTask -Name $ShutdownTaskName -Mode "shutdown" -TriggerType $TASK_TRIGGER_SESSION_STATE_CHANGE

Write-Host ""
Write-Ok "Setup complete. OneDrivePCSync now runs automatically:"
Write-Host "    - On logon              -> downloads from OneDrive"
Write-Host "    - On workstation lock   -> uploads to OneDrive"
Write-Host ""
Write-Info "View or manage these tasks in Task Scheduler under: Task Scheduler Library > OneDrivePCSync"
Write-Info "Logs are written to: $(Join-Path $ProjectRoot 'logs\onedrive_pcsync.log')"
Write-Info "To remove these tasks later, run: .\Setup-ScheduledTasks.ps1 -Uninstall"
