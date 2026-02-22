#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Install cloudflared and register as Windows service for Cloudflare Tunnel.

.DESCRIPTION
    This script:
    1. Downloads cloudflared.exe from GitHub (with size verification)
    2. Creates a Quick Tunnel to expose Bot Manager (port 80)
    3. Registers cloudflared as a Windows service via nssm
    4. Outputs the tunnel URL

    SECURITY NOTE: Quick Tunnels create a publicly accessible URL.
    Bot Manager's Basic Auth is the only access control.
    For production use, consider Named Tunnels with Cloudflare Access.

.PARAMETER InstallDir
    Bot installation directory. Default: C:\gmo-bot

.PARAMETER Port
    Local port to tunnel. Default: 80

.PARAMETER TestOnly
    Run tunnel in foreground for testing (don't register service).

.EXAMPLE
    .\setup-cloudflared.ps1
    # Install and register cloudflared service

.EXAMPLE
    .\setup-cloudflared.ps1 -TestOnly
    # Run tunnel in foreground for testing
#>

param(
    [string]$InstallDir = "C:\gmo-bot",
    [ValidateRange(1, 65535)]
    [int]$Port = 80,
    [switch]$TestOnly
)

$ErrorActionPreference = "Stop"

# TLS 1.2+
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$CloudflaredExe = "$InstallDir\cloudflared.exe"
$ServiceName = "cloudflared"
$LogDir = "$InstallDir\logs"

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

   ██████╗██╗      ██████╗ ██╗   ██╗██████╗ ███████╗██╗      █████╗ ██████╗ ███████╗██████╗
  ██╔════╝██║     ██╔═══██╗██║   ██║██╔══██╗██╔════╝██║     ██╔══██╗██╔══██╗██╔════╝██╔══██╗
  ██║     ██║     ██║   ██║██║   ██║██║  ██║█████╗  ██║     ███████║██████╔╝█████╗  ██║  ██║
  ██║     ██║     ██║   ██║██║   ██║██║  ██║██╔══╝  ██║     ██╔══██║██╔══██╗██╔══╝  ██║  ██║
  ╚██████╗███████╗╚██████╔╝╚██████╔╝██████╔╝██║     ███████╗██║  ██║██║  ██║███████╗██████╔╝
   ╚═════╝╚══════╝ ╚═════╝  ╚═════╝ ╚═════╝ ╚═╝     ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚═════╝

  Cloudflare Tunnel Setup (Quick Tunnel)

"@ -ForegroundColor Magenta

# ============================================================
# Step 1: Download cloudflared
# ============================================================
Write-Step "Step 1/3: Downloading cloudflared"

if (Test-Path $CloudflaredExe) {
    $version = & $CloudflaredExe --version 2>&1
    Write-Success "cloudflared already installed: $version"
} else {
    $downloadUrl = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
    Write-Info "Downloading from $downloadUrl ..."

    try {
        Invoke-WebRequest -Uri $downloadUrl -OutFile $CloudflaredExe -UseBasicParsing
        $fileSize = (Get-Item $CloudflaredExe).Length
        $fileSizeMB = [math]::Round($fileSize / 1MB, 2)
        Write-Success "Downloaded: $fileSizeMB MB"

        # Sanity check: cloudflared binary should be at least 5MB
        if ($fileSize -lt 5MB) {
            Write-Err "Downloaded file is suspiciously small ($fileSize bytes). Aborting."
            Remove-Item $CloudflaredExe -Force
            exit 1
        }

        $version = & $CloudflaredExe --version 2>&1
        Write-Success "Version: $version"
    } catch {
        Write-Err "Download failed: $_"
        if (Test-Path $CloudflaredExe) {
            Remove-Item $CloudflaredExe -Force
        }
        exit 1
    }
}

# ============================================================
# Step 2: Test or Register
# ============================================================

if ($TestOnly) {
    Write-Step "Step 2/2: Running tunnel in foreground (Ctrl+C to stop)"
    Write-Info "Tunnel URL will appear below..."
    Write-Host ""
    & $CloudflaredExe tunnel --url "http://localhost:$Port"
    exit 0
}

Write-Step "Step 2/3: Registering nssm service"

# Check nssm
if (-not (Get-Command nssm -ErrorAction SilentlyContinue)) {
    Write-Err "nssm is not installed or not in PATH."
    exit 1
}

# Ensure log directory exists
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}

# Stop existing service if running
$oldPref = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$existingStatus = & nssm status $ServiceName 2>&1
if ($existingStatus -match "SERVICE_RUNNING") {
    Write-Info "Stopping existing $ServiceName service..."
    & nssm stop $ServiceName 2>&1 | Out-Null
    Start-Sleep -Seconds 2
}
# Remove existing service registration
& nssm remove $ServiceName confirm 2>&1 | Out-Null
$ErrorActionPreference = $oldPref

# Register service
Write-Info "Registering $ServiceName service..."
& nssm install $ServiceName $CloudflaredExe
if ($LASTEXITCODE -ne 0) {
    Write-Err "Failed to register service (exit code: $LASTEXITCODE)"
    exit 1
}

& nssm set $ServiceName AppParameters "tunnel --url http://localhost:$Port"
& nssm set $ServiceName AppDirectory $InstallDir
& nssm set $ServiceName DisplayName "Cloudflare Tunnel"
& nssm set $ServiceName Description "Cloudflare Quick Tunnel for Bot Manager"
& nssm set $ServiceName Start SERVICE_AUTO_START
& nssm set $ServiceName AppStdout "$LogDir\cloudflared-stdout.log"
& nssm set $ServiceName AppStderr "$LogDir\cloudflared-stderr.log"
& nssm set $ServiceName AppStdoutCreationDisposition 4
& nssm set $ServiceName AppStderrCreationDisposition 4
& nssm set $ServiceName AppRotateFiles 1
& nssm set $ServiceName AppRotateBytes 1048576

Write-Success "Service registered"

# ============================================================
# Step 3: Start service and get URL
# ============================================================
Write-Step "Step 3/3: Starting tunnel"

# Rotate old log to avoid picking up stale URL
$stderrLog = "$LogDir\cloudflared-stderr.log"
if (Test-Path $stderrLog) {
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    Rename-Item $stderrLog "$LogDir\cloudflared-stderr-$timestamp.log"
}

$oldPref = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& nssm start $ServiceName 2>&1 | Out-Null
$ErrorActionPreference = $oldPref

Write-Info "Waiting for tunnel URL (up to 15 seconds)..."

$tunnelUrl = $null
for ($i = 0; $i -lt 15; $i++) {
    Start-Sleep -Seconds 1

    if (Test-Path $stderrLog) {
        $match = Select-String -Path $stderrLog -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" | Select-Object -Last 1
        if ($match) {
            $tunnelUrl = ($match.Matches[0].Value)
            break
        }
    }
}

$status = & nssm status $ServiceName 2>&1

Write-Host @"

========================================
  Cloudflare Tunnel Setup Complete!
========================================

"@ -ForegroundColor Green

if ($tunnelUrl) {
    Write-Host "  Tunnel URL:  $tunnelUrl" -ForegroundColor White
    Write-Host "  Status:      $status" -ForegroundColor White
} else {
    Write-Host "  Status:      $status" -ForegroundColor White
    Write-Host "  URL not yet available. Check log:" -ForegroundColor Yellow
    Write-Host "  Select-String -Path '$stderrLog' -Pattern 'trycloudflare.com'" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "[Test from Mac]" -ForegroundColor Yellow
if ($tunnelUrl) {
    Write-Host @"
  curl -u admin:<password> "$tunnelUrl/status"
  curl -u admin:<password> "$tunnelUrl/api/logs"

"@
} else {
    Write-Host @"
  curl -u admin:<password> "https://TUNNEL_URL/status"
  curl -u admin:<password> "https://TUNNEL_URL/api/logs"

"@
}

Write-Host "[Useful Commands]" -ForegroundColor Yellow
Write-Host @"
  nssm status $ServiceName                    # Check service
  nssm restart $ServiceName                   # Restart (new URL)
  Select-String -Path '$stderrLog' -Pattern 'trycloudflare.com'   # Get URL

  NOTE: Quick Tunnel URL changes on every restart.

"@
