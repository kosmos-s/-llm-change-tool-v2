@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run setup.bat first.
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install "pyinstaller==6.22.3"
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean LLMChangeTool.spec
if errorlevel 1 exit /b 1
start /wait "" "dist\LLMChangeTool\LLMChangeTool.exe" --self-test --report "dist\self-test.json"
if errorlevel 1 exit /b 1
echo Portable build: dist\LLMChangeTool\LLMChangeTool.exe
