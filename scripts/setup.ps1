$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $Root

Write-Host '=== FORGE setup ===' -ForegroundColor Cyan

$Python = Get-Command python -ErrorAction SilentlyContinue
if (-not $Python) {
    throw 'Python was not found in PATH. Install Python 3.10+ and run setup again.'
}

$PythonVersion = & python -c "import sys; print('%d.%d' % sys.version_info[:2])"
if ($LASTEXITCODE -ne 0) {
    throw 'Unable to detect Python version.'
}
$VersionParts = $PythonVersion.Trim().Split('.')
if ([int]$VersionParts[0] -lt 3 -or ([int]$VersionParts[0] -eq 3 -and [int]$VersionParts[1] -lt 10)) {
    throw "Python 3.10 or newer is required. Found Python $PythonVersion."
}
Write-Host "Python: $PythonVersion" -ForegroundColor Green

if (-not (Test-Path (Join-Path $Root '.venv'))) {
    & python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Unable to create the virtual environment.' }
}

$Py = Join-Path $Root '.venv\Scripts\python.exe'
& $Py -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'Unable to upgrade pip.' }
& $Py -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Unable to install requirements.txt.' }

if (-not (Test-Path (Join-Path $Root '.env'))) {
    Copy-Item (Join-Path $Root '.env.example') (Join-Path $Root '.env')
    Write-Host 'Created .env from .env.example.' -ForegroundColor Green
}

$Template = Join-Path $Root 'adapters\remotion_template'
$Node = Get-Command node -ErrorAction SilentlyContinue
$Npm = Get-Command npm -ErrorAction SilentlyContinue
if ($Node -and $Npm) {
    Write-Host "Node: $(& node --version)" -ForegroundColor Green
    if (Test-Path (Join-Path $Template 'package.json')) {
        Push-Location $Template
        try {
            & npm install
            if ($LASTEXITCODE -ne 0) {
                Write-Warning 'Remotion npm install failed. Python/TUI can still be used; video rendering is not ready.'
            }
        }
        finally { Pop-Location }
    }

    $MotionStudio = Join-Path $Root 'motion_studio'
    if (Test-Path (Join-Path $MotionStudio 'package.json')) {
        Push-Location $MotionStudio
        try {
            & npm install
            if ($LASTEXITCODE -eq 0) {
                & npm run build
                if ($LASTEXITCODE -ne 0) {
                    Write-Warning 'Motion Studio frontend build failed. See TypeScript/Vite output above.'
                }
            }
            else {
                Write-Warning 'Motion Studio npm install failed. TUI can still be used; browser preview is not ready.'
            }
        }
        finally { Pop-Location }
    }
}
else {
    Write-Warning 'Node.js/npm not found. Python/TUI can still be used; Remotion rendering is unavailable.'
}

$Ollama = Get-Command ollama -ErrorAction SilentlyContinue
if ($Ollama) {
    Write-Host 'Installed Ollama models:' -ForegroundColor Cyan
    & ollama list
    Write-Host 'Check that model names in .env match the list above.'
}
else {
    Write-Warning 'Ollama not found. Install/start Ollama before submitting a mission.'
}

Write-Host ''
Write-Host 'Setup completed. Start FORGE with: .\scripts\run.ps1' -ForegroundColor Green
