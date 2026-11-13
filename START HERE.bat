@echo off
title Fame Strategist
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo This app needs its own Python environment, once only.
  echo In PowerShell, from this folder, run:
  echo     python -m venv .venv
  echo     .venv\Scripts\pip install -r requirements.txt
  echo Then double-click this file again.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" run.py
pause
