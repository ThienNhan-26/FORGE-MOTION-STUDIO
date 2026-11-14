$ErrorActionPreference = "Stop"
$root = (Get-Location).Path
if (!(Test-Path (Join-Path $root "config.py")) -or !(Test-Path (Join-Path $root "contracts\scene3d.py"))) {
    throw "Hãy giải nén gói và chạy INSTALL.ps1 tại thư mục gốc D:\FORGE_MOTION_STUDIO_G1_FINAL."
}
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = Join-Path $root "backups\three_d_specialist_$stamp"
New-Item -ItemType Directory -Force -Path $backup | Out-Null

$targets = @(
    "skills\create_3d_scene\skill.py",
    "skills\create_3d_scene\manifest.json"
)
foreach ($rel in $targets) {
    $dest = Join-Path $root $rel
    if (Test-Path $dest) {
        $backupDest = Join-Path $backup $rel
        New-Item -ItemType Directory -Force -Path (Split-Path $backupDest) | Out-Null
        Copy-Item $dest $backupDest
    }
}
$planner = Join-Path $root "agents\planner.py"
if (Test-Path $planner) { Copy-Item $planner (Join-Path $backup "planner.py") }

New-Item -ItemType Directory -Force -Path (Join-Path $root "agents") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $root "skills\create_3d_scene") | Out-Null
Copy-Item (Join-Path $PSScriptRoot "agents\three_d_specialist.py") (Join-Path $root "agents\three_d_specialist.py") -Force
Copy-Item (Join-Path $PSScriptRoot "skills\create_3d_scene\skill.py") (Join-Path $root "skills\create_3d_scene\skill.py") -Force
Copy-Item (Join-Path $PSScriptRoot "skills\create_3d_scene\manifest.json") (Join-Path $root "skills\create_3d_scene\manifest.json") -Force

& (Join-Path $PSScriptRoot "PATCH_PLANNER.ps1")
if ($LASTEXITCODE -ne 0) { throw "Planner patch thất bại." }

Write-Host ""
Write-Host "3D Specialist integration files installed."
Write-Host "Backup: $backup"
Write-Host "Next: run the verification commands in README.txt."
