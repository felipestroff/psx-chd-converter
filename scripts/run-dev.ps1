param(
    [string]$PythonExe = "python"
)

$ErrorActionPreference = "Stop"
if (-not $PSScriptRoot) {
    throw "Não foi possível resolver o diretório do script."
}
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot
& $PythonExe src/main.py
