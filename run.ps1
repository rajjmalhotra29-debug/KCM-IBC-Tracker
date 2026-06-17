# IBC Matchmaker — start script (Windows PowerShell)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$py = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $py)) {
  Write-Host "Virtual env not found. Creating it..." -ForegroundColor Yellow
  $base = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
  & $base -m venv (Join-Path $root ".venv")
  & $py -m pip install -r (Join-Path $root "backend\requirements.txt")
}

Set-Location (Join-Path $root "backend")

if (-not (Test-Path (Join-Path $root "backend\ibc.db"))) {
  Write-Host "Seeding demo data..." -ForegroundColor Cyan
  & $py -m app.seed
}

Write-Host "`nStarting IBC Matchmaker at http://127.0.0.1:8000 ..." -ForegroundColor Green
& $py -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
