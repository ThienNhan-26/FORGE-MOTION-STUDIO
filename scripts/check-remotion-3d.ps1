\
    $ErrorActionPreference = 'Stop'
    $Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
    $Template = Join-Path $Root 'adapters\remotion_template'
    $Packages = @(
      'react', 'react-dom', 'three',
      '@react-three\fiber', '@react-three\drei',
      '@remotion\three', '@remotion\cli'
    )

    foreach ($Package in $Packages) {
      $PackageJson = Join-Path $Template ("node_modules\" + $Package + "\package.json")
      if (-not (Test-Path $PackageJson)) {
        throw "Missing package: $Package. Run npm install in adapters\remotion_template."
      }
      $Info = Get-Content $PackageJson -Raw | ConvertFrom-Json
      Write-Host ("{0,-22} {1}" -f $Package, $Info.version) -ForegroundColor Green
    }

    Write-Host "`nR3F singleton aliases are configured in remotion.config.ts." -ForegroundColor Cyan
    Write-Host "Now retry the MP4 render from Motion Studio."
