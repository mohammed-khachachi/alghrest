$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$dashboardDir = Join-Path $repoRoot "dashboard"
$mockServer = Join-Path $repoRoot "api\mock_server.py"
$dashboardPackage = Join-Path $dashboardDir "package.json"
$dashboardNodeModules = Join-Path $dashboardDir "node_modules"

$env:ENVIRONMENT = "development"
$env:ENABLE_DEFI_AGENTS = "false"

$pythonPathParts = @($repoRoot, (Join-Path $repoRoot "api"))
if ($env:PYTHONPATH) {
    $pythonPathParts += $env:PYTHONPATH
}
$env:PYTHONPATH = ($pythonPathParts -join [System.IO.Path]::PathSeparator)

if (-not (Test-Path $mockServer)) {
    throw "Missing mock server: $mockServer"
}

if (-not (Test-Path $dashboardPackage)) {
    throw "Missing dashboard package.json: $dashboardPackage"
}

if (-not (Test-Path $dashboardNodeModules)) {
    throw "Missing dashboard\node_modules. Run this once: Set-Location dashboard; npm install; Set-Location .."
}

$python = (Get-Command python -ErrorAction Stop).Source
$npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
if ($null -eq $npmCommand) {
    $npmCommand = Get-Command npm -ErrorAction Stop
}
$npm = $npmCommand.Source

Write-Host "ALGHREST lightweight development mode"
Write-Host "ENVIRONMENT=$env:ENVIRONMENT"
Write-Host "ENABLE_DEFI_AGENTS=$env:ENABLE_DEFI_AGENTS"
Write-Host "Mock backend: http://localhost:8000"
Write-Host "Dashboard:    http://localhost:5173"
Write-Host "Docker, Kafka, Redis, TimescaleDB, agents, and ML server are not started."
Write-Host "Press Ctrl+C to stop both processes."

function Stop-LiteProcess {
    param(
        [System.Diagnostics.Process] $Process,
        [string] $Name
    )

    if ($null -ne $Process -and -not $Process.HasExited) {
        Write-Host "Stopping $Name (PID $($Process.Id))..."
        Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
    }
}

$apiProcess = $null
$dashboardProcess = $null

try {
    $apiProcess = Start-Process `
        -FilePath $python `
        -ArgumentList @("api/mock_server.py") `
        -WorkingDirectory $repoRoot `
        -NoNewWindow `
        -PassThru

    $dashboardProcess = Start-Process `
        -FilePath $npm `
        -ArgumentList @("run", "dev") `
        -WorkingDirectory $dashboardDir `
        -NoNewWindow `
        -PassThru

    while ($true) {
        Start-Sleep -Seconds 1
        $apiProcess.Refresh()
        $dashboardProcess.Refresh()

        if ($apiProcess.HasExited) {
            throw "Mock backend stopped with exit code $($apiProcess.ExitCode)."
        }

        if ($dashboardProcess.HasExited) {
            throw "Dashboard dev server stopped with exit code $($dashboardProcess.ExitCode)."
        }
    }
}
finally {
    Stop-LiteProcess -Process $apiProcess -Name "mock backend"
    Stop-LiteProcess -Process $dashboardProcess -Name "dashboard dev server"
}
