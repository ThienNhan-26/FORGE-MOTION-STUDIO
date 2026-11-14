$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$patchRoot = Join-Path $root "patch"
if (!(Test-Path $patchRoot)) { throw "Không tìm thấy thư mục patch cạnh APPLY.ps1." }

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupRoot = Join-Path $root "backups\model_decoupling_$stamp"
$targets = @(
    @{ Source = "skills\create_3d_scene\skill.py"; Destination = "skills\create_3d_scene\skill.py" },
    @{ Source = "skills\create_3d_scene\manifest.json"; Destination = "skills\create_3d_scene\manifest.json" }
)

foreach ($item in $targets) {
    $source = Join-Path $patchRoot $item.Source
    $destination = Join-Path $root $item.Destination
    if (!(Test-Path $source)) { throw "Thiếu file patch: $source" }
    $destinationDir = Split-Path -Parent $destination
    New-Item -ItemType Directory -Force -Path $destinationDir | Out-Null

    if (Test-Path $destination) {
        $backup = Join-Path $backupRoot $item.Destination
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $backup) | Out-Null
        Copy-Item -LiteralPath $destination -Destination $backup -Force
    }
    Copy-Item -LiteralPath $source -Destination $destination -Force
    Write-Host "UPDATED: $($item.Destination)" -ForegroundColor Green
}

$python = Join-Path $root ".venv\Scripts\python.exe"
if (Test-Path $python) {
    & $python -m compileall -q (Join-Path $root "skills")
    if ($LASTEXITCODE -ne 0) { throw "compileall thất bại. Backup: $backupRoot" }
    Write-Host "Python compile: PASS" -ForegroundColor Green
} else {
    Write-Warning "Không tìm thấy .venv; bỏ qua compileall."
}

Write-Host ""
Write-Host "Model decoupling patch applied." -ForegroundColor Cyan
Write-Host "Backup: $backupRoot"
Write-Host "Không thay đổi Planner, Coder, Reviewer, Ollama models, workspace hoặc database."
