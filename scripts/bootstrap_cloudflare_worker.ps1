[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoZipUrl = "https://github.com/ljs712312-prog/find/archive/refs/heads/main.zip"
$tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("won-top-buildinghub-" + [Guid]::NewGuid().ToString("N"))
$zipPath = Join-Path $tempRoot "repo.zip"
$extractPath = Join-Path $tempRoot "repo"

New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null

try {
    Write-Host "Downloading the latest ONE TOP BuildingHUB deployment tools from GitHub..."
    Invoke-WebRequest -Uri $repoZipUrl -OutFile $zipPath -UseBasicParsing

    Write-Host "Preparing a temporary deployment workspace..."
    Expand-Archive -Path $zipPath -DestinationPath $extractPath -Force

    $repoDir = Get-ChildItem -Path $extractPath -Directory | Select-Object -First 1
    if ($null -eq $repoDir) {
        throw "The downloaded GitHub archive did not contain a repository directory."
    }

    $deployScript = Join-Path $repoDir.FullName "scripts\deploy_cloudflare_worker.ps1"
    if (-not (Test-Path $deployScript)) {
        throw "The deployment script was not found in the downloaded repository."
    }

    # Run in this PowerShell process. This avoids environments that deny
    # spawning a second powershell.exe and also keeps the temporary portable
    # Node.js PATH scoped to this deployment session.
    & $deployScript
}
finally {
    Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}
