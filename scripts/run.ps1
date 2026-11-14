$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $Root
$Py = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $Py)) {
    throw 'Virtual environment not found. Run .\scripts\setup.ps1 first.'
}
& $Py main.py
if ($LASTEXITCODE -ne 0) {
    throw "FORGE exited with code $LASTEXITCODE. Check the error above."
}
