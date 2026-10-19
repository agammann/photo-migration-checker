param([string]$Python = 'python', [int]$Port = 8765)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $projectRoot
try {
    if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
        & $Python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'A working Python 3.11+ installation is required.' }
    }
    & '.\.venv\Scripts\python.exe' -m pip install .
    if ($LASTEXITCODE -ne 0) { throw 'Installation failed.' }
    & '.\.venv\Scripts\python.exe' -m pmc --port $Port
} finally {
    Pop-Location
}
