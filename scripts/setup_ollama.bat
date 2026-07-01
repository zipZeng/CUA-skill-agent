@echo off
setlocal
cd /d "%~dp0.."
echo.
echo [CUA-Skill] Full setup: Python + Ollama app + vision model
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_ollama.ps1" %*
set ERR=%ERRORLEVEL%
echo.
if %ERR% NEQ 0 (
  echo Setup failed with exit code %ERR%
  pause
  exit /b %ERR%
)
echo.
echo Setup succeeded. Activate venv with: .venv\Scripts\activate
pause
