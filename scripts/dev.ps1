# Start backend + Electron with Vite hot reload (Windows).
$ErrorActionPreference = 'Stop'
$Root = Resolve-Path "$PSScriptRoot\.."
Set-Location $Root

$backend = Start-Process -PassThru -FilePath .\.venv\Scripts\python.exe `
  -ArgumentList "-m","uvicorn","backend.app.main:app","--host","127.0.0.1","--port","8765"

try {
  Set-Location frontend
  $env:OVERLORD_NO_BACKEND = "1"
  npx concurrently -k -n VITE,ELEC -c cyan,magenta `
    "npm run dev" `
    "npx wait-on http://localhost:5173 && npx electron ."
} finally {
  if ($backend -and -not $backend.HasExited) { Stop-Process -Id $backend.Id -Force }
}
