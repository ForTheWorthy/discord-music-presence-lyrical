@echo off
setlocal
cd /d "%~dp0"

echo === Lyrical Presence Windows setup ===
where python >nul 2>&1
if errorlevel 1 (
  echo Python was not found on PATH. Install Python 3.10+ from https://www.python.org/downloads/
  echo Make sure "Add python.exe to PATH" is checked.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  python -m venv .venv
  if errorlevel 1 (
    echo Failed to create .venv
    pause
    exit /b 1
  )
)

echo Installing / updating package...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -e .
if errorlevel 1 (
  echo Install failed.
  pause
  exit /b 1
)

if not exist "lyrical-presence.json" (
  copy /Y "lyrical-presence.example.json" "lyrical-presence.json" >nul
  echo Created lyrical-presence.json — set client_id to your Discord Application ID.
)

echo.
echo Setup complete. You can now double-click start.bat
echo.
pause
