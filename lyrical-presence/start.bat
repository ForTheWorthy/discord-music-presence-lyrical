@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Virtual environment not found. Running first-time setup...
  call "%~dp0setup-windows.bat"
  if errorlevel 1 exit /b 1
)

if not exist "lyrical-presence.json" (
  if exist "lyrical-presence.example.json" (
    echo Creating lyrical-presence.json from example...
    copy /Y "lyrical-presence.example.json" "lyrical-presence.json" >nul
    echo.
    echo Edit lyrical-presence.json and set your Discord client_id, then run start.bat again.
    notepad "lyrical-presence.json"
    exit /b 1
  )
)

echo Starting Lyrical Presence...
".venv\Scripts\lyrical-presence.exe" %*
if errorlevel 1 (
  echo.
  echo If that failed, trying module form...
  ".venv\Scripts\python.exe" -m lyrical_presence.cli %*
)

echo.
pause
