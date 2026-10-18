<# Register and remove EXE tasks in a disposable, isolated scheduler folder. #>
[CmdletBinding()]
param([string]$ApplicationExe)
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
if (-not $ApplicationExe) { $ApplicationExe = Join-Path $ProjectRoot 'dist\OneDrivePCSync\OneDrivePCSync.exe' }
$ApplicationExe = (Resolve-Path -LiteralPath $ApplicationExe).Path
$ValidationFolder = '\OneDrivePCSyncValidation_' + [guid]::NewGuid().ToString('N')
$service = New-Object -ComObject Schedule.Service
$service.Connect()
. (Join-Path $PSScriptRoot 'Validation-TaskIsolation.ps1')
function Invoke-Setup([string]$ScriptName, [switch]$Uninstall, [string]$Exe = $ApplicationExe) {
    $arguments = @('-NoProfile','-ExecutionPolicy','Bypass','-File',(Join-Path $ProjectRoot $ScriptName),'-ApplicationExe',$Exe,'-TaskFolderPath',$ValidationFolder)
    if ($Uninstall) { $arguments += '-Uninstall' }
    & powershell.exe @arguments | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Setup script failed: $ScriptName" }
    if (-not $Uninstall) {
        Disable-ValidationTaskTriggers $service $ValidationFolder $ApplicationExe
    }
}
try {
    Invoke-Setup 'Setup-ScheduledTasks.ps1'
    Invoke-Setup 'Setup-ShutdownMonitor.ps1'
    $folder = $service.GetFolder($ValidationFolder)
    $tasks = $folder.GetTasks(1) # Include the hidden shutdown monitor.
    if ($tasks.Count -ne 4) { throw "Expected 4 tasks, got $($tasks.Count)" }
    foreach ($task in $tasks) {
        $definition = $task.Definition
        if ($definition.Actions.Item(1).Path -ine $ApplicationExe) { throw 'Task is not using the EXE' }
        if ($definition.Actions.Item(1).Arguments -notin @('--mode startup','--mode shutdown','--monitor')) { throw 'Unexpected EXE arguments' }
        if ($definition.Principal.RunLevel -ne 0) { throw 'Task requested administrator rights' }
    }
    Invoke-Setup 'Setup-ScheduledTasks.ps1' -Uninstall -Exe 'C:\OtherInstallation\OneDrivePCSync.exe'
    Invoke-Setup 'Setup-ShutdownMonitor.ps1' -Uninstall -Exe 'C:\OtherInstallation\OneDrivePCSync.exe'
    if ($folder.GetTasks(1).Count -ne 4) { throw 'Uninstall removed tasks owned by another installation' }
    Invoke-Setup 'Setup-ScheduledTasks.ps1' -Uninstall
    Invoke-Setup 'Setup-ShutdownMonitor.ps1' -Uninstall
    if ($folder.GetTasks(1).Count -ne 0) { throw 'Uninstall left tasks behind' }
    Write-Output 'PASS: four native EXE tasks; least privilege; ownership-safe removal'
} finally {
    Invoke-Setup 'Setup-ScheduledTasks.ps1' -Uninstall
    Invoke-Setup 'Setup-ShutdownMonitor.ps1' -Uninstall
    $service.GetFolder('\').DeleteFolder($ValidationFolder.TrimStart('\'), 0)
}
