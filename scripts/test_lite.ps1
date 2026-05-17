$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot

$env:ENVIRONMENT = "development"
$env:ENABLE_DEFI_AGENTS = "false"

ruff check .
pytest -m unit
