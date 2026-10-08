# ─────────────────────────────────────────────────────────────────────────────
# ALGHREST — Git + GitHub Setup Script
# Run from PowerShell inside D:\Mohammed_Claude\mohammed\alghrest
#   cd D:\Mohammed_Claude\mohammed\alghrest
#   .\scripts\git_setup.ps1
# ─────────────────────────────────────────────────────────────────────────────

$ErrorActionPreference = "Stop"
$ROOT = "D:\Mohammed_Claude\mohammed\alghrest"

Write-Host "`n── ALGHREST Git Setup ──────────────────────────────" -ForegroundColor Cyan
Set-Location $ROOT

# ── STEP 1: git init ─────────────────────────────────────────────────────────
Write-Host "`n[1/6] Initialising git repo (branch: main)..." -ForegroundColor Yellow
git init -b main
git config --local user.name  "Mohammed"
git config --local user.email "mohammedkhachachi99@gmail.com"
Write-Host "      Identity set (local only — global config untouched)" -ForegroundColor Green

# ── STEP 2: Safety check — .env must be ignored ──────────────────────────────
Write-Host "`n[2/6] Checking .env is ignored before any git add..." -ForegroundColor Yellow
$status   = git status --short
$ignored  = git check-ignore -v .env 2>&1

Write-Host ""
Write-Host "  git status (first 20 lines):" -ForegroundColor Gray
$status | Select-Object -First 20 | ForEach-Object { Write-Host "    $_" }

Write-Host ""
Write-Host "  git check-ignore -v .env:" -ForegroundColor Gray
Write-Host "    $ignored"

if ($ignored -notmatch ".env") {
    Write-Host "`nERROR: .env is NOT ignored. Aborting — do not commit secrets!" -ForegroundColor Red
    exit 1
}
Write-Host "  ✓ .env is properly ignored" -ForegroundColor Green

# ── STEP 3: First commit — .gitignore + CLAUDE.md only ───────────────────────
Write-Host "`n[3/6] First commit: .gitignore + CLAUDE.md..." -ForegroundColor Yellow
git add .gitignore CLAUDE.md
git commit -m "chore: add .gitignore and CLAUDE.md"
Write-Host "  ✓ First commit done" -ForegroundColor Green

# ── STEP 4: Second commit — everything else ───────────────────────────────────
Write-Host "`n[4/6] Second commit: rest of codebase..." -ForegroundColor Yellow
git add .
git status --short | Select-Object -First 30 | ForEach-Object { Write-Host "    $_" }
git commit -m "feat: initial ALGHREST codebase — 32-agent autonomous trading system"
Write-Host "  ✓ Second commit done" -ForegroundColor Green

# ── STEP 5: Check gh CLI ──────────────────────────────────────────────────────
Write-Host "`n[5/6] Checking GitHub CLI (gh)..." -ForegroundColor Yellow
$ghPath = Get-Command gh -ErrorAction SilentlyContinue

if (-not $ghPath) {
    Write-Host "  gh CLI not found. Installing via winget..." -ForegroundColor Yellow
    winget install --id GitHub.cli --silent --accept-package-agreements --accept-source-agreements
    # Refresh PATH
    $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH","Machine") + ";" +
                [System.Environment]::GetEnvironmentVariable("PATH","User")
}

# ── STEP 6: Create private GitHub repo and push ──────────────────────────────
Write-Host "`n[6/6] Creating private GitHub repo 'alghrest' and pushing..." -ForegroundColor Yellow
Write-Host "      (you may be prompted to authenticate with GitHub)" -ForegroundColor Gray

gh repo create alghrest --private --source=. --remote=origin --push

Write-Host "`n✅ Done!" -ForegroundColor Green
Write-Host "   Repo: https://github.com/$(gh api user --jq .login)/alghrest" -ForegroundColor Cyan
Write-Host "   Log:  git log --oneline`n" -ForegroundColor Cyan
git log --oneline
