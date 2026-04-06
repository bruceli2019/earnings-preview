# run-daily-news.ps1 — Generates daily news notes, backfilling any missed days.

$ErrorActionPreference = "Continue"

$projectDir = "C:\Users\pengy\Documents\Vibe Coding\earnings-preview"
$vaultDir   = "C:\Users\pengy\Documents\Obsidian Vault"
$notesDir   = Join-Path $vaultDir "Daily Notes"
$pythonExe  = Join-Path $projectDir ".venv\Scripts\python.exe"
$maxBackfill = 7  # look back up to 7 days

Set-Location $projectDir

# Ensure Daily Notes folder exists
if (-not (Test-Path $notesDir)) {
    New-Item -ItemType Directory -Path $notesDir -Force | Out-Null
}

# Find missing days (today + up to $maxBackfill days back)
$today = Get-Date -Format "yyyy-MM-dd"
$missingDates = @()

for ($i = $maxBackfill; $i -ge 0; $i--) {
    $d = (Get-Date).AddDays(-$i).ToString("yyyy-MM-dd")
    $noteFile = Join-Path $notesDir "$d.md"
    if (-not (Test-Path $noteFile)) {
        $missingDates += $d
    }
}

if ($missingDates.Count -eq 0) {
    Write-Host "All notes up to date. Nothing to do."
    exit 0
}

Write-Host "Generating notes for: $($missingDates -join ', ')"

foreach ($d in $missingDates) {
    Write-Host "`n--- Generating note for $d ---"
    & $pythonExe -m earnings_analyzer.cli news --no-analyze --no-open --date $d 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Warning: failed to generate note for $d"
    }
}

Write-Host "`nDone. Generated $($missingDates.Count) note(s)."
