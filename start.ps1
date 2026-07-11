# Nine Frogs -- Windows startup script
# Run from the repo root: .\start.ps1
# Optional flags:
#   -SkipRedis   -- Redis is already running externally
#   -SkipOllama  -- Using a cloud LLM provider (Anthropic/OpenAI)
#   -SkipWorker  -- Don't start the Celery worker (Labs features won't work)
param(
    [switch]$SkipRedis,
    [switch]$SkipOllama,
    [switch]$SkipWorker
)

$Root   = $PSScriptRoot
$App    = Join-Path $Root "ninefrogs"
$StartErrors = @()

function Write-Step { param($msg) Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-OK   { param($msg) Write-Host "    [OK] $msg" -ForegroundColor Green }
function Write-Warn { param($msg) Write-Host "    [WARN] $msg" -ForegroundColor Yellow }
function Write-Fail { param($msg) Write-Host "    [FAIL] $msg" -ForegroundColor Red }

# --- 0. BLOOD FOR THE BLOOD GOD — kill stale processes on all Nine Frogs ports ---
Write-Step "Purging stale processes (8080, 6379, 11434, 5555)"
foreach ($port in @(8080, 6379, 11434, 5555)) {
    $pids = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($p in $pids) {
        try {
            Stop-Process -Id $p -Force -ErrorAction Stop
            Write-OK "Killed PID $p on :$port"
        } catch {
            Write-Warn "Could not kill PID $p on :$port (may already be gone)"
        }
    }
}

# --- 1. Sanity checks ---
Write-Step "Checking prerequisites"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Fail "uv not found. Install from https://docs.astral.sh/uv/"
    exit 1
}
Write-OK "uv found"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Warn "docker not found -- Redis and Docker-based Lab challenges won't work"
} else {
    Write-OK "docker found"
}

if (-not (Test-Path "$App\.env")) {
    Write-Warn ".env not found -- copying .env.example"
    Copy-Item "$App\.env.example" "$App\.env"
    Write-Warn "Edit $App\.env before continuing (DATABASE_URL, LLM settings, etc.)"
}

# --- 2. Redis ---
if (-not $SkipRedis) {
    Write-Step "Starting Redis (Docker)"
    $redisPing = docker exec redis redis-cli ping 2>$null
    if ($redisPing -eq "PONG") {
        Write-OK "Redis already running"
    } else {
        docker start redis 2>$null | Out-Null
        Start-Sleep -Milliseconds 800
        $redisPing = docker exec redis redis-cli ping 2>$null
        if ($redisPing -eq "PONG") {
            Write-OK "Redis started (existing container)"
        } else {
            docker run -d --name redis -p 6379:6379 redis:7-alpine 2>$null | Out-Null
            Start-Sleep -Seconds 2
            $redisPing = docker exec redis redis-cli ping 2>$null
            if ($redisPing -eq "PONG") {
                Write-OK "Redis started (new container)"
            } else {
                Write-Fail "Could not start Redis -- check Docker"
                $StartErrors += "Redis"
            }
        }
    }
} else {
    Write-Warn "Skipping Redis (-SkipRedis)"
}

# --- 3. Ollama ---
if (-not $SkipOllama) {
    Write-Step "Checking Ollama"
    try {
        Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 3 -ErrorAction Stop | Out-Null
        Write-OK "Ollama is running"
    } catch {
        Write-Warn "Ollama not responding on :11434"
        if (Get-Command ollama -ErrorAction SilentlyContinue) {
            Write-Warn "Starting Ollama in background..."
            Start-Process "ollama" -ArgumentList "serve" -WindowStyle Hidden
            Start-Sleep -Seconds 3
            Write-OK "Ollama started"
        } else {
            Write-Warn "ollama CLI not found -- install from https://ollama.com or use -SkipOllama"
        }
    }
} else {
    Write-Warn "Skipping Ollama (-SkipOllama)"
}

# --- 4. Python deps ---
Write-Step "Syncing Python dependencies (uv sync)"
Push-Location $App
uv sync --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Fail "uv sync failed"
    Pop-Location
    exit 1
}
Write-OK "Dependencies ready"
Pop-Location

# --- 5. Celery worker ---
if (-not $SkipWorker) {
    Write-Step "Starting Celery worker (new terminal window)"
    $celeryCmd = "cd '$App'; uv run celery -A lab.tasks.celery_app worker --loglevel=info --pool=solo; pause"
    Start-Process "powershell.exe" -ArgumentList "-NoExit", "-Command", $celeryCmd
    Write-OK "Celery worker window launched"
} else {
    Write-Warn "Skipping Celery worker (-SkipWorker)"
}

# --- 6. Summary ---
Write-Step "Summary"
if ($StartErrors.Count -gt 0) {
    Write-Warn "Started with errors: $($StartErrors -join ', ')"
}

Write-Host ""
Write-Host "Starting Nine Frogs app at http://localhost:8080 ..." -ForegroundColor Cyan
Write-Host "(Ctrl+C to stop)" -ForegroundColor DarkGray
Write-Host ""

# --- 7. FastAPI app (foreground) ---
Push-Location $App
uv run python main.py
Pop-Location
