$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $Root

$Py = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $Py)) { throw 'Virtual environment not found. Run .\scripts\setup.ps1 first.' }
$Dist = Join-Path $Root 'motion_studio\dist\index.html'
if (-not (Test-Path $Dist)) {
    $Npm = Get-Command npm -ErrorAction SilentlyContinue
    if (-not $Npm) { throw 'npm was not found. Install Node.js and run .\scripts\setup.ps1.' }
    Push-Location (Join-Path $Root 'motion_studio')
    try {
        & npm install
        if ($LASTEXITCODE -ne 0) { throw 'Motion Studio npm install failed.' }
        & npm run build
        if ($LASTEXITCODE -ne 0) { throw 'Motion Studio frontend build failed.' }
    }
    finally { Pop-Location }
}

Write-Host 'Starting FORGE Motion Studio at http://127.0.0.1:8765' -ForegroundColor Cyan
& $Py (Join-Path $Root 'motion_studio\server.py')
if ($LASTEXITCODE -ne 0) { throw "Motion Studio server exited with code $LASTEXITCODE." }
