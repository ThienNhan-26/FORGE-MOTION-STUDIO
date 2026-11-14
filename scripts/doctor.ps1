$ErrorActionPreference = 'Continue'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $Root

Write-Host '=== FORGE environment check ===' -ForegroundColor Cyan
foreach ($Name in @('python', 'node', 'npm', 'ollama', 'ffmpeg', 'ffprobe')) {
    $Command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($Command) {
        $Version = & $Name --version 2>&1 | Select-Object -First 1
        Write-Host ("[OK] {0}: {1}" -f $Name, $Version) -ForegroundColor Green
    }
    else {
        Write-Host ("[MISSING] {0}" -f $Name) -ForegroundColor Yellow
    }
}

$Py = Join-Path $Root '.venv\Scripts\python.exe'
if (Test-Path $Py) {
    & $Py main.py --doctor
}
else {
    Write-Warning 'Virtual environment is missing. Run .\scripts\setup.ps1.'
}

Write-Host ''
Write-Host '=== Motion Studio checks ===' -ForegroundColor Cyan
$MotionDist = Join-Path $Root 'motion_studio\dist\index.html'
$ThreePackage = Join-Path $Root 'adapters\remotion_template\node_modules\@remotion\three\package.json'
if (Test-Path $MotionDist) { Write-Host '[OK] Motion Studio frontend is built.' -ForegroundColor Green }
else { Write-Host '[MISSING] Motion Studio frontend. Run .\scripts\setup.ps1.' -ForegroundColor Yellow }
if (Test-Path $ThreePackage) { Write-Host '[OK] @remotion/three is installed.' -ForegroundColor Green }
else { Write-Host '[MISSING] @remotion/three. Run .\scripts\setup.ps1.' -ForegroundColor Yellow }
