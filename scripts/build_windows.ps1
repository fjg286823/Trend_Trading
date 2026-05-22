$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (!(Test-Path ".venv")) {
    py -3 -m venv .venv
}
& .\.venv\Scripts\Activate.ps1
pip install -r requirements-build.txt
pyinstaller --clean --noconfirm trend_trade.spec
Write-Host "Built: dist\trend-trade.exe"
