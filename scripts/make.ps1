# Windows equivalent of the Makefile targets.
# Usage: .\scripts\make.ps1 <target>
param([Parameter(Mandatory = $true)][string]$Target)

$Root = Split-Path -Parent $PSScriptRoot
$Venv = Join-Path $Root "backend\.venv\Scripts"
$Python = Join-Path $Venv "python.exe"

function Find-SystemPython {
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
        "C:\Program Files\Python312\python.exe"
    )
    foreach ($c in $candidates) { if (Test-Path $c) { return $c } }
    return "python"
}

switch ($Target) {
    "install" {
        $sys = Find-SystemPython
        Push-Location (Join-Path $Root "backend")
        & $sys -m venv .venv
        & $Python -m pip install -e ".[dev]"
        Pop-Location
        Push-Location (Join-Path $Root "frontend")
        npm install
        Pop-Location
    }
    "backend"   { Push-Location (Join-Path $Root "backend"); & $Python -m uvicorn app.main:app --reload --port 8000; Pop-Location }
    "frontend"  { Push-Location (Join-Path $Root "frontend"); npm run dev; Pop-Location }
    "test"      { Push-Location (Join-Path $Root "backend"); & $Python -m pytest -q; Pop-Location }
    "lint"      { Push-Location (Join-Path $Root "backend"); & $Python -m ruff check app tests; Pop-Location }
    "typecheck" { Push-Location (Join-Path $Root "backend"); & $Python -m mypy app; Pop-Location }
    "migrate"   { Push-Location (Join-Path $Root "backend"); & $Python -m alembic upgrade head; Pop-Location }
    "seed"      { Push-Location (Join-Path $Root "backend"); & $Python ..\scripts\seed_database.py; Pop-Location }
    "backtest"  { Push-Location (Join-Path $Root "backend"); & $Python ..\scripts\run_backtest.py; Pop-Location }
    "verify-paper-account" { Push-Location (Join-Path $Root "backend"); & $Python ..\scripts\verify_broker_connection.py; Pop-Location }
    "kill-switch" { Push-Location (Join-Path $Root "backend"); & $Python -m app.cli kill-switch --activate --reason "CLI activation"; Pop-Location }
    "docker-up"   { Push-Location $Root; docker compose up -d --build; Pop-Location }
    "docker-down" { Push-Location $Root; docker compose down; Pop-Location }
    default { Write-Error "Unknown target: $Target" }
}
