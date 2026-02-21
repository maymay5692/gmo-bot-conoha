#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Download and deploy GMO Bot binary from GitHub Releases.

.DESCRIPTION
    This script:
    1. Fetches the latest (or specified) release from GitHub
    2. Downloads gmo.exe
    3. Stops the gmo-bot service via nssm
    4. Backs up the existing binary
    5. Deploys the new binary
    6. Syncs config files via git pull
    7. Restarts the service
    8. Rolls back on startup failure

.PARAMETER Version
    Specific release version to download (e.g., v1.0.0).
    Defaults to the latest release.

.PARAMETER SkipRestart
    Download and replace the binary without restarting the service.

.PARAMETER UpdateBotManager
    Also update bot-manager via git pull + pip install + restart.

.PARAMETER Token
    GitHub personal access token for private repositories.

.PARAMETER InstallDir
    Bot installation directory. Default: C:\gmo-bot

.EXAMPLE
    .\download-release.ps1
    # Downloads and deploys the latest release

.EXAMPLE
    .\download-release.ps1 -Version v1.0.0
    # Downloads and deploys a specific version

.EXAMPLE
    .\download-release.ps1 -UpdateBotManager
    # Updates both gmo.exe and bot-manager
#>

param(
    [string]$Version,
    [switch]$SkipRestart,
    [switch]$UpdateBotManager,
    [string]$Token = $env:GITHUB_TOKEN,
    [string]$InstallDir = "C:\gmo-bot"
)

$ErrorActionPreference = "Stop"

# Enforce TLS 1.2+ for GitHub API
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# Validate Version format
if ($Version -and $Version -notmatch '^v\d+\.\d+\.\d+(-[\w.]+)?$') {
    Write-Host "[ERROR] Invalid version format: $Version (expected: v1.0.0)" -ForegroundColor Red
    exit 1
}

# Check nssm availability
if (-not $SkipRestart -and -not (Get-Command nssm -ErrorAction SilentlyContinue)) {
    Write-Host "[ERROR] nssm is not installed or not in PATH." -ForegroundColor Red
    Write-Host "Install via: choco install nssm" -ForegroundColor Yellow
    exit 1
}

$RepoOwner = "maymay5692"
$RepoName = "gmo-bot-conoha"
$ServiceName = "gmo-bot"
$BinaryName = "gmo.exe"
$BinaryPath = "$InstallDir\target\release\$BinaryName"

# --- Logging helpers ---

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

# --- GitHub API helpers ---

function Get-GitHubHeaders {
    $headers = @{ "User-Agent" = "gmo-bot-deploy" }
    if ($Token) {
        $headers["Authorization"] = "Bearer $Token"
    }
    return $headers
}

function Get-ReleaseInfo {
    param([string]$TargetVersion)

    $headers = Get-GitHubHeaders

    if ($TargetVersion) {
        $url = "https://api.github.com/repos/$RepoOwner/$RepoName/releases/tags/$TargetVersion"
    } else {
        $url = "https://api.github.com/repos/$RepoOwner/$RepoName/releases/latest"
    }

    try {
        $response = Invoke-RestMethod -Uri $url -Headers $headers -Method Get
        return $response
    } catch {
        if ($_.Exception.Response.StatusCode -eq 404) {
            Write-Err "Release not found: $TargetVersion"
            Write-Err "Check available releases: https://github.com/$RepoOwner/$RepoName/releases"
        } else {
            $errorMsg = "$_"
            if ($Token) {
                $errorMsg = $errorMsg -replace [regex]::Escape($Token), "***"
            }
            Write-Err "GitHub API request failed: $errorMsg"
        }
        exit 1
    }
}

function Get-AssetDownloadUrl {
    param($Release)

    $asset = $Release.assets | Where-Object { $_.name -eq $BinaryName }
    if (-not $asset) {
        Write-Err "'$BinaryName' not found in release $($Release.tag_name)"
        Write-Err "Available assets:"
        foreach ($a in $Release.assets) {
            Write-Err "  - $($a.name)"
        }
        exit 1
    }

    return $asset.browser_download_url
}

# --- Service helpers ---

function Stop-BotService {
    Write-Info "Stopping $ServiceName service..."
    $oldPref = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $status = & nssm status $ServiceName 2>&1
    if ($status -match "SERVICE_RUNNING") {
        & nssm stop $ServiceName 2>&1 | Out-Null
        Start-Sleep -Seconds 2
        Write-Success "$ServiceName stopped"
    } else {
        Write-Info "$ServiceName is not running (status: $status)"
    }
    $ErrorActionPreference = $oldPref
}

function Start-BotService {
    Write-Info "Starting $ServiceName service..."
    # nssm writes SERVICE_START_PENDING to stderr which triggers NativeCommandError
    # with $ErrorActionPreference="Stop". Temporarily allow it.
    $oldPref = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & nssm start $ServiceName 2>&1 | Out-Null
    $ErrorActionPreference = $oldPref

    # Wait up to 15 seconds for SERVICE_RUNNING (START_PENDING is normal)
    $maxWait = 15
    for ($i = 0; $i -lt $maxWait; $i++) {
        Start-Sleep -Seconds 1
        $status = & nssm status $ServiceName 2>&1
        if ($status -match "SERVICE_RUNNING") {
            Write-Success "$ServiceName started successfully"
            return $true
        }
        if ($status -match "SERVICE_STOPPED") {
            Write-Err "$ServiceName stopped unexpectedly"
            return $false
        }
    }

    # Final check after timeout
    $status = & nssm status $ServiceName 2>&1
    if ($status -match "SERVICE_RUNNING") {
        Write-Success "$ServiceName started successfully"
        return $true
    } else {
        Write-Err "$ServiceName failed to start after ${maxWait}s (status: $status)"
        return $false
    }
}

# --- Main ---

Write-Host @"

  ██████╗ ███╗   ███╗ ██████╗     ██████╗  ██████╗ ████████╗
 ██╔════╝ ████╗ ████║██╔═══██╗    ██╔══██╗██╔═══██╗╚══██╔══╝
 ██║  ███╗██╔████╔██║██║   ██║    ██████╔╝██║   ██║   ██║
 ██║   ██║██║╚██╔╝██║██║   ██║    ██╔══██╗██║   ██║   ██║
 ╚██████╔╝██║ ╚═╝ ██║╚██████╔╝    ██████╔╝╚██████╔╝   ██║
  ╚═════╝ ╚═╝     ╚═╝ ╚═════╝     ╚═════╝  ╚═════╝    ╚═╝

  Release Downloader & Deployer

"@ -ForegroundColor Magenta

# ============================================================
# Step 1: Fetch release info
# ============================================================
Write-Step "Step 1/5: Fetching release info"

$release = Get-ReleaseInfo -TargetVersion $Version
$tagName = $release.tag_name
$publishedAt = $release.published_at

Write-Success "Found release: $tagName (published: $publishedAt)"

$downloadUrl = Get-AssetDownloadUrl -Release $release
Write-Info "Download URL: $downloadUrl"

# ============================================================
# Step 2: Download binary
# ============================================================
Write-Step "Step 2/5: Downloading $BinaryName"

$tempDir = "$InstallDir\temp-release"
if (Test-Path $tempDir) {
    Remove-Item -Recurse -Force $tempDir
}
New-Item -ItemType Directory -Path $tempDir | Out-Null

$tempBinary = "$tempDir\$BinaryName"
$headers = Get-GitHubHeaders

try {
    Write-Info "Downloading $tagName/$BinaryName ..."
    if ($Token) {
        $headers["Accept"] = "application/octet-stream"
        Invoke-WebRequest -Uri $downloadUrl -Headers $headers -OutFile $tempBinary
    } else {
        Invoke-WebRequest -Uri $downloadUrl -OutFile $tempBinary
    }
    $fileSize = (Get-Item $tempBinary).Length
    $fileSizeMB = [math]::Round($fileSize / 1MB, 2)
    Write-Success "Downloaded: $fileSizeMB MB"

    if ($fileSize -lt 1MB) {
        Write-Err "Downloaded file is suspiciously small ($fileSize bytes). Aborting."
        Remove-Item -Recurse -Force $tempDir
        exit 1
    }
} catch {
    $errorMsg = "$_"
    if ($Token) {
        $errorMsg = $errorMsg -replace [regex]::Escape($Token), "***"
    }
    Write-Err "Download failed: $errorMsg"
    Remove-Item -Recurse -Force $tempDir
    exit 1
}

# ============================================================
# Step 3: Deploy binary
# ============================================================
Write-Step "Step 3/5: Deploying binary"

# Ensure target directory exists
$targetDir = Split-Path $BinaryPath -Parent
if (-not (Test-Path $targetDir)) {
    New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
}

# Stop service before replacing binary
if (-not $SkipRestart) {
    Stop-BotService
}

# Backup existing binary
$backupPath = "$BinaryPath.bak"
if (Test-Path $BinaryPath) {
    Write-Info "Backing up existing binary to $backupPath"
    Copy-Item -Path $BinaryPath -Destination $backupPath -Force
    Write-Success "Backup created"
}

# Replace binary
Move-Item -Path $tempBinary -Destination $BinaryPath -Force
Write-Success "Binary deployed: $BinaryPath"

# Cleanup temp
Remove-Item -Recurse -Force $tempDir

# ============================================================
# Step 4: Sync config files (git pull)
# ============================================================
Write-Step "Step 4/5: Syncing config files"

Write-Info "Running git pull to sync trade-config.yaml and other files..."
try {
    Push-Location $InstallDir
    $gitOutput = & git pull origin main 2>&1
    Pop-Location
    Write-Success "Config synced: $gitOutput"
} catch {
    Pop-Location
    Write-Info "WARNING: git pull failed: $_"
    Write-Info "Continuing with existing config files..."
}

# ============================================================
# Step 5: Restart service
# ============================================================
Write-Step "Step 5/5: Restarting service"

if ($SkipRestart) {
    Write-Info "Skipping restart (-SkipRestart specified)"
    Write-Info "Run 'nssm restart $ServiceName' to apply the update"
} else {
    $started = Start-BotService
    if (-not $started) {
        Write-Err "Service failed to start. Rolling back..."

        if (Test-Path $backupPath) {
            Copy-Item -Path $backupPath -Destination $BinaryPath -Force
            Write-Info "Restored previous binary"

            $rollbackStarted = Start-BotService
            if ($rollbackStarted) {
                Write-Success "Rollback successful - previous version is running"
            } else {
                Write-Err "Rollback also failed. Manual intervention required."
                Write-Err "Backup binary: $backupPath"
            }
        } else {
            Write-Err "No backup available for rollback. Manual intervention required."
        }
        exit 1
    }
}

# ============================================================
# Optional: Update Bot Manager
# ============================================================
if ($UpdateBotManager) {
    Write-Step "Updating Bot Manager"

    $managerDir = "$InstallDir\bot-manager"
    $managerService = "bot-manager"

    if (-not (Test-Path $managerDir)) {
        Write-Err "bot-manager directory not found: $managerDir"
    } else {
        # Stop bot-manager service
        Write-Info "Stopping $managerService ..."
        $oldPref = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        & nssm stop $managerService 2>&1 | Out-Null
        $ErrorActionPreference = $oldPref

        # Git pull
        Write-Info "Pulling latest code..."
        Push-Location $InstallDir
        & git pull origin main
        Pop-Location
        Write-Success "Code updated"

        # Reinstall dependencies
        Write-Info "Installing Python dependencies..."
        $pipExe = "$managerDir\venv\Scripts\pip.exe"
        if (Test-Path $pipExe) {
            & $pipExe install -r "$managerDir\requirements.txt" --quiet
            Write-Success "Dependencies updated"
        } else {
            Write-Err "pip not found at $pipExe - skipping dependency install"
        }

        # Restart bot-manager service
        Write-Info "Starting $managerService ..."
        $oldPref = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        & nssm start $managerService
        $ErrorActionPreference = $oldPref
        Start-Sleep -Seconds 3

        $bmStatus = & nssm status $managerService 2>&1
        if ($bmStatus -match "SERVICE_RUNNING") {
            Write-Success "$managerService started successfully"
        } else {
            Write-Err "$managerService failed to start (status: $bmStatus)"
        }
    }
}

# ============================================================
# Summary
# ============================================================
Write-Host @"

========================================
  Deploy Complete!
========================================

"@ -ForegroundColor Green

Write-Host "  Version:  $tagName" -ForegroundColor White
Write-Host "  Binary:   $BinaryPath" -ForegroundColor White
Write-Host "  Backup:   $backupPath" -ForegroundColor White
Write-Host ""

Write-Host "[Useful Commands]" -ForegroundColor Yellow
Write-Host @"
  nssm status $ServiceName       # Check service status
  nssm restart $ServiceName      # Restart service
  Get-Content $InstallDir\logs\gmo-bot-stderr.log -Wait -Tail 50   # View logs

"@
