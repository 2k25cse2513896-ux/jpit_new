$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'

if (-not (Test-Path (Join-Path $backend '.venv'))) {
  py -3 -m venv (Join-Path $backend '.venv')
}
& (Join-Path $backend '.venv\Scripts\python.exe') -m pip install -r (Join-Path $backend 'requirements.txt')
if (-not (Test-Path (Join-Path $frontend 'node_modules'))) { npm install --prefix $frontend }

Start-Process powershell -ArgumentList "-NoExit","-Command","cd '$backend'; & '.\.venv\Scripts\python.exe' -m uvicorn app.main:app --reload --port 8000"
Start-Process powershell -ArgumentList "-NoExit","-Command","cd '$frontend'; npm run dev -- --host 127.0.0.1"
Start-Sleep -Seconds 3
Start-Process 'http://127.0.0.1:5173'
