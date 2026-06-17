# Daily ingest job — scrapes IBBI, ingests new opportunities, recomputes matches.
# Invoked by the "Jarvis IBC Daily Ingest" scheduled task. Logs to tools\ingest.log.
# Uses absolute paths so it behaves identically under Task Scheduler (no $PSScriptRoot).
$ErrorActionPreference = "Stop"
$root    = "C:\Users\MNAAdvisoryKCM\Desktop\Dhanish Personal Folder\Claude Git\Sessions\ibc-matchmaker"
$py      = Join-Path $root ".venv\Scripts\python.exe"
$backend = Join-Path $root "backend"
$log     = Join-Path $root "tools\ingest.log"
$ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content $log "[$ts] starting ingest..."
try {
  Set-Location $backend
  $out = & $py -m app.ingest 2>&1 | Out-String
  Add-Content $log "[$ts] $($out.Trim())"
} catch {
  Add-Content $log "[$ts] ERROR: $_"
  exit 1
}
