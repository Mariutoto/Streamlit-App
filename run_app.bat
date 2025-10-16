@echo off
setlocal ENABLEDELAYEDEXPANSION

REM Change to the folder where this script lives
cd /d "%~dp0"

REM Choose Python launcher: prefer 'py', fall back to 'python'
where py >nul 2>nul && (set PY=py) || (set PY=python)

REM Create virtual environment if missing
if not exist .venv\Scripts\python.exe (
  echo [INFO] Creating virtual environment in .venv ...
  %PY% -3 -m venv .venv 2>nul || %PY% -m venv .venv
)

REM Activate venv
call .venv\Scripts\activate.bat
if errorlevel 1 (
  echo [ERROR] Failed to activate virtual environment.
  exit /b 1
)

REM Upgrade pip and install requirements
python -m pip install --upgrade pip
if exist requirements.txt (
  echo [INFO] Installing requirements from requirements.txt ...
  pip install -r requirements.txt
  REM Ensure pywin32 postinstall runs (safe to run even if already done)
  python -m pywin32_postinstall -install >nul 2>nul
) else (
  echo [WARN] requirements.txt not found; attempting to run anyway.
)

REM Run the Streamlit app
echo [INFO] Launching Streamlit app ...
streamlit run streamlit_app.py

endlocal
