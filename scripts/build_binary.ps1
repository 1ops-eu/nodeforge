# build_binary.ps1 — Windows binary build script for nodeforge
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\build_binary.ps1
#
# Prerequisites:
#   - Python 3.11+ installed and on PATH
#   - sqlcipher3 manually set up for Windows (see README.md)
#
# Output:
#   dist\nodeforge.exe

$ErrorActionPreference = "Stop"

Write-Host ">>> Installing build dependencies"
python -m pip install --upgrade pip
python -m pip install build pyinstaller

Write-Host ">>> Cleaning prior artifacts"
if (Test-Path build)  { Remove-Item -Recurse -Force build }
if (Test-Path dist)   { Remove-Item -Recurse -Force dist }
Get-ChildItem -Filter *.spec | Remove-Item -Force -ErrorAction SilentlyContinue

Write-Host ">>> Building standalone executable"
pyinstaller `
    --onefile `
    --name nodeforge `
    --clean `
    --paths . `
    --hidden-import sqlcipher3 `
    --hidden-import paramiko `
    --hidden-import invoke `
    --hidden-import fabric `
    scripts\entrypoint.py

Write-Host ""
Write-Host ">>> Built: dist\nodeforge.exe"
Write-Host ">>> Verify with: .\dist\nodeforge.exe --help"
