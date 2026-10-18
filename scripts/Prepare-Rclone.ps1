<# Prepare the pinned, hash-verified Windows runtime used by cloud sync. #>
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$pin = Get-Content -LiteralPath (Join-Path $ProjectRoot 'packaging/rclone-version.json') -Raw | ConvertFrom-Json
$tools = Join-Path $ProjectRoot 'build/tools'
New-Item -ItemType Directory -Force -Path $tools | Out-Null
$archive = Join-Path $tools $pin.archive
if (-not (Test-Path -LiteralPath $archive)) {
    Invoke-WebRequest -Uri ("https://github.com/rclone/rclone/releases/download/$($pin.version)/$($pin.archive)") -OutFile $archive
}
if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLower() -ne $pin.sha256) {
    throw 'The rclone archive does not match the pinned SHA-256. Remove that archive and retry.'
}
$destination = Join-Path $tools 'rclone'
# Re-extract only a verified upstream archive, replacing stale extracted files.
Expand-Archive -LiteralPath $archive -DestinationPath $destination -Force
$executable = Join-Path $destination ("rclone-$($pin.version)-windows-amd64/rclone.exe")
if (-not (Test-Path -LiteralPath $executable)) { throw 'The verified archive did not contain the expected cloud engine' }
Write-Output $executable
