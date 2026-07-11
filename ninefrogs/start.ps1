# Start Nine Frogs web server + Celery worker
# Usage: .\start.ps1

Set-Location $PSScriptRoot

# Celery worker in a separate window
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd 'D:\Nine Frogs\ninefrogs'; uv run celery -A lab.tasks.celery_app worker --loglevel=info --pool=solo"

# Web server in this window
uv run python main.py
