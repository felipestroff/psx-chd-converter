[CmdletBinding()]
param(
    [string]$PythonExe = "python",
    [string]$AppName = "CueChdConverter",
    [switch]$FetchMame,
    [switch]$ForceMameRefresh,
    [switch]$Fetch7Zip,
    [switch]$Force7ZipRefresh
)

$ErrorActionPreference = "Stop"

if (-not $PSScriptRoot) {
    throw "Não foi possível resolver o diretório do script."
}

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

function Invoke-ExternalCommand {
    param(
        [Parameter(Mandatory = $true)][string]$Exe,
        [Parameter(Mandatory = $false)][string[]]$Args = @()
    )

    & $Exe @Args
    if ($LASTEXITCODE -ne 0) {
        throw "Comando falhou (exit code $LASTEXITCODE): $Exe $($Args -join ' ')"
    }
}

if ($FetchMame) {
    Write-Host "==> Atualizando chdman via release oficial do MAME"
    & "$PSScriptRoot\fetch-mame.ps1" -OutputDir "tools/mame" -Force:$ForceMameRefresh
    if ($LASTEXITCODE -ne 0) {
        throw "Falha na atualização automática do MAME."
    }
}

if ($FetchMame -or $Fetch7Zip) {
    Write-Host "==> Atualizando extrator 7-Zip"
    & "$PSScriptRoot\fetch-7zip.ps1" -OutputDir "tools/7zip" -Force:$Force7ZipRefresh
    if ($LASTEXITCODE -ne 0) {
        throw "Falha na atualização automática do 7-Zip."
    }
}

if (-not (Test-Path "tools\mame\chdman.exe")) {
    throw "chdman.exe não encontrado em tools\mame\chdman.exe. Use -FetchMame ou copie manualmente."
}

Write-Host "==> Limpando artefatos antigos"
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
if (Test-Path "$AppName.spec") { Remove-Item -Force "$AppName.spec" }

Write-Host "==> Instalando dependências de build"
Invoke-ExternalCommand -Exe $PythonExe -Args @("-m", "pip", "install", "-r", "requirements-build.txt")

Write-Host "==> Gerando executável portátil (one-dir)"
Invoke-ExternalCommand -Exe $PythonExe -Args @(
    "-m",
    "PyInstaller",
    "--noconfirm",
    "--clean",
    "--windowed",
    "--name",
    $AppName,
    "--paths",
    "src",
    "src/main.py"
)

Write-Host "==> Copiando pasta tools/mame para distribuição"
$targetTools = Join-Path "dist\$AppName" "tools"
New-Item -Path $targetTools -ItemType Directory -Force | Out-Null
Copy-Item -Path "tools\*" -Destination $targetTools -Recurse -Force

Write-Host "==> Build concluído em dist\$AppName"
