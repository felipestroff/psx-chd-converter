[CmdletBinding()]
param(
    [string]$ReleasePageUrl = "https://www.mamedev.org/release.html",
    [string]$OutputDir = "tools/mame",
    [string]$Architecture = "x64",
    [string]$PackageUrl = "",
    [switch]$Force
)

$ErrorActionPreference = "Stop"

if (-not $PSScriptRoot) {
    throw "Não foi possível resolver o diretório do script."
}

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

$outputPath = [System.IO.Path]::GetFullPath($OutputDir)
$targetChdman = Join-Path $outputPath "chdman.exe"
if ((Test-Path $targetChdman) -and -not $Force) {
    Write-Host "chdman.exe já existe em $targetChdman. Use -Force para atualizar."
    exit 0
}

if ([string]::IsNullOrWhiteSpace($PackageUrl)) {
    Write-Host "==> Consultando release oficial: $ReleasePageUrl"
    $releaseHtml = (Invoke-WebRequest -Uri $ReleasePageUrl -UseBasicParsing).Content
    $escapedArch = [regex]::Escape($Architecture)
    $pattern = 'https://github\.com/mamedev/mame/releases/download/[^"]+/mame\d+b_{0}\.exe' -f $escapedArch
    $match = [regex]::Match($releaseHtml, $pattern, [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
    if (-not $match.Success) {
        throw "Não foi possível localizar automaticamente o pacote do MAME para '$Architecture'."
    }
    $PackageUrl = $match.Value
}

Write-Host "==> Pacote selecionado: $PackageUrl"

$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("cue-chd-mame-fetch-" + [guid]::NewGuid().ToString("N"))
$packageName = Split-Path $PackageUrl -Leaf
$packagePath = Join-Path $tempRoot $packageName
$extractPath = Join-Path $tempRoot "extract"

New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
New-Item -ItemType Directory -Path $extractPath -Force | Out-Null
New-Item -ItemType Directory -Path $outputPath -Force | Out-Null

try {
    Write-Host "==> Baixando pacote..."
    Invoke-WebRequest -Uri $PackageUrl -OutFile $packagePath

    Write-Host "==> Extraindo conteúdo..."
    $args = @("-y", "-o$extractPath")
    $proc = Start-Process -FilePath $packagePath -ArgumentList $args -Wait -PassThru -NoNewWindow
    if ($proc.ExitCode -ne 0) {
        throw "Falha ao extrair o pacote MAME (exit code: $($proc.ExitCode))."
    }

    $chdman = Get-ChildItem -Path $extractPath -Recurse -Filter "chdman.exe" | Select-Object -First 1
    if (-not $chdman) {
        throw "chdman.exe não encontrado dentro do pacote baixado."
    }

    Copy-Item -Path $chdman.FullName -Destination $targetChdman -Force

    $dlls = Get-ChildItem -Path $chdman.Directory.FullName -Filter "*.dll"
    foreach ($dll in $dlls) {
        Copy-Item -Path $dll.FullName -Destination (Join-Path $outputPath $dll.Name) -Force
    }

    $metadataPath = Join-Path $outputPath "mame-fetch-metadata.json"
    $metadata = [ordered]@{
        release_page_url = $ReleasePageUrl
        package_url = $PackageUrl
        package_file = $packageName
        fetched_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    } | ConvertTo-Json -Depth 3
    Set-Content -Path $metadataPath -Value $metadata -Encoding UTF8

    Write-Host "==> chdman atualizado em $targetChdman"
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
