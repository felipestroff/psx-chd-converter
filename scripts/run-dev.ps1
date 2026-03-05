param(
    [string]$PythonExe = "python"
)

$ErrorActionPreference = "Stop"
if (-not $PSScriptRoot) {
    throw "Could not resolve the script directory."
}
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot
& $PythonExe src/main.py

