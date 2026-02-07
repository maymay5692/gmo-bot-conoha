#Requires -RunAsAdministrator
<#
.SYNOPSIS
    GMO Bot + Bot Manager One-Command Setup Script (Windows)

.DESCRIPTION
    This script automatically sets up:
    1. Chocolatey (Package Manager)
    2. Rust (For bot build)
    3. Python 3.11 (For Bot Manager)
    4. Git (For source code)
    5. NSSM (Windows Service Manager)
    6. GMO Bot build and service registration
    7. Bot Manager setup and service registration

.EXAMPLE
    .\windows-setup.ps1

.EXAMPLE
    .\windows-setup.ps1 -SkipBuild

.NOTES
    Run as Administrator
#>

param(
    [switch]$SkipBuild,
    [switch]$SkipServices,
    [string]$InstallDir = "C:\gmo-bot"
)

# Stop on error
$ErrorActionPreference = "Stop"

# Colored log functions
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

# Administrator check
function Test-Administrator {
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($currentUser)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Administrator)) {
    Write-Err "This script requires administrator privileges"
    Write-Host "Right-click PowerShell -> Select 'Run as Administrator'"
    exit 1
}

Write-Host @"

  ██████╗ ███╗   ███╗ ██████╗     ██████╗  ██████╗ ████████╗
 ██╔════╝ ████╗ ████║██╔═══██╗    ██╔══██╗██╔═══██╗╚══██╔══╝
 ██║  ███╗██╔████╔██║██║   ██║    ██████╔╝██║   ██║   ██║
 ██║   ██║██║╚██╔╝██║██║   ██║    ██╔══██╗██║   ██║   ██║
 ╚██████╔╝██║ ╚═╝ ██║╚██████╔╝    ██████╔╝╚██████╔╝   ██║
  ╚═════╝ ╚═╝     ╚═╝ ╚═════╝     ╚═════╝  ╚═════╝    ╚═╝

  Windows VPS One-Command Setup

"@ -ForegroundColor Magenta

# ============================================================
# Phase 1: Chocolatey Install
# ============================================================
Write-Step "Phase 1/7: Installing Chocolatey"

if (Get-Command choco -ErrorAction SilentlyContinue) {
    Write-Success "Chocolatey is already installed"
} else {
    Write-Info "Installing Chocolatey..."
    Set-ExecutionPolicy Bypass -Scope Process -Force
    [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
    Invoke-Expression ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))

    # Update PATH
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    Write-Success "Chocolatey installation complete"
}

# ============================================================
# Phase 2: Install Required Tools
# ============================================================
Write-Step "Phase 2/7: Installing Required Tools"

$tools = @(
    @{Name="git"; Check="git --version"},
    @{Name="rust"; Check="rustc --version"},
    @{Name="python311"; Check="python --version"},
    @{Name="nssm"; Check="nssm version"}
)

foreach ($tool in $tools) {
    Write-Info "Checking $($tool.Name)..."
    try {
        Invoke-Expression $tool.Check 2>&1 | Out-Null
        Write-Success "$($tool.Name) is already installed"
    } catch {
        Write-Info "Installing $($tool.Name)..."
        choco install $tool.Name -y --no-progress
        Write-Success "$($tool.Name) installation complete"
    }
}

# Reload PATH
$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")

# ============================================================
# Phase 3: Clone/Copy Project
# ============================================================
Write-Step "Phase 3/7: Setting Up Project"

if (Test-Path $InstallDir) {
    Write-Info "Existing install directory detected: $InstallDir"
    $response = Read-Host "Overwrite? (y/N)"
    if ($response -ne "y") {
        Write-Info "Using existing directory"
    } else {
        Remove-Item -Recurse -Force $InstallDir
        New-Item -ItemType Directory -Path $InstallDir | Out-Null
    }
} else {
    New-Item -ItemType Directory -Path $InstallDir | Out-Null
}

# Clone from GitHub
$repoUrl = "https://github.com/maymay5692/gmo-bot-conoha.git"
if (-not (Test-Path "$InstallDir\.git")) {
    Write-Info "Cloning repository..."
    git clone $repoUrl $InstallDir
    Write-Success "Clone complete"
} else {
    Write-Info "Fetching latest version..."
    Push-Location $InstallDir
    git pull origin main
    Pop-Location
    Write-Success "Update complete"
}

# ============================================================
# Phase 4: Environment Variables Setup
# ============================================================
Write-Step "Phase 4/7: Setting Up Environment Variables"

$envFile = "$InstallDir\.env"
if (Test-Path $envFile) {
    Write-Success ".env file already exists"
} else {
    # Prompt for API keys (skip if already configured)
    Write-Info "Please configure GMO Coin API keys"

    $apiKey = Read-Host "Enter API Key"
    $apiSecret = Read-Host "Enter API Secret"

    @"
# GMO Coin API Credentials
GMO_API_KEY=$apiKey
GMO_API_SECRET=$apiSecret
"@ | Out-File -FilePath $envFile -Encoding UTF8

    Write-Success ".env file created"
}

# Load .env file into environment variables
Get-Content $envFile | ForEach-Object {
    if ($_ -match "^([^#][^=]+)=(.*)$") {
        [System.Environment]::SetEnvironmentVariable($matches[1], $matches[2], "Process")
    }
}

# ============================================================
# Phase 5: Rust Build
# ============================================================
Write-Step "Phase 5/7: Building GMO Bot"

if ($SkipBuild) {
    Write-Info "Skipping build"
} else {
    Push-Location $InstallDir

    Write-Info "Building release... (this may take several minutes)"
    cargo build --release --bin gmo

    if ($LASTEXITCODE -ne 0) {
        Write-Err "Build failed"
        Pop-Location
        exit 1
    }

    Write-Success "Build complete: $InstallDir\target\release\gmo.exe"
    Pop-Location
}

# ============================================================
# Phase 6: Bot Manager Setup
# ============================================================
Write-Step "Phase 6/7: Setting Up Bot Manager"

$managerDir = "$InstallDir\bot-manager"

if (Test-Path $managerDir) {
    Push-Location $managerDir

    # Create Python virtual environment
    if (-not (Test-Path "venv")) {
        Write-Info "Creating Python virtual environment..."
        python -m venv venv
    }

    # Install dependencies
    Write-Info "Installing dependencies..."
    & "$managerDir\venv\Scripts\pip.exe" install --upgrade pip
    & "$managerDir\venv\Scripts\pip.exe" install -r requirements.txt
    & "$managerDir\venv\Scripts\pip.exe" install waitress  # WSGI server for Windows

    Write-Success "Bot Manager setup complete"
    Pop-Location
} else {
    Write-Err "bot-manager directory not found"
}

# ============================================================
# Phase 7: Windows Service Registration
# ============================================================
Write-Step "Phase 7/7: Registering Windows Services"

if ($SkipServices) {
    Write-Info "Skipping service registration"
} else {
    # Create log directory
    $logDir = "$InstallDir\logs"
    if (-not (Test-Path $logDir)) {
        New-Item -ItemType Directory -Path $logDir | Out-Null
    }

    # Load environment variables from .env file (minimize console display)
    $envContent = Get-Content $envFile -ErrorAction SilentlyContinue
    $apiKey = ($envContent | Where-Object { $_ -match "^GMO_API_KEY=" }) -replace "GMO_API_KEY=", ""
    $apiSecret = ($envContent | Where-Object { $_ -match "^GMO_API_SECRET=" }) -replace "GMO_API_SECRET=", ""

    # --- GMO Bot Service ---
    Write-Info "Registering GMO Bot service..."

    # Remove existing service
    nssm stop gmo-bot 2>$null
    nssm remove gmo-bot confirm 2>$null

    # Register new service (Note: env vars are stored in service config/registry)
    nssm install gmo-bot "$InstallDir\target\release\gmo.exe"
    nssm set gmo-bot AppDirectory "$InstallDir"
    nssm set gmo-bot AppEnvironmentExtra "GMO_API_KEY=$apiKey" "GMO_API_SECRET=$apiSecret"
    nssm set gmo-bot DisplayName "GMO Trading Bot"
    nssm set gmo-bot Description "GMO Coin High-Frequency Trading Bot"
    nssm set gmo-bot Start SERVICE_AUTO_START
    nssm set gmo-bot AppStdout "$logDir\gmo-bot-stdout.log"
    nssm set gmo-bot AppStderr "$logDir\gmo-bot-stderr.log"
    nssm set gmo-bot AppRotateFiles 1
    nssm set gmo-bot AppRotateBytes 10485760

    Write-Success "GMO Bot service registered"

    # --- Bot Manager Service ---
    Write-Info "Registering Bot Manager service..."

    # Remove existing service
    nssm stop bot-manager 2>$null
    nssm remove bot-manager confirm 2>$null

    # Waitress startup command
    $waitressExe = "$managerDir\venv\Scripts\waitress-serve.exe"

    nssm install bot-manager "$waitressExe"
    nssm set bot-manager AppParameters "--host=127.0.0.1 --port=5000 app:app"
    nssm set bot-manager AppDirectory "$managerDir"
    # Generate secure password
    $adminPass = -join ((65..90) + (97..122) + (48..57) | Get-Random -Count 16 | ForEach-Object {[char]$_})
    $secretKey = [guid]::NewGuid().ToString()

    # Save credentials to file (for later reference)
    $credFile = "$InstallDir\bot-manager-credentials.txt"
    @"
Bot Manager Credentials
=======================
URL:      http://127.0.0.1:5000
Username: admin
Password: $adminPass

Generated: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
"@ | Out-File -FilePath $credFile -Encoding UTF8

    nssm set bot-manager AppEnvironmentExtra `
        "FLASK_ENV=production" `
        "BOT_CONFIG_PATH=$InstallDir\src\trade-config.yaml" `
        "ADMIN_USER=admin" `
        "ADMIN_PASS=$adminPass" `
        "SECRET_KEY=$secretKey"
    nssm set bot-manager DisplayName "GMO Bot Manager"
    nssm set bot-manager Description "GMO Bot Web Management Interface"
    nssm set bot-manager Start SERVICE_AUTO_START
    nssm set bot-manager AppStdout "$logDir\bot-manager-stdout.log"
    nssm set bot-manager AppStderr "$logDir\bot-manager-stderr.log"

    Write-Success "Bot Manager service registered"
}

# ============================================================
# Complete
# ============================================================
Write-Host @"

========================================
  Setup Complete!
========================================

"@ -ForegroundColor Green

Write-Host "[Service Commands]" -ForegroundColor Yellow
Write-Host @"
  # GMO Bot
  nssm start gmo-bot        # Start
  nssm stop gmo-bot         # Stop
  nssm restart gmo-bot      # Restart
  nssm status gmo-bot       # Check status

  # Bot Manager
  nssm start bot-manager    # Start
  nssm stop bot-manager     # Stop

"@

Write-Host "[Bot Manager Access]" -ForegroundColor Yellow
if (Test-Path "$InstallDir\bot-manager-credentials.txt") {
    $creds = Get-Content "$InstallDir\bot-manager-credentials.txt"
    Write-Host ($creds | Out-String)
    Write-Host "  * Credentials saved to: $InstallDir\bot-manager-credentials.txt" -ForegroundColor Cyan
} else {
    Write-Host "  URL:      http://127.0.0.1:5000"
    Write-Host "  Username: admin"
    Write-Host "  * Check bot-manager-credentials.txt for password"
}
Write-Host ""

Write-Host "[View Logs]" -ForegroundColor Yellow
Write-Host @"
  GMO Bot:     Get-Content $logDir\gmo-bot-stdout.log -Wait -Tail 50
  Bot Manager: Get-Content $logDir\bot-manager-stdout.log -Wait -Tail 50

"@

Write-Host "[Next Steps]" -ForegroundColor Cyan
Write-Host @"
  1. Start services:
     nssm start gmo-bot
     nssm start bot-manager

  2. Access Bot Manager:
     Open http://127.0.0.1:5000 in browser

  3. Check trading config:
     $InstallDir\src\trade-config.yaml

"@

Write-Host "Setup completed successfully." -ForegroundColor Green
