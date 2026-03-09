[CmdletBinding()]
param(
    [string]$ReleaseApiUrl = "https://api.github.com/repos/has207/psxtract-2/releases/latest",
    [string]$OutputDir = "tools/psxtract",
    [string]$BinaryUrl = "",
    [switch]$Force
)

$ErrorActionPreference = "Stop"

if (-not $PSScriptRoot) {
    throw "Could not resolve the script directory."
}

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

$outputPath = [System.IO.Path]::GetFullPath($OutputDir)
$targetExe = Join-Path $outputPath "psxtract.exe"
if ((Test-Path $targetExe) -and -not $Force) {
    Write-Host "psxtract.exe already exists at $targetExe. Use -Force to refresh."
    exit 0
}

$selectedSourceName = ""
if ([string]::IsNullOrWhiteSpace($BinaryUrl)) {
    Write-Host "==> Checking psxtract release API: $ReleaseApiUrl"
    $release = Invoke-RestMethod -Uri $ReleaseApiUrl

    $asset = $release.assets |
        Where-Object { $_.name -match '(?i)psxtract.*\.(zip|exe)$' } |
        Select-Object -First 1
    if (-not $asset) {
        throw "Could not automatically find a psxtract asset (.zip or .exe)."
    }

    $BinaryUrl = [string]$asset.browser_download_url
    $selectedSourceName = [string]$asset.name
}
else {
    $selectedSourceName = Split-Path $BinaryUrl -Leaf
}

Write-Host "==> Selected source: $BinaryUrl"

$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("cue-chd-psxtract-fetch-" + [guid]::NewGuid().ToString("N"))
$downloadName = if ([string]::IsNullOrWhiteSpace($selectedSourceName)) { Split-Path $BinaryUrl -Leaf } else { $selectedSourceName }
$downloadPath = Join-Path $tempRoot $downloadName
$extractPath = Join-Path $tempRoot "extract"

New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
New-Item -ItemType Directory -Path $extractPath -Force | Out-Null
New-Item -ItemType Directory -Path $outputPath -Force | Out-Null

try {
    Write-Host "==> Downloading psxtract package..."
    Invoke-WebRequest -Uri $BinaryUrl -OutFile $downloadPath

    $downloadExt = [System.IO.Path]::GetExtension($downloadPath).ToLowerInvariant()
    if ($downloadExt -eq ".zip") {
        Write-Host "==> Extracting package contents..."
        Expand-Archive -Path $downloadPath -DestinationPath $extractPath -Force
        $psxtract = Get-ChildItem -Path $extractPath -Recurse -Filter "psxtract.exe" | Select-Object -First 1
        if (-not $psxtract) {
            throw "psxtract.exe was not found inside the downloaded archive."
        }
        Copy-Item -Path $psxtract.FullName -Destination $targetExe -Force
    }
    elseif ($downloadExt -eq ".exe") {
        Copy-Item -Path $downloadPath -Destination $targetExe -Force
    }
    else {
        throw "Unsupported psxtract package format: $downloadExt"
    }

    $metadataPath = Join-Path $outputPath "psxtract-fetch-metadata.json"
    $metadata = [ordered]@{
        release_api_url = $ReleaseApiUrl
        binary_url = $BinaryUrl
        source_file = $downloadName
        fetched_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    } | ConvertTo-Json -Depth 3
    Set-Content -Path $metadataPath -Value $metadata -Encoding UTF8

    Write-Host "==> psxtract updated at $targetExe"
}
finally {
    if (Test-Path $tempRoot) {
        try {
            Remove-Item -Path $tempRoot -Recurse -Force -ErrorAction Stop
        }
        catch {
            Write-Warning "Could not clean temporary folder: $tempRoot"
        }
    }
}
