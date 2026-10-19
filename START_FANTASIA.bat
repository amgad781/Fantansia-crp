@echo off
cd /d "%~dp0"
set PYTHONDONTWRITEBYTECODE=1
start "" ".\venv\Scripts\pythonw.exe" main.py
