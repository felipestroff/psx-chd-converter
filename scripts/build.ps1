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
    throw "Could not resolve the script directory."
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
        throw "Command failed (exit code $LASTEXITCODE): $Exe $($Args -join ' ')"
    }
}

function Invoke-WithCleanTlsEnv {
    param(
        [Parameter(Mandatory = $true)][scriptblock]$Action
    )

    $varsToClear = @("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "PIP_CERT")
    $backup = @{}

    foreach ($varName in $varsToClear) {
        $currentValue = [System.Environment]::GetEnvironmentVariable($varName, "Process")
        if (-not [string]::IsNullOrWhiteSpace($currentValue)) {
            $backup[$varName] = $currentValue
            Remove-Item -Path ("Env:{0}" -f $varName) -ErrorAction SilentlyContinue
            Write-Host "==> Temporarily clearing $varName for pip execution"
        }
    }

    try {
        & $Action
    }
    finally {
        foreach ($item in $backup.GetEnumerator()) {
            [System.Environment]::SetEnvironmentVariable($item.Key, [string]$item.Value, "Process")
        }
    }
}

if ($FetchMame) {
    Write-Host "==> Updating chdman from the official MAME release"
    & "$PSScriptRoot\fetch-mame.ps1" -OutputDir "tools/mame" -Force:$ForceMameRefresh
    if ($LASTEXITCODE -ne 0) {
        throw "Automatic MAME update failed."
    }
}

if ($FetchMame -or $Fetch7Zip) {
    Write-Host "==> Updating 7-Zip extractor"
    & "$PSScriptRoot\fetch-7zip.ps1" -OutputDir "tools/7zip" -Force:$Force7ZipRefresh
    if ($LASTEXITCODE -ne 0) {
        throw "Automatic 7-Zip update failed."
    }
}

if (-not (Test-Path "tools\mame\chdman.exe")) {
    throw "chdman.exe was not found at tools\mame\chdman.exe. Use -FetchMame or copy it manually."
}

Write-Host "==> Cleaning old build artifacts"
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
if (Test-Path "$AppName.spec") { Remove-Item -Force "$AppName.spec" }

Write-Host "==> Installing build dependencies"
Invoke-WithCleanTlsEnv {
    Invoke-ExternalCommand -Exe $PythonExe -Args @("-m", "pip", "install", "-r", "requirements-build.txt")
}

Write-Host "==> Building portable executable (one-dir)"
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

Write-Host "==> Copying tools/mame folder to distribution output"
$targetTools = Join-Path "dist\$AppName" "tools"
New-Item -Path $targetTools -ItemType Directory -Force | Out-Null
Copy-Item -Path "tools\*" -Destination $targetTools -Recurse -Force

Write-Host "==> Build completed at dist\$AppName"
