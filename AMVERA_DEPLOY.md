$ErrorActionPreference = "Stop"

Write-Host "== PredskazBot: update and run =="

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "Git is not installed or not available in PATH."
    Write-Host "Install Git for Windows, then clone the repo instead of downloading ZIP archives."
    exit 1
}

if (-not (Test-Path ".git")) {
    Write-Host "This folder is not a git clone."
    Write-Host "Do this once in PowerShell:"
    Write-Host "  cd M:\"
    Write-Host "  git clone https://github.com/AdamFolz/BOTOVODYVROT.git"
    Write-Host "  cd BOTOVODYVROT"
    Write-Host "Then copy your existing .env into the cloned folder."
    exit 1
}

Write-Host "Pulling latest code..."
git pull --ff-only

if (-not (Test-Path ".env")) {
    Write-Host ".env not found. Creating it from .env.example..."
    Copy-Item ".env.example" ".env"
    Write-Host "Open .env and fill TELEGRAM_BOT_TOKEN and OPENAI_API_KEY, then run this script again."
    notepad .env
    exit 1
}

Write-Host "Installing/updating Python dependencies..."
python -m pip install -r requirements.txt

Write-Host "Starting bot..."
python bot.py
