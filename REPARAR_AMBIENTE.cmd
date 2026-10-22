@echo off
setlocal EnableExtensions
set "PYTHONHOME="
set "PYTHONPATH="
cd /d "%~dp0"
where pythonw >nul 2>&1
if not errorlevel 1 (
  start "" pythonw "%~dp0tools\assistente.py" --mode run --repair
  exit /b 0
)
where python >nul 2>&1
if errorlevel 1 (
  echo Esta previa precisa de Python 3.11, 3.12, 3.13 ou 3.14 de 64 bits no computador de desenvolvimento.
  pause
  exit /b 1
)
python "%~dp0tools\assistente.py" --mode run --repair
endlocal
