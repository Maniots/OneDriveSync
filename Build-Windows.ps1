<# Build a self-contained desktop bundle and optionally its Windows installer. #>
[CmdletBinding()]
param(
    [string]$PythonExe,
    [string]$InnoCompiler,
    [int]$BuildNumber = 0,
    [switch]$BundleOnly
)
$ErrorActionPreference = 'Stop'
if (-not $PythonExe) { $PythonExe = Join-Path $PSScriptRoot '.venv\Scripts\python.exe' }
if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
    throw 'Python not found. Create .venv and install requirements-build.txt first.'
}
Push-Location $PSScriptRoot
try {
    $RcloneExe = & .\scripts\Prepare-Rclone.ps1
    if (-not (Test-Path -LiteralPath $RcloneExe)) { throw 'Cloud engine preparation failed.' }
    $ReleaseVersion = & $PythonExe scripts\release_metadata.py build --build-number $BuildNumber
    if ($LASTEXITCODE -ne 0) { throw 'Build metadata generation failed.' }
    & $PythonExe -m PyInstaller --noconfirm --workpath build\windows packaging\OneDrivePCSync.spec
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }
    Copy-Item -LiteralPath Setup-ScheduledTasks.ps1,Setup-ShutdownMonitor.ps1 -Destination dist\OneDrivePCSync
    Copy-Item -LiteralPath $RcloneExe -Destination dist\OneDrivePCSync\rclone.exe
    Copy-Item -LiteralPath packaging\rclone-LICENSE.txt -Destination dist\OneDrivePCSync\rclone-LICENSE.txt
    if ($BundleOnly) { return }
    if (-not $InnoCompiler) {
        $candidates = @(
            (Join-Path $PSScriptRoot 'build\tools\inno\ISCC.exe'),
            (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
            (Join-Path $env:ProgramFiles 'Inno Setup 7\ISCC.exe')
        )
        $InnoCompiler = $candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
    }
    if (-not $InnoCompiler) { throw 'Inno Setup compiler not found. Supply -InnoCompiler or use -BundleOnly.' }
    & $InnoCompiler /Qp packaging\windows-installer.iss
    if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed.' }
    & $PythonExe scripts\release_metadata.py manifest
    if ($LASTEXITCODE -ne 0) { throw 'Update manifest generation failed.' }
    Write-Host "Installer: dist\installer\EverySync-Setup-$ReleaseVersion.exe"
} finally {
    Pop-Location
}
