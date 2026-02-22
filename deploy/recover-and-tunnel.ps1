#Requires -RunAsAdministrator
<#
.SYNOPSIS
    All-in-one: restart gmo-bot + install Cloudflare Tunnel.

.DESCRIPTION
    Run this single script via VNC to:
    1. Check and restart gmo-bot service
    2. Download and install cloudflared
    3. Register Cloudflare Tunnel as a service
    4. Display tunnel URL for Mac access

.PARAMETER InstallDir
    Bot installation directory. Default: C:\gmo-bot

.EXAMPLE
    cd C:\gmo-bot
    git pull origin main
    .\deploy\recover-and-tunnel.ps1
#>

param(
    [string]$InstallDir = "C:\gmo-bot"
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "`n========================================" -ForegroundColor Cyan
    Write-Host " $Message" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Write-Info {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Yellow
}

function Write-Err {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

Write-Host @"

  GMO Bot Recovery + Cloudflare Tunnel Setup
  ============================================

"@ -ForegroundColor Magenta

# ============================================================
# Phase 1: Bot Recovery
# ============================================================
Write-Step "Phase 1: Bot Recovery"

$botStatus = & nssm status gmo-bot 2>&1
Write-Info "Current gmo-bot status: $botStatus"

if ($botStatus -match "SERVICE_RUNNING") {
    Write-Success "gmo-bot is already running"
} else {
    Write-Info "Restarting gmo-bot..."
    $oldPref = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & nssm restart gmo-bot 2>&1 | Out-Null
    $ErrorActionPreference = $oldPref

    # Wait for startup
    for ($i = 0; $i -lt 15; $i++) {
        Start-Sleep -Seconds 1
        $botStatus = & nssm status gmo-bot 2>&1
        if ($botStatus -match "SERVICE_RUNNING") {
            break
        }
    }

    $botStatus = & nssm status gmo-bot 2>&1
    if ($botStatus -match "SERVICE_RUNNING") {
        Write-Success "gmo-bot restarted successfully"
    } else {
        Write-Err "gmo-bot failed to start (status: $botStatus)"
        Write-Err "Check: Get-Content $InstallDir\logs\gmo-bot-stderr.log -Tail 30"
        $continue = Read-Host "Continue with tunnel setup anyway? (y/N)"
        if ($continue -ne "y") { exit 1 }
    }
}

# Show recent log output
Write-Info "Recent bot log (last 5 lines):"
$stderrFile = "$InstallDir\logs\gmo-bot-stderr.log"
if (Test-Path $stderrFile) {
    Get-Content $stderrFile -Tail 5 | ForEach-Object { Write-Host "  $_" }
} else {
    Write-Info "No stderr log found"
}

# Also check bot-manager
Write-Step "Phase 1b: Bot Manager Check"

$bmStatus = & nssm status bot-manager 2>&1
Write-Info "bot-manager status: $bmStatus"

if ($bmStatus -notmatch "SERVICE_RUNNING") {
    Write-Info "Restarting bot-manager..."
    $oldPref = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & nssm restart bot-manager 2>&1 | Out-Null
    $ErrorActionPreference = $oldPref
    Start-Sleep -Seconds 3
    $bmStatus = & nssm status bot-manager 2>&1
    Write-Info "bot-manager status after restart: $bmStatus"
}

# ============================================================
# Phase 2: Cloudflare Tunnel
# ============================================================
Write-Step "Phase 2: Cloudflare Tunnel Setup"

# Call the dedicated setup script
$setupScript = "$InstallDir\deploy\setup-cloudflared.ps1"
if (Test-Path $setupScript) {
    & $setupScript -InstallDir $InstallDir
} else {
    Write-Err "setup-cloudflared.ps1 not found at $setupScript"
    Write-Err "Run: cd $InstallDir && git pull origin main"
    exit 1
}

# ============================================================
# Summary
# ============================================================
Write-Host @"

========================================
  All Done!
========================================

"@ -ForegroundColor Green

$botFinal = & nssm status gmo-bot 2>&1
$bmFinal = & nssm status bot-manager 2>&1
$cfFinal = & nssm status cloudflared 2>&1

Write-Host "  gmo-bot:      $botFinal" -ForegroundColor White
Write-Host "  bot-manager:  $bmFinal" -ForegroundColor White
Write-Host "  cloudflared:  $cfFinal" -ForegroundColor White
Write-Host ""

# Get tunnel URL
$cfStderrLog = "$InstallDir\logs\cloudflared-stderr.log"
if (Test-Path $cfStderrLog) {
    $match = Select-String -Path $cfStderrLog -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" | Select-Object -Last 1
    if ($match) {
        $url = $match.Matches[0].Value
        Write-Host "  Tunnel URL: $url" -ForegroundColor Green
        Write-Host ""
        Write-Host "  Test from Mac:" -ForegroundColor Yellow
        Write-Host "    curl -u admin:<password> `"$url/status`""
        Write-Host "    curl -u admin:<password> `"$url/api/logs`""
    }
}
Write-Host ""
