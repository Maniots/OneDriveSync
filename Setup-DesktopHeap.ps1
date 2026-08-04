<#
.SYNOPSIS
    Increases the non-interactive desktop heap size to resolve
    STATUS_DLL_INIT_FAILED (0xC0000142) failures when spawning
    robocopy.exe from a background process during system shutdown.

.DESCRIPTION
    Modifies HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\SubSystems\Windows,
    increasing the third SharedSection value (non-interactive desktop heap,
    in KB) from the Windows default of 768 to 12288.

    Background processes (like a Scheduled Task running with no visible
    desktop) create new child processes on a NON-INTERACTIVE desktop.
    That desktop has its own separate, much smaller heap budget than the
    interactive one you normally use. When that heap is exhausted or
    under pressure - plausible during a real system shutdown, when many
    processes are closing and creating objects simultaneously - new
    console processes (like robocopy.exe) can fail to initialize with
    STATUS_DLL_INIT_FAILED, even though the exact same command works
    fine in any manual/interactive test.

    REQUIRES A REBOOT to take effect. Run as Administrator.

.EXAMPLE
    Right-click -> "Run with PowerShell" (as Administrator), or:
        powershell -ExecutionPolicy Bypass -File .\Setup-DesktopHeap.ps1

.EXAMPLE
    Revert to the original value later:
        powershell -ExecutionPolicy Bypass -File .\Setup-DesktopHeap.ps1 -Revert
#>

[CmdletBinding()]
param(
    [switch]$Revert
)

$ErrorActionPreference = "Stop"

$RegPath = "HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\SubSystems"
$BackupPath = Join-Path $PSScriptRoot "desktop_heap_original_value.txt"

function Write-Info($msg) { Write-Host "[i] $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "[OK] $msg" -ForegroundColor Green }
function Write-Err($msg)  { Write-Host "[X] $msg" -ForegroundColor Red }

# Must run elevated - this key is not writable otherwise.
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Err "This script must be run as Administrator (the registry key is protected)."
    exit 1
}

$currentValue = (Get-ItemProperty -Path $RegPath -Name "Windows").Windows
Write-Info "Current value:"
Write-Host "    $currentValue"

if ($Revert) {
    if (-not (Test-Path $BackupPath)) {
        Write-Err "No backup file found at $BackupPath - nothing to revert to."
        Write-Err "If you know the original value, restore it manually via regedit."
        exit 1
    }
    $originalValue = Get-Content $BackupPath -Raw
    Set-ItemProperty -Path $RegPath -Name "Windows" -Value $originalValue
    Write-Ok "Reverted to original value:"
    Write-Host "    $originalValue"
    Write-Info "A REBOOT is required for this change to take effect."
    exit 0
}

# Idempotency: if the non-interactive heap is already set to the target
# value, report success and exit — nothing to do.
if ($currentValue -match "SharedSection=1024,20480,12288") {
    Write-Ok "Non-interactive desktop heap is already set to 12288 KB."
    Write-Info "No changes needed. A reboot is still required if this value"
    Write-Info "was changed previously but the system has not been restarted yet."
    exit 0
}

# Only proceed if this looks like the standard default we expect to modify -
# refuse to blindly overwrite an already-customized value.
if ($currentValue -notmatch "SharedSection=1024,20480,768") {
    Write-Err "The current value does not match the expected Windows default"
    Write-Err "(SharedSection=1024,20480,768). Refusing to modify automatically,"
    Write-Err "since this value may have already been customized on this machine."
    Write-Err "Current value shown above - please edit it manually if you want to proceed."
    exit 1
}

# Back up the original value before touching anything.
if (-not (Test-Path $BackupPath)) {
    Set-Content -Path $BackupPath -Value $currentValue -NoNewline
    Write-Ok "Backed up original value to: $BackupPath"
} else {
    Write-Info "Backup already exists at $BackupPath - not overwriting it."
}

# Increase the third SharedSection value (non-interactive desktop heap,
# in KB) from 768 to 12288 (16x). First two values (interactive heap
# size limits) are left untouched.
$newValue = $currentValue -replace "SharedSection=1024,20480,768", "SharedSection=1024,20480,12288"

Set-ItemProperty -Path $RegPath -Name "Windows" -Value $newValue

Write-Ok "New value set:"
Write-Host "    $newValue"
Write-Host ""
Write-Host "=====================================================================" -ForegroundColor Yellow
Write-Host " A REBOOT IS REQUIRED for this change to take effect." -ForegroundColor Yellow
Write-Host "=====================================================================" -ForegroundColor Yellow
Write-Host ""
Write-Info "To revert this change later, run:"
Write-Host "    powershell -ExecutionPolicy Bypass -File .\Setup-DesktopHeap.ps1 -Revert"