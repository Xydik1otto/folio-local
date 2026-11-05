@echo off
rem folio-local launcher: venv + deps + server, then open the browser.
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  python -m venv .venv || goto :error
)

if not exist ".venv\Scripts\uvicorn.exe" (
  echo Installing dependencies...
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :error
)

rem Find a free port (default 8000, FOLIO_PORT overrides).
set PORT=%FOLIO_PORT%
if "%PORT%"=="" set PORT=8000
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":%PORT% .*LISTENING"') do (
  echo Port %PORT% busy, trying 8001...
  set PORT=8001
)

echo Starting folio-local on http://127.0.0.1:%PORT% ...
start "" http://127.0.0.1:%PORT%
".venv\Scripts\uvicorn.exe" backend.main:app --host 127.0.0.1 --port %PORT%
goto :eof

:error
echo.
echo ERROR: startup failed. Is Python 3.12+ installed and on PATH?
pause
