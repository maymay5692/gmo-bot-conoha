#Requires -RunAsAdministrator
<#
.SYNOPSIS
    GMO Bot + Bot Manager ワンコマンドセットアップスクリプト (Windows)

.DESCRIPTION
    このスクリプトは以下を自動でセットアップします:
    1. Chocolatey (パッケージマネージャー)
    2. Rust (ボットのビルド用)
    3. Python 3.11 (Bot Manager用)
    4. Git (ソースコード取得用)
    5. NSSM (Windowsサービス管理用)
    6. GMO Bot のビルドとサービス登録
    7. Bot Manager のセットアップとサービス登録

.EXAMPLE
    .\windows-setup.ps1

.EXAMPLE
    .\windows-setup.ps1 -SkipBuild

.NOTES
    管理者権限で実行してください
#>

param(
    [switch]$SkipBuild,
    [switch]$SkipServices,
    [string]$InstallDir = "C:\gmo-bot"
)

# エラー時に停止
$ErrorActionPreference = "Stop"

# 色付きログ関数
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

# 管理者権限チェック
function Test-Administrator {
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($currentUser)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Administrator)) {
    Write-Err "このスクリプトは管理者権限で実行してください"
    Write-Host "PowerShellを右クリック → '管理者として実行' を選択してください"
    exit 1
}

Write-Host @"

  ██████╗ ███╗   ███╗ ██████╗     ██████╗  ██████╗ ████████╗
 ██╔════╝ ████╗ ████║██╔═══██╗    ██╔══██╗██╔═══██╗╚══██╔══╝
 ██║  ███╗██╔████╔██║██║   ██║    ██████╔╝██║   ██║   ██║
 ██║   ██║██║╚██╔╝██║██║   ██║    ██╔══██╗██║   ██║   ██║
 ╚██████╔╝██║ ╚═╝ ██║╚██████╔╝    ██████╔╝╚██████╔╝   ██║
  ╚═════╝ ╚═╝     ╚═╝ ╚═════╝     ╚═════╝  ╚═════╝    ╚═╝

  Windows VPS ワンコマンドセットアップ

"@ -ForegroundColor Magenta

# ============================================================
# Phase 1: Chocolatey インストール
# ============================================================
Write-Step "Phase 1/7: Chocolatey インストール"

if (Get-Command choco -ErrorAction SilentlyContinue) {
    Write-Success "Chocolatey は既にインストールされています"
} else {
    Write-Info "Chocolatey をインストール中..."
    Set-ExecutionPolicy Bypass -Scope Process -Force
    [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
    Invoke-Expression ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))

    # PATHを更新
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    Write-Success "Chocolatey インストール完了"
}

# ============================================================
# Phase 2: 必要なツールのインストール
# ============================================================
Write-Step "Phase 2/7: 必要なツールのインストール"

$tools = @(
    @{Name="git"; Check="git --version"},
    @{Name="rust"; Check="rustc --version"},
    @{Name="python311"; Check="python --version"},
    @{Name="nssm"; Check="nssm version"}
)

foreach ($tool in $tools) {
    Write-Info "$($tool.Name) をチェック中..."
    try {
        Invoke-Expression $tool.Check 2>&1 | Out-Null
        Write-Success "$($tool.Name) は既にインストールされています"
    } catch {
        Write-Info "$($tool.Name) をインストール中..."
        choco install $tool.Name -y --no-progress
        Write-Success "$($tool.Name) インストール完了"
    }
}

# PATHを再読み込み
$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")

# ============================================================
# Phase 3: プロジェクトのクローン/コピー
# ============================================================
Write-Step "Phase 3/7: プロジェクトのセットアップ"

if (Test-Path $InstallDir) {
    Write-Info "既存のインストールディレクトリを検出: $InstallDir"
    $response = Read-Host "上書きしますか? (y/N)"
    if ($response -ne "y") {
        Write-Info "既存のディレクトリを使用します"
    } else {
        Remove-Item -Recurse -Force $InstallDir
        New-Item -ItemType Directory -Path $InstallDir | Out-Null
    }
} else {
    New-Item -ItemType Directory -Path $InstallDir | Out-Null
}

# GitHubからクローン
$repoUrl = "https://github.com/maymay5692/gmo-bot-conoha.git"
if (-not (Test-Path "$InstallDir\.git")) {
    Write-Info "リポジトリをクローン中..."
    git clone $repoUrl $InstallDir
    Write-Success "クローン完了"
} else {
    Write-Info "最新版を取得中..."
    Push-Location $InstallDir
    git pull origin main
    Pop-Location
    Write-Success "更新完了"
}

# ============================================================
# Phase 4: 環境変数ファイルの設定
# ============================================================
Write-Step "Phase 4/7: 環境変数の設定"

$envFile = "$InstallDir\.env"
if (Test-Path $envFile) {
    Write-Success ".env ファイルが既に存在します"
} else {
    # APIキーの入力を求める（既に設定されている場合はスキップ）
    Write-Info "GMO Coin APIキーを設定してください"

    $apiKey = Read-Host "API Key を入力"
    $apiSecret = Read-Host "API Secret を入力"

    @"
# GMO Coin API認証情報
GMO_API_KEY=$apiKey
GMO_API_SECRET=$apiSecret
"@ | Out-File -FilePath $envFile -Encoding UTF8

    Write-Success ".env ファイルを作成しました"
}

# .envファイルを読み込んで環境変数に設定
Get-Content $envFile | ForEach-Object {
    if ($_ -match "^([^#][^=]+)=(.*)$") {
        [System.Environment]::SetEnvironmentVariable($matches[1], $matches[2], "Process")
    }
}

# ============================================================
# Phase 5: Rust ビルド
# ============================================================
Write-Step "Phase 5/7: GMO Bot ビルド"

if ($SkipBuild) {
    Write-Info "ビルドをスキップします"
} else {
    Push-Location $InstallDir

    Write-Info "リリースビルド中... (数分かかります)"
    cargo build --release --bin gmo

    if ($LASTEXITCODE -ne 0) {
        Write-Err "ビルドに失敗しました"
        Pop-Location
        exit 1
    }

    Write-Success "ビルド完了: $InstallDir\target\release\gmo.exe"
    Pop-Location
}

# ============================================================
# Phase 6: Bot Manager セットアップ
# ============================================================
Write-Step "Phase 6/7: Bot Manager セットアップ"

$managerDir = "$InstallDir\bot-manager"

if (Test-Path $managerDir) {
    Push-Location $managerDir

    # Python仮想環境作成
    if (-not (Test-Path "venv")) {
        Write-Info "Python仮想環境を作成中..."
        python -m venv venv
    }

    # 依存関係インストール
    Write-Info "依存関係をインストール中..."
    & "$managerDir\venv\Scripts\pip.exe" install --upgrade pip
    & "$managerDir\venv\Scripts\pip.exe" install -r requirements.txt
    & "$managerDir\venv\Scripts\pip.exe" install waitress  # Windows用WSGIサーバー

    Write-Success "Bot Manager セットアップ完了"
    Pop-Location
} else {
    Write-Err "bot-manager ディレクトリが見つかりません"
}

# ============================================================
# Phase 7: Windows サービス登録
# ============================================================
Write-Step "Phase 7/7: Windows サービス登録"

if ($SkipServices) {
    Write-Info "サービス登録をスキップします"
} else {
    # ログディレクトリ作成
    $logDir = "$InstallDir\logs"
    if (-not (Test-Path $logDir)) {
        New-Item -ItemType Directory -Path $logDir | Out-Null
    }

    # .envから環境変数を読み込み（ファイルから読み込むことでコンソール表示を最小化）
    $envContent = Get-Content $envFile -ErrorAction SilentlyContinue
    $apiKey = ($envContent | Where-Object { $_ -match "^GMO_API_KEY=" }) -replace "GMO_API_KEY=", ""
    $apiSecret = ($envContent | Where-Object { $_ -match "^GMO_API_SECRET=" }) -replace "GMO_API_SECRET=", ""

    # --- GMO Bot サービス ---
    Write-Info "GMO Bot サービスを登録中..."

    # 既存サービスを削除
    nssm stop gmo-bot 2>$null
    nssm remove gmo-bot confirm 2>$null

    # 新規登録（注: 環境変数はサービス設定に保存され、レジストリに格納される）
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

    Write-Success "GMO Bot サービス登録完了"

    # --- Bot Manager サービス ---
    Write-Info "Bot Manager サービスを登録中..."

    # 既存サービスを削除
    nssm stop bot-manager 2>$null
    nssm remove bot-manager confirm 2>$null

    # Waitressで起動するコマンド
    $waitressExe = "$managerDir\venv\Scripts\waitress-serve.exe"

    nssm install bot-manager "$waitressExe"
    nssm set bot-manager AppParameters "--host=127.0.0.1 --port=5000 app:app"
    nssm set bot-manager AppDirectory "$managerDir"
    # セキュアなパスワードを生成
    $adminPass = -join ((65..90) + (97..122) + (48..57) | Get-Random -Count 16 | ForEach-Object {[char]$_})
    $secretKey = [guid]::NewGuid().ToString()

    # 認証情報をファイルに保存（後で確認用）
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

    Write-Success "Bot Manager サービス登録完了"
}

# ============================================================
# 完了
# ============================================================
Write-Host @"

========================================
  セットアップ完了!
========================================

"@ -ForegroundColor Green

Write-Host "【サービス操作コマンド】" -ForegroundColor Yellow
Write-Host @"
  # GMO Bot
  nssm start gmo-bot        # 起動
  nssm stop gmo-bot         # 停止
  nssm restart gmo-bot      # 再起動
  nssm status gmo-bot       # 状態確認

  # Bot Manager
  nssm start bot-manager    # 起動
  nssm stop bot-manager     # 停止

"@

Write-Host "【Bot Manager アクセス】" -ForegroundColor Yellow
if (Test-Path "$InstallDir\bot-manager-credentials.txt") {
    $creds = Get-Content "$InstallDir\bot-manager-credentials.txt"
    Write-Host ($creds | Out-String)
    Write-Host "  ※ 認証情報は $InstallDir\bot-manager-credentials.txt に保存されています" -ForegroundColor Cyan
} else {
    Write-Host "  URL:      http://127.0.0.1:5000"
    Write-Host "  Username: admin"
    Write-Host "  ※ パスワードは bot-manager-credentials.txt を確認してください"
}
Write-Host ""

Write-Host "【ログ確認】" -ForegroundColor Yellow
Write-Host @"
  GMO Bot:     Get-Content $logDir\gmo-bot-stdout.log -Wait -Tail 50
  Bot Manager: Get-Content $logDir\bot-manager-stdout.log -Wait -Tail 50

"@

Write-Host "【次のステップ】" -ForegroundColor Cyan
Write-Host @"
  1. サービスを起動:
     nssm start gmo-bot
     nssm start bot-manager

  2. Bot Manager にアクセス:
     ブラウザで http://127.0.0.1:5000 を開く

  3. 取引設定を確認:
     $InstallDir\src\trade-config.yaml

"@

Write-Host "セットアップが完了しました。" -ForegroundColor Green
