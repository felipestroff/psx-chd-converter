[CmdletBinding()]
param(
    [string]$DownloadPageUrl = "https://www.7-zip.org/download.html",
    [string]$OutputDir = "tools/7zip",
    [string]$BinaryUrl = "",
    [switch]$Force
)

$ErrorActionPreference = "Stop"

if (-not $PSScriptRoot) {
    throw "Não foi possível resolver o diretório do script."
}

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

$outputPath = [System.IO.Path]::GetFullPath($OutputDir)
$target7z = Join-Path $outputPath "7z.exe"
$target7zr = Join-Path $outputPath "7zr.exe"

if ((Test-Path $target7z) -and -not $Force) {
    Write-Host "7z.exe já existe em $target7z. Use -Force para atualizar."
    exit 0
}

if (-not (Test-Path $target7z) -and (Test-Path $target7zr) -and -not $Force) {
    Write-Host "7zr.exe já existe em $target7zr. Use -Force para atualizar."
    exit 0
}

if ([string]::IsNullOrWhiteSpace($BinaryUrl)) {
    Write-Host "==> Consultando download oficial do 7-Zip: $DownloadPageUrl"
    $downloadHtml = (Invoke-WebRequest -Uri $DownloadPageUrl -UseBasicParsing).Content

    $pattern = 'href="(?<href>[^"]*7zr[^"]*\.exe)"'
    $match = [regex]::Match($downloadHtml, $pattern, [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
    if (-not $match.Success) {
        throw "Não foi possível localizar automaticamente o link de 7zr.exe na página oficial."
    }

    $href = $match.Groups["href"].Value
    if ($href.StartsWith("http://") -or $href.StartsWith("https://")) {
        $BinaryUrl = $href
    }
    else {
        $base = [Uri]$DownloadPageUrl
        $BinaryUrl = [Uri]::new($base, $href).AbsoluteUri
    }
}

Write-Host "==> Binário selecionado: $BinaryUrl"

$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("cue-chd-7zip-fetch-" + [guid]::NewGuid().ToString("N"))
$binaryName = Split-Path $BinaryUrl -Leaf
$downloadPath = Join-Path $tempRoot $binaryName

New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
New-Item -ItemType Directory -Path $outputPath -Force | Out-Null

try {
    Write-Host "==> Baixando 7zr.exe..."
    Invoke-WebRequest -Uri $BinaryUrl -OutFile $downloadPath

    Copy-Item -Path $downloadPath -Destination $target7zr -Force
    Copy-Item -Path $downloadPath -Destination $target7z -Force

    $metadataPath = Join-Path $outputPath "7zip-fetch-metadata.json"
    $metadata = [ordered]@{
        download_page_url = $DownloadPageUrl
        binary_url = $BinaryUrl
        binary_file = $binaryName
        fetched_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    } | ConvertTo-Json -Depth 3
    Set-Content -Path $metadataPath -Value $metadata -Encoding UTF8

    Write-Host "==> 7z.exe atualizado em $target7z"
}
finally {
    if (Test-Path $tempRoot) {
        try {
            Remove-Item -Path $tempRoot -Recurse -Force -ErrorAction Stop
        }
        catch {
            Write-Warning "Não foi possível limpar a pasta temporária: $tempRoot"
        }
    }
}
