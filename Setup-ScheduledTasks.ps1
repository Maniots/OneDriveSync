<#
.SYNOPSIS
    One-time setup script that registers Windows Scheduled Tasks for
    OneDrivePCSync: download on logon, upload on lock, and a periodic
    upload safety net.

.DESCRIPTION
    Run this script once (see instructions below) and OneDrivePCSync will
    run automatically from then on, with no further action required:

        - "OneDrivePCSync - Startup (Download)"        fires when you log on.
        - "OneDrivePCSync - Shutdown (Upload on Lock)" fires when you lock
          your workstation (Win+L, or automatic idle lock).
        - "OneDrivePCSync - Periodic Upload"           fires every 15
          minutes while you're logged on.

    IMPORTANT LIMITATION: Windows Task Scheduler has no native "log off" or
    "shutdown" trigger, and clicking Start > Shut Down does NOT lock your
    session first - it ends it directly (and with Fast Startup enabled, a
    "shutdown" is actually a hibernation that emits no session event at
    all). This means the lock-triggered upload task will NOT fire if you
    shut down without first pressing Win+L.

    The periodic upload task exists specifically to cover that gap: instead
    of trying to catch the exact moment of shutdown (which isn't reliably
    possible without Group Policy logoff scripts, Pro/Enterprise editions
    only), it uploads every 15 minutes throughout your session, so you're
    never more than ~15 minutes of play behind on OneDrive regardless of
    how the session ends.

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
$ShutdownTaskName = "OneDrivePCSync - Shutdown (Upload on Lock)"
$PeriodicTaskName = "OneDrivePCSync - Periodic Upload"
$PeriodicIntervalMinutes = 15

# Task Scheduler COM API constants (see Microsoft's Task Scheduler Schema docs).
$TASK_TRIGGER_TIME                  = 1
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
    Remove-ExistingTask -Name $PeriodicTaskName
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

# If we ended up with python.exe (console-allocating) rather than pythonw.exe
# (no console window), check whether a pythonw.exe sibling exists right next
# to it and prefer that instead - this avoids a console window flashing on
# screen every time a task fires, including the periodic one every 15 minutes.
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

# --- Generate the hidden-run wrapper ----------------------------------------
# Even pythonw.exe can briefly flash a window when launched directly as a
# Task Scheduler action (a known quirk, especially on Windows 11 with
# Windows Terminal set as the default terminal host - Task Scheduler's own
# process-launch bookkeeping briefly creates a console host regardless of
# which Python binary is targeted). Routing the launch through WScript.Shell
# with window style 0 (hidden) sidesteps this entirely - it is the standard,
# reliable fix for this exact Task Scheduler behavior.
$RunHiddenVbsPath = Join-Path $ProjectRoot "RunHidden.vbs"
$VbsContent = @"
' RunHidden.vbs
' Auto-generated by Setup-ScheduledTasks.ps1 - do not edit by hand,
' re-run that script to regenerate this file instead.
'
' Launches a command completely hidden (window style 0), with no window
' flash whatsoever. Used to work around a Task Scheduler quirk where even
' pythonw.exe can briefly flash a console window when launched directly.
'
' Arguments: <python_exe_path> <main_py_path> <mode> <working_directory>
Option Explicit
Dim objShell, strPython, strScript, strMode, strCwd, strCommand

If WScript.Arguments.Count < 4 Then
    WScript.Quit 1
End If

strPython = WScript.Arguments(0)
strScript = WScript.Arguments(1)
strMode   = WScript.Arguments(2)
strCwd    = WScript.Arguments(3)

Set objShell = CreateObject("WScript.Shell")
objShell.CurrentDirectory = strCwd

strCommand = """" & strPython & """ """ & strScript & """ --mode " & strMode
objShell.Run strCommand, 0, True
"@
Set-Content -Path $RunHiddenVbsPath -Value $VbsContent -Encoding ASCII
Write-Ok "Generated hidden-run wrapper: $RunHiddenVbsPath"

$WscriptExe = (Get-Command wscript.exe -ErrorAction SilentlyContinue).Source
if (-not $WscriptExe) {
    $WscriptExe = Join-Path $env:SystemRoot "System32\wscript.exe"
}

$Folder = Get-OrCreateTaskFolder
Remove-ExistingTask -Name $StartupTaskName
Remove-ExistingTask -Name $ShutdownTaskName
Remove-ExistingTask -Name $PeriodicTaskName

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
    } elseif ($TriggerType -eq $TASK_TRIGGER_TIME) {
        # Start one minute from now, then repeat every $PeriodicIntervalMinutes
        # indefinitely (empty Duration = repeat forever) for as long as the
        # user stays logged on.
        $Trigger.StartBoundary = (Get-Date).AddMinutes(1).ToString("yyyy-MM-ddTHH:mm:ss")
        $Trigger.Repetition.Interval = "PT${PeriodicIntervalMinutes}M"
        $Trigger.Repetition.StopAtDurationEnd = $false
    }

    $Action = $TaskDef.Actions.Create($TASK_ACTION_EXEC)
    $Action.Path = $WscriptExe
    $Action.Arguments = "`"$RunHiddenVbsPath`" `"$PythonExe`" `"$MainScript`" $Mode `"$ProjectRoot`""
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
New-OneDrivePCSyncTask -Name $PeriodicTaskName -Mode "shutdown" -TriggerType $TASK_TRIGGER_TIME

Write-Host ""
Write-Ok "Setup complete. OneDrivePCSync now runs automatically:"
Write-Host "    - On logon                    -> downloads from OneDrive"
Write-Host "    - On workstation lock (Win+L) -> uploads to OneDrive"
Write-Host "    - Every $PeriodicIntervalMinutes minutes while logged on -> uploads to OneDrive"
Write-Host ""
Write-Warn "Note: a direct Shut Down/Restart does NOT reliably trigger the lock-based"
Write-Warn "upload task (Windows doesn't lock the session first). The periodic task"
Write-Warn "above is your safety net for that - your last upload will be at most"
Write-Warn "$PeriodicIntervalMinutes minutes old. Pressing Win+L before shutting down still"
Write-Warn "gives you an immediate extra upload on top of that."
Write-Host ""
Write-Info "View or manage these tasks in Task Scheduler under: Task Scheduler Library > OneDrivePCSync"
Write-Info "Logs are written to: $(Join-Path $ProjectRoot 'logs\onedrive_pcsync.log')"
Write-Info "To remove these tasks later, run: .\Setup-ScheduledTasks.ps1 -Uninstall"