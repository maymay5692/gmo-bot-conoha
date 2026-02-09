# GMO Coin API Diagnostic Script
# Diagnose ERR-5012 "Invalid API-action" by testing each endpoint individually
#
# Usage: .\deploy\diagnose-api.ps1
# Requires: GMO_API_KEY and GMO_API_SECRET environment variables (reads from nssm)

param(
    [string]$ApiKey = "",
    [string]$ApiSecret = ""
)

$ErrorActionPreference = "Continue"

# --- Utility Functions ---

function Get-UnixTimestampMs {
    [long]([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds())
}

function Get-HmacSha256 {
    param([string]$Message, [string]$Secret)
    $hmac = New-Object System.Security.Cryptography.HMACSHA256
    $hmac.Key = [System.Text.Encoding]::UTF8.GetBytes($Secret)
    $hash = $hmac.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($Message))
    return ($hash | ForEach-Object { $_.ToString("x2") }) -join ""
}

function Invoke-GmoApi {
    param(
        [string]$Method,
        [string]$Path,
        [string]$Body = "",
        [string]$Key,
        [string]$Secret
    )

    # Split path from query string for HMAC signing
    # GMO API: HMAC is computed with path only (no query params), body empty for GET
    $signPath = $Path
    if ($Path.Contains("?")) {
        $signPath = $Path.Substring(0, $Path.IndexOf("?"))
    }

    $timestamp = Get-UnixTimestampMs
    $signData = "$timestamp$($Method.ToUpper())$signPath$Body"
    $sign = Get-HmacSha256 -Message $signData -Secret $Secret

    $baseUrl = "https://api.coin.z.com/private"
    $url = "$baseUrl$Path"

    $headers = @{
        "API-KEY"       = $Key
        "API-TIMESTAMP" = $timestamp.ToString()
        "API-SIGN"      = $sign
        "Content-Type"  = "application/json"
    }

    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        if ($Method -eq "GET") {
            $response = Invoke-RestMethod -Uri $url -Method Get -Headers $headers -TimeoutSec 10
        } else {
            $response = Invoke-RestMethod -Uri $url -Method Post -Headers $headers -Body $Body -TimeoutSec 10
        }
        return $response
    } catch {
        $statusCode = $_.Exception.Response.StatusCode
        try {
            $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
            $errorBody = $reader.ReadToEnd()
            $reader.Close()
            return $errorBody | ConvertFrom-Json
        } catch {
            return @{ status = -1; error = $_.Exception.Message }
        }
    }
}

# --- Main ---

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  GMO Coin API Diagnostic Tool" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Get API keys
if (-not $ApiKey -or -not $ApiSecret) {
    Write-Host "[1/6] Reading API keys from nssm..." -ForegroundColor Yellow
    $envExtra = nssm get gmo-bot AppEnvironmentExtra 2>$null
    if ($envExtra) {
        foreach ($line in ($envExtra -split "`n")) {
            if ($line -match "^GMO_API_KEY=(.+)$") { $ApiKey = $Matches[1].Trim() }
            if ($line -match "^GMO_API_SECRET=(.+)$") { $ApiSecret = $Matches[1].Trim() }
        }
    }
}

if (-not $ApiKey -or -not $ApiSecret) {
    Write-Host "ERROR: Could not find API keys. Set GMO_API_KEY and GMO_API_SECRET." -ForegroundColor Red
    exit 1
}

# Show masked keys
$keyMask = $ApiKey.Substring(0, [Math]::Min(8, $ApiKey.Length)) + "****"
$secretMask = $ApiSecret.Substring(0, [Math]::Min(8, $ApiSecret.Length)) + "****"
Write-Host "  API Key:    $keyMask (length=$($ApiKey.Length))" -ForegroundColor Gray
Write-Host "  API Secret: $secretMask (length=$($ApiSecret.Length))" -ForegroundColor Gray

# Check for suspicious characters
$suspiciousChars = @('<', '>', '"', "'", ' ', "`t")
$keyIssues = @()
$secretIssues = @()
foreach ($ch in $suspiciousChars) {
    if ($ApiKey.Contains($ch)) { $keyIssues += "'$ch'" }
    if ($ApiSecret.Contains($ch)) { $secretIssues += "'$ch'" }
}
if ($keyIssues.Count -gt 0) {
    Write-Host "  WARNING: API Key contains suspicious chars: $($keyIssues -join ', ')" -ForegroundColor Red
}
if ($secretIssues.Count -gt 0) {
    Write-Host "  WARNING: API Secret contains suspicious chars: $($secretIssues -join ', ')" -ForegroundColor Red
}

Write-Host ""

# Check system time
Write-Host "[2/6] Checking system time..." -ForegroundColor Yellow
$localTime = Get-Date
$utcTime = [DateTimeOffset]::UtcNow
Write-Host "  Local: $localTime"
Write-Host "  UTC:   $utcTime"
Write-Host ""

# Test endpoints
$tests = @(
    @{ Name = "Account Assets (Spot)";       Method = "GET";  Path = "/v1/account/assets" },
    @{ Name = "Account Margin (Leverage)";   Method = "GET";  Path = "/v1/account/margin" },
    @{ Name = "Open Positions (Leverage)";   Method = "GET";  Path = "/v1/openPositions?symbol=BTC_JPY" },
    @{ Name = "Active Orders (Leverage)";    Method = "GET";  Path = "/v1/activeOrders?symbol=BTC_JPY&page=1&count=1" }
)

Write-Host "[3/6] Testing API endpoints..." -ForegroundColor Yellow
Write-Host ""

$results = @()
foreach ($test in $tests) {
    Write-Host "  Testing: $($test.Name)" -ForegroundColor White
    Write-Host "    $($test.Method) $($test.Path)" -ForegroundColor Gray

    $result = Invoke-GmoApi -Method $test.Method -Path $test.Path -Key $ApiKey -Secret $ApiSecret

    if ($result.status -eq 0) {
        Write-Host "    -> OK (status=0)" -ForegroundColor Green
        $results += @{ Name = $test.Name; Status = "OK" }
    } else {
        $errCode = ""
        $errMsg = ""
        if ($result.messages) {
            $errCode = $result.messages[0].message_code
            $errMsg = $result.messages[0].message_string
        } elseif ($result.error) {
            $errMsg = $result.error
        }
        Write-Host "    -> FAILED: $errCode - $errMsg" -ForegroundColor Red
        $results += @{ Name = $test.Name; Status = "FAIL"; Code = $errCode; Message = $errMsg }
    }
    Write-Host ""
    Start-Sleep -Milliseconds 500
}

# Summary
Write-Host "[4/6] Results Summary" -ForegroundColor Yellow
Write-Host "  ----------------------------------------"
foreach ($r in $results) {
    $color = if ($r.Status -eq "OK") { "Green" } else { "Red" }
    $detail = if ($r.Status -eq "OK") { "OK" } else { "$($r.Code) - $($r.Message)" }
    Write-Host "  $($r.Name): $detail" -ForegroundColor $color
}
Write-Host ""

# Diagnosis
Write-Host "[5/6] Diagnosis" -ForegroundColor Yellow

$allFailed = ($results | Where-Object { $_.Status -ne "OK" }).Count -eq $results.Count
$spotFailed = ($results | Where-Object { $_.Name -match "Spot|Assets" -and $_.Status -ne "OK" }).Count -gt 0
$marginFailed = ($results | Where-Object { $_.Name -match "Margin|Position|Leverage" -and $_.Status -ne "OK" }).Count -gt 0
$spotOk = ($results | Where-Object { $_.Name -match "Spot|Assets" -and $_.Status -eq "OK" }).Count -gt 0

if ($allFailed) {
    $codes = ($results | Where-Object { $_.Code } | Select-Object -ExpandProperty Code -Unique) -join ", "
    Write-Host "  ALL endpoints failed ($codes)." -ForegroundColor Red
    Write-Host "  -> Check: API key validity, account status, or IP restrictions." -ForegroundColor Yellow
    if ($codes -match "5012") {
        Write-Host "  -> ERR-5012 on ALL calls = API key has NO action permissions." -ForegroundColor Red
        Write-Host "  -> Go to GMO Coin dashboard -> API -> verify ALL toggles are ON." -ForegroundColor Yellow
    }
} elseif ($spotOk -and $marginFailed) {
    Write-Host "  Spot endpoints work but Margin/Leverage endpoints fail." -ForegroundColor Red
    Write-Host "  -> Your API key lacks 'Leverage Trading' permission." -ForegroundColor Yellow
    Write-Host "  -> Go to GMO Coin dashboard -> API key settings." -ForegroundColor Yellow
    Write-Host "  -> Enable permission for: Exchange Leverage (取引所レバレッジ)" -ForegroundColor Yellow
    Write-Host "  -> Also verify: Leverage trading account is opened on your GMO account." -ForegroundColor Yellow
}
elseif (-not $spotFailed -and -not $marginFailed) {
    Write-Host "  All endpoints working!" -ForegroundColor Green
}
Write-Host ""

Write-Host "[6/6] Raw environment variable check" -ForegroundColor Yellow
Write-Host "  Checking registry directly..." -ForegroundColor Gray
try {
    $regEnv = (Get-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Services\gmo-bot" -Name Environment -ErrorAction Stop).Environment
    Write-Host "  Registry entries:" -ForegroundColor Gray
    foreach ($entry in $regEnv) {
        if ($entry -match "^([^=]+)=(.+)$") {
            $n = $Matches[1]
            $v = $Matches[2]
            if ($n -match "KEY|SECRET") {
                $masked = $v.Substring(0, [Math]::Min(4, $v.Length)) + "..." + $v.Substring([Math]::Max(0, $v.Length - 4))
                Write-Host "    $n=$masked (len=$($v.Length))" -ForegroundColor Gray
            } else {
                Write-Host "    $n=$v" -ForegroundColor Gray
            }
        }
    }
} catch {
    Write-Host "  Could not read registry. Run as Administrator." -ForegroundColor Red
}

Write-Host ""
Write-Host "Done." -ForegroundColor Cyan
