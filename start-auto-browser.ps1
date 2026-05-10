# Auto Browser Backend Startup Script
# Starts the Docker Compose stack that serves the MCP HTTP endpoint on port 8000
# Called by Claude Desktop before sessions that need auto-browser

param(
    [switch]$Detached,       # Run containers in background (default: foreground)
    [switch]$Rebuild,        # Force image rebuild before start
    [switch]$Status          # Just check status and exit
)

$AutoBrowserDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Port = 8000

function Test-DockerAvailable {
    $null = Get-Command docker -ErrorAction SilentlyContinue
    return $?
}

function Test-BackendReachable {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/health" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
        return $r.StatusCode -lt 400
    } catch {
        try {
            # Some versions expose /docs instead of /health
            $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/docs" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
            return $r.StatusCode -lt 400
        } catch {
            return $false
        }
    }
}

# Status check only
if ($Status) {
    if (Test-BackendReachable) {
        Write-Host "[OK] Auto Browser backend is running on port $Port"
        exit 0
    } else {
        Write-Host "[DOWN] Auto Browser backend is NOT running on port $Port"
        exit 1
    }
}

# Check Docker
if (-not (Test-DockerAvailable)) {
    Write-Error @"
Docker is not installed or not in PATH.

Auto Browser requires Docker Desktop. To install:
  winget install -e --id Docker.DockerDesktop
  -- or --
  Download from: https://www.docker.com/products/docker-desktop/

After install, restart your terminal and run this script again.
"@
    exit 1
}

# Check if already running
if (Test-BackendReachable) {
    Write-Host "[OK] Auto Browser backend already running on port $Port. Nothing to do."
    exit 0
}

Write-Host "Starting Auto Browser backend..."

Set-Location $AutoBrowserDir

$ComposeArgs = @("compose", "up")
if ($Detached -or -not $PSBoundParameters.ContainsKey('Detached')) {
    $ComposeArgs += "-d"
}
if ($Rebuild) {
    $ComposeArgs += "--build"
}

& docker @ComposeArgs

if ($LASTEXITCODE -ne 0) {
    Write-Error "docker compose up failed with exit code $LASTEXITCODE"
    exit $LASTEXITCODE
}

# Wait up to 30s for backend to be reachable
Write-Host "Waiting for backend to become ready..."
$deadline = [DateTime]::UtcNow.AddSeconds(30)
while ([DateTime]::UtcNow -lt $deadline) {
    if (Test-BackendReachable) {
        Write-Host "[OK] Auto Browser backend ready at http://127.0.0.1:$Port"
        exit 0
    }
    Start-Sleep -Seconds 2
}

Write-Error "Backend did not become reachable within 30 seconds. Check: docker compose logs"
exit 1
