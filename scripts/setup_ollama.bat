@echo off
setlocal
cd /d "%~dp0.."
echo.
echo [CUA-Skill] Ollama model setup
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_ollama.ps1" %*
set ERR=%ERRORLEVEL%
echo.
if %ERR% NEQ 0 (
  echo Setup failed with exit code %ERR%
  pause
  exit /b %ERR%
)
pause
