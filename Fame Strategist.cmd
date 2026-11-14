@echo off
rem Fame Strategist - starts the local engine if it is not already running, then opens the app.
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo The virtual environment is missing. Re-run setup first.
  pause
  exit /b 1
)
call powershell -NoProfile -Command "try{Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8756/ -TimeoutSec 2|Out-Null;exit 0}catch{exit 1}"
if errorlevel 1 (
  start "Fame Strategist engine" /min ".venv\Scripts\python.exe" run.py
  call powershell -NoProfile -Command "for($i=0;$i -lt 30;$i++){try{Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8756/ -TimeoutSec 1|Out-Null;exit 0}catch{Start-Sleep -Milliseconds 400}};exit 1"
)
start "" "http://127.0.0.1:8756/"
endlocal
