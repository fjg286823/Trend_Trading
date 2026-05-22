$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (!(Test-Path ".venv")) {
    py -3 -m venv .venv
}
& .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
