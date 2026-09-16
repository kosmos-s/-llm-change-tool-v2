@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run setup.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m llm_change_tool %*
if errorlevel 1 (
  echo Application failed. Check the error above.
  pause
  exit /b 1
)
