# ─────────────────────────────────────────────────────────────────────────────
#  Enterprise RAG — Local Dev Launcher (Windows PowerShell)
#  Usage:  .\start_local.ps1
# ─────────────────────────────────────────────────────────────────────────────

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║     Enterprise vLLM RAG — Local Dev Startup                ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# ── Step 1: Check Docker is running ──────────────────────────────────────────
Write-Host "▶ Checking Docker..." -ForegroundColor Yellow
try {
    docker info | Out-Null
    Write-Host "  ✅ Docker is running" -ForegroundColor Green
} catch {
    Write-Host "  ❌ Docker is not running. Please start Docker Desktop first." -ForegroundColor Red
    exit 1
}

# ── Step 2: Start infrastructure containers (no GPU needed) ──────────────────
Write-Host ""
Write-Host "▶ Starting Qdrant + Redis containers..." -ForegroundColor Yellow

docker compose up -d qdrant-vector-db redis-cache

Write-Host "  ✅ Qdrant  → http://localhost:6333" -ForegroundColor Green
Write-Host "  ✅ Redis   → localhost:6379" -ForegroundColor Green

# Wait for Qdrant to be healthy
Write-Host ""
Write-Host "▶ Waiting for Qdrant to be healthy..." -ForegroundColor Yellow
$attempts = 0
do {
    Start-Sleep -Seconds 2
    $attempts++
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:6333/healthz" -TimeoutSec 2 -ErrorAction SilentlyContinue
        if ($response.StatusCode -eq 200) { break }
    } catch {}
} while ($attempts -lt 15)

if ($attempts -ge 15) {
    Write-Host "  ⚠️  Qdrant did not respond in time. Continuing anyway..." -ForegroundColor Yellow
} else {
    Write-Host "  ✅ Qdrant is healthy" -ForegroundColor Green
}

# ── Step 3: Python venv setup ─────────────────────────────────────────────────
Write-Host ""
Write-Host "▶ Setting up Python virtual environment..." -ForegroundColor Yellow

$rootDir = $PSScriptRoot
$venvPath = Join-Path $rootDir ".venv"

if (-not (Test-Path $venvPath)) {
    Write-Host "  Creating .venv..." -ForegroundColor Cyan
    python -m venv $venvPath
}

$activateScript = Join-Path $venvPath "Scripts\Activate.ps1"
. $activateScript

Write-Host "  Installing Python dependencies..." -ForegroundColor Cyan
pip install -r (Join-Path $rootDir "requirements.txt") -q --no-warn-script-location

Write-Host "  ✅ Python environment ready" -ForegroundColor Green

# ── Step 4: Start FastAPI backend ─────────────────────────────────────────────
Write-Host ""
Write-Host "▶ Starting FastAPI backend on port 8080..." -ForegroundColor Yellow

$env:DEMO_MODE = "true"
$env:QDRANT_HOST = "localhost"
$env:QDRANT_PORT = "6333"
$env:REDIS_HOST = "localhost"
$env:REDIS_PORT = "6379"
$env:VLLM_HOST = "localhost"
$env:APP_ENV = "development"

# Launch FastAPI in a new terminal window
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    ". '$activateScript'; cd '$rootDir'; uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload --log-level info"
) -WindowStyle Normal

Write-Host "  ✅ FastAPI starting  → http://localhost:8080" -ForegroundColor Green
Write-Host "  📄 API Docs          → http://localhost:8080/docs" -ForegroundColor Cyan

Start-Sleep -Seconds 4

# ── Step 5: Seed sample data ──────────────────────────────────────────────────
Write-Host ""
$seedChoice = Read-Host "▶ Seed sample enterprise documents into Qdrant? (y/n)"
if ($seedChoice -eq "y" -or $seedChoice -eq "Y") {
    Write-Host "  Seeding data..." -ForegroundColor Cyan
    $env:API_URL = "http://localhost:8080"
    python (Join-Path $rootDir "scripts\seed_data.py")
}

# ── Step 6: Start Next.js frontend ────────────────────────────────────────────
Write-Host ""
Write-Host "▶ Starting Next.js frontend on port 3000..." -ForegroundColor Yellow

$frontendDir = Join-Path $rootDir "frontend-node"

if (-not (Test-Path (Join-Path $frontendDir "node_modules"))) {
    Write-Host "  Installing npm packages..." -ForegroundColor Cyan
    Push-Location $frontendDir
    npm install -q
    Pop-Location
}

Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "cd '$frontendDir'; `$env:NEXT_PUBLIC_API_URL='http://localhost:8080'; npm run dev"
) -WindowStyle Normal

Write-Host "  ✅ Next.js starting  → http://localhost:3000" -ForegroundColor Green

# ── Done ──────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║  🚀 All services launched! Open in browser:                ║" -ForegroundColor Cyan
Write-Host "║     http://localhost:3000   (Next.js UI)                   ║" -ForegroundColor Cyan
Write-Host "║     http://localhost:8080/docs  (FastAPI Swagger)          ║" -ForegroundColor Cyan
Write-Host "║     http://localhost:6333/dashboard  (Qdrant Dashboard)    ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# Auto-open browser
Start-Sleep -Seconds 5
Start-Process "http://localhost:3000"
