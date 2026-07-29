@echo off
REM Run Lyrical Presence in the background without leaving a console window open.
REM Useful for Windows Startup.
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
  echo Run setup-windows.bat first.
  pause
  exit /b 1
)

start "" ".venv\Scripts\pythonw.exe" -m lyrical_presence.cli
