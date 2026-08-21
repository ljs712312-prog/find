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

function Get-UsableNodeVersion {
    $nodeCommand = Get-Command node -ErrorAction SilentlyContinue
    $npxCommand = Get-Command npx -ErrorAction SilentlyContinue
    if (-not $nodeCommand -or -not $npxCommand) {
        return $null
    }

    try {
        $versionText = (& node --version 2>$null).Trim()
    }
    catch {
        return $null
    }

    if ($versionText -notmatch '^v(?<major>\d+)\.') {
        return $null
    }
    if ([int]$Matches.major -lt 20) {
        return $null
    }
    return $versionText
}

function Enable-Tls12ForWindowsPowerShell {
    try {
        [Net.ServicePointManager]::SecurityProtocol =
            [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    }
    catch {
        # PowerShell 7+ uses the modern .NET HTTP stack and does not need this.
    }
}

function Install-PortableNodeLts {
    Enable-Tls12ForWindowsPowerShell

    $architecture = $env:PROCESSOR_ARCHITEW6432
    if ([string]::IsNullOrWhiteSpace($architecture)) {
        $architecture = $env:PROCESSOR_ARCHITECTURE
    }
    $nodeArch = if ($architecture -match 'ARM64') { 'arm64' } else { 'x64' }
    $fileMarker = "win-$nodeArch-zip"

    Write-Host "Node.js 20+ was not found. Preparing an official portable Node.js LTS runtime..."

    try {
        $releases = Invoke-RestMethod -Uri "https://nodejs.org/dist/index.json" -Method Get -TimeoutSec 30
    }
    catch {
        throw "Could not read the official Node.js release index from nodejs.org. Check the internet connection and run the same command again."
    }

    $release = $releases |
        Where-Object { $_.lts -and ($_.files -contains $fileMarker) } |
        Select-Object -First 1
    if (-not $release) {
        throw "Could not find a current Node.js LTS Windows $nodeArch portable build."
    }

    $version = [string]$release.version
    if ($version -notmatch '^v(?<major>\d+)\.' -or [int]$Matches.major -lt 20) {
        throw "The Node.js release index returned an unexpected LTS version: $version"
    }

    $fileName = "node-$version-win-$nodeArch.zip"
    $distBase = "https://nodejs.org/dist/$version"
    $runtimeRoot = Join-Path $env:TEMP "won-top-node-runtime"
    $downloadRoot = Join-Path $env:TEMP "won-top-node-download"
    $zipPath = Join-Path $downloadRoot $fileName
    $extractDir = Join-Path $runtimeRoot "node-$version-win-$nodeArch"

    if (-not (Test-Path (Join-Path $extractDir "node.exe"))) {
        Remove-Item -LiteralPath $downloadRoot -Recurse -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $runtimeRoot -Recurse -Force -ErrorAction SilentlyContinue
        New-Item -ItemType Directory -Path $downloadRoot -Force | Out-Null
        New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null

        Write-Host "Downloading Node.js $version portable runtime from nodejs.org..."
        try {
            Invoke-WebRequest -Uri "$distBase/$fileName" -OutFile $zipPath -UseBasicParsing -TimeoutSec 120
            $checksumText = (Invoke-WebRequest -Uri "$distBase/SHASUMS256.txt" -UseBasicParsing -TimeoutSec 30).Content
        }
        catch {
            throw "Failed to download the official Node.js runtime or checksum file from nodejs.org."
        }

        $escapedFileName = [regex]::Escape($fileName)
        $checksumMatch = [regex]::Match(
            [string]$checksumText,
            "(?mi)^([0-9a-f]{64})\s+$escapedFileName\s*$"
        )
        if (-not $checksumMatch.Success) {
            throw "Could not find the SHA-256 checksum for $fileName in Node.js SHASUMS256.txt."
        }

        $expectedHash = $checksumMatch.Groups[1].Value.ToUpperInvariant()
        $actualHash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToUpperInvariant()
        if ($actualHash -ne $expectedHash) {
            Remove-Item -LiteralPath $zipPath -Force -ErrorAction SilentlyContinue
            throw "Node.js portable runtime checksum verification failed. The downloaded file was discarded."
        }

        Write-Host "Node.js SHA-256 verified. Extracting the portable runtime..."
        Expand-Archive -LiteralPath $zipPath -DestinationPath $runtimeRoot -Force
        Remove-Item -LiteralPath $zipPath -Force -ErrorAction SilentlyContinue
    }

    if (-not (Test-Path (Join-Path $extractDir "node.exe"))) {
        throw "Portable Node.js extraction completed, but node.exe was not found."
    }

    $env:Path = "$extractDir;$env:Path"
    $versionText = Get-UsableNodeVersion
    if (-not $versionText) {
        throw "Portable Node.js was prepared but could not be activated in this PowerShell session."
    }

    Write-Host "Portable Node.js $versionText is ready. Nothing was installed system-wide."
    return $versionText
}

function Ensure-NodeRuntime {
    $versionText = Get-UsableNodeVersion
    if ($versionText) {
        Write-Host "Using existing Node.js $versionText."
        return $versionText
    }
    return Install-PortableNodeLts
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

Ensure-NodeRuntime | Out-Null

Write-Host "[1/6] Running Worker unit tests..."
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

Write-Host "[2/6] Checking Cloudflare login..."
Push-Location $workerDir
try {
    & npx --yes wrangler@latest whoami *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Cloudflare login is required. A browser sign-in will open."
        Invoke-Wrangler -Arguments @("login")
    }

    Write-Host "[3/6] Deploying the Worker using the Free-compatible configuration..."
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

    Write-Host "[4/6] Reading the existing BuildingHUB API key securely..."
    $secureApiKey = Read-Host "Paste the current BUILDING_HUB_API_KEY (input is hidden)" -AsSecureString
    $apiKey = ConvertFrom-SecureStringPlain -SecureValue $secureApiKey
    if ([string]::IsNullOrWhiteSpace($apiKey)) {
        throw "BUILDING_HUB_API_KEY cannot be empty."
    }

    Write-Host "[5/6] Saving the BuildingHUB key in the Worker secret store..."
    $apiKey | & npx --yes wrangler@latest secret put DATA_GO_SERVICE_KEY | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to save DATA_GO_SERVICE_KEY."
    }
    $apiKey = $null
    $secureApiKey = $null

    Write-Host "[6/6] Checking Worker health..."
    $health = Invoke-RestMethod -Uri "$workerUrl/healthz" -Method Get -TimeoutSec 20
    if ($health.status -ne "ok") {
        throw "Worker health check returned an unexpected response."
    }

    try {
        Set-Clipboard -Value $workerUrl
    }
    catch {
        Write-Warning "Clipboard copy failed. Copy the Worker URL printed below manually."
    }

    Write-Host ""
    Write-Host "Cloudflare Worker deployment is complete."
    Write-Host "Worker URL: $workerUrl"
    Write-Host "The Worker URL was copied to the clipboard when possible."
    Write-Host "Send only this public Worker URL back to ChatGPT. Do NOT send the BuildingHUB API key."
    Write-Host "No additional relay HMAC secret is required in Streamlit."
}
finally {
    Pop-Location
}
