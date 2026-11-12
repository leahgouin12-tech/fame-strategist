@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo First run: setting up the local environment.
  python -m venv .venv || (echo Python 3.11 or newer is required. & pause & exit /b 1)
  ".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt
)
".venv\Scripts\python.exe" run.py
pause
