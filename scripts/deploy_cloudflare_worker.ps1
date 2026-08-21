[CmdletBinding()]
param(
    [string]$WorkerUrl
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function ConvertFrom-SecureStringPlain {
    param([Parameter(Mandatory = $true)][Security.SecureString]$SecureValue)

    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureValue)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
}

function New-RelayHmacSecret {
    param([int]$ByteCount = 48)

    $bytes = New-Object byte[] $ByteCount
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($bytes)
    }
    finally {
        $rng.Dispose()
    }
    return [Convert]::ToBase64String($bytes).TrimEnd("=").Replace("+", "-").Replace("/", "_")
}

function Invoke-Wrangler {
    param(
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [switch]$Capture
    )

    if ($Capture) {
        $output = & npx --yes wrangler@latest @Arguments 2>&1 | Out-String
        if ($LASTEXITCODE -ne 0) {
            throw "Wrangler command failed: $($Arguments -join ' ')`n$output"
        }
        return $output
    }

    & npx --yes wrangler@latest @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Wrangler command failed: $($Arguments -join ' ')"
    }
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$workerDir = Join-Path $repoRoot "relay\cloudflare-worker"
if (-not (Test-Path (Join-Path $workerDir "wrangler.jsonc"))) {
    throw "Cloudflare Worker directory was not found: $workerDir"
}

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw "Node.js 20+ is required. Install Node.js and run this script again."
}
if (-not (Get-Command npx -ErrorAction SilentlyContinue)) {
    throw "npx was not found. Install Node.js 20+ and run this script again."
}

$nodeVersionText = (& node --version).Trim()
if ($nodeVersionText -notmatch '^v(?<major>\d+)\.') {
    throw "Could not determine the Node.js version: $nodeVersionText"
}
if ([int]$Matches.major -lt 20) {
    throw "Node.js 20+ is required. Current version: $nodeVersionText"
}

Write-Host "[1/7] Running Worker unit tests..."
Push-Location $workerDir
try {
    & npm test
    if ($LASTEXITCODE -ne 0) {
        throw "Worker unit tests failed. Deployment was cancelled."
    }
}
finally {
    Pop-Location
}

Write-Host "[2/7] Checking Cloudflare login..."
Push-Location $workerDir
try {
    & npx --yes wrangler@latest whoami *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Cloudflare login is required. A browser sign-in will open."
        Invoke-Wrangler -Arguments @("login")
    }

    Write-Host "[3/7] Deploying the Worker using the Free-compatible configuration..."
    $deployOutput = Invoke-Wrangler -Arguments @("deploy") -Capture
    Write-Host $deployOutput.Trim()

    if ([string]::IsNullOrWhiteSpace($WorkerUrl)) {
        $urlMatch = [regex]::Match($deployOutput, 'https://[A-Za-z0-9.-]+\.workers\.dev')
        if ($urlMatch.Success) {
            $WorkerUrl = $urlMatch.Value
        }
        else {
            $WorkerUrl = Read-Host "Deployment succeeded. Paste the workers.dev URL shown by Wrangler or the Cloudflare dashboard"
        }
    }
    if ($WorkerUrl -notmatch '^https://[A-Za-z0-9.-]+\.workers\.dev/?$') {
        throw "Worker URL must be an https://...workers.dev address."
    }
    $workerUrl = $WorkerUrl.TrimEnd("/")

    Write-Host "[4/7] Reading the existing BuildingHUB API key securely..."
    $secureApiKey = Read-Host "Paste the current BUILDING_HUB_API_KEY (input is hidden)" -AsSecureString
    $apiKey = ConvertFrom-SecureStringPlain -SecureValue $secureApiKey
    if ([string]::IsNullOrWhiteSpace($apiKey)) {
        throw "BUILDING_HUB_API_KEY cannot be empty."
    }

    $relayHmacSecret = New-RelayHmacSecret

    Write-Host "[5/7] Saving Worker secrets..."
    $apiKey | & npx --yes wrangler@latest secret put DATA_GO_SERVICE_KEY | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to save DATA_GO_SERVICE_KEY."
    }
    $relayHmacSecret | & npx --yes wrangler@latest secret put RELAY_HMAC_SECRET | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to save RELAY_HMAC_SECRET."
    }
    $apiKey = $null
    $secureApiKey = $null

    Write-Host "[6/7] Checking Worker health..."
    $health = Invoke-RestMethod -Uri "$workerUrl/healthz" -Method Get -TimeoutSec 20
    if ($health.status -ne "ok") {
        throw "Worker health check returned an unexpected response."
    }

    $streamlitSecrets = @"
BUILDING_HUB_RELAY_URL = "$workerUrl"
BUILDING_HUB_RELAY_HMAC_SECRET = "$relayHmacSecret"
"@

    Write-Host "[7/7] Preparing Streamlit Cloud secrets..."
    try {
        Set-Clipboard -Value $streamlitSecrets
    }
    catch {
        throw "Worker deployment succeeded, but Windows clipboard access failed. Rerun this script from Windows Terminal/PowerShell so the HMAC secret can be copied safely."
    }

    Write-Host ""
    Write-Host "Cloudflare Worker deployment is complete."
    Write-Host "Worker URL: $workerUrl"
    Write-Host "The two Streamlit relay secret lines are now in your clipboard."
    Write-Host "Open Streamlit Community Cloud > App settings > Secrets, keep the existing BUILDING_HUB_API_KEY, paste the two copied lines, and save."
    Write-Host "Do not paste DATA_GO_SERVICE_KEY into Streamlit; it is stored only in the Worker."
}
finally {
    Pop-Location
}
