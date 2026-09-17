@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto install
where py >nul 2>nul
if errorlevel 1 goto python_fallback
py -3.11 -m venv .venv
if not errorlevel 1 goto install
:python_fallback
python -c "import sys; assert (3,11) <= sys.version_info[:2] < (3,14)" >nul 2>nul
if errorlevel 1 goto missing_python
python -m venv .venv
if errorlevel 1 goto failed
:install
".venv\Scripts\python.exe" -m pip install -r requirements-lock.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install --no-deps -e .
if errorlevel 1 goto failed
if exist ".git" git config core.hooksPath .githooks
echo Setup complete. Run run.bat to start.
pause
exit /b 0
:missing_python
echo Install Python 3.11 for Windows with Add Python to PATH enabled.
:failed
echo Setup failed. Check the error above.
pause
exit /b 1
