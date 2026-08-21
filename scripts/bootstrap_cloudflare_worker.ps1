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

    & powershell -NoProfile -ExecutionPolicy Bypass -File $deployScript
    if ($LASTEXITCODE -ne 0) {
        throw "Cloudflare deployment script exited with code $LASTEXITCODE."
    }
}
finally {
    Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}
