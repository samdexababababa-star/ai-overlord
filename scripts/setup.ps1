# Install backend (Python venv) + frontend (npm) dependencies on Windows.
$ErrorActionPreference = 'Stop'
$Root = Resolve-Path "$PSScriptRoot\.."
Set-Location $Root

if (-not (Test-Path .venv)) {
  python -m venv .venv
}
& .\.venv\Scripts\python.exe -m pip install --upgrade pip wheel
& .\.venv\Scripts\pip.exe install -e .\backend

Set-Location frontend
if (Get-Command pnpm -ErrorAction SilentlyContinue) {
  pnpm install
} else {
  npm install
}

Write-Host ""
Write-Host "Setup complete."
Write-Host "Next:  .\scripts\dev.ps1"
