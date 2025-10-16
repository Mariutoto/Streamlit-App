@echo off
setlocal ENABLEDELAYEDEXPANSION

REM Build a self-contained onedir app with PyInstaller
cd /d "%~dp0"

where py >nul 2>nul && (set PY=py) || (set PY=python)

if not exist .venv\Scripts\python.exe (
  echo [INFO] Creating build venv ...
  %PY% -3 -m venv .venv 2>nul || %PY% -m venv .venv
)

call .venv\Scripts\activate.bat
if errorlevel 1 (
  echo [ERROR] Failed to activate venv.
  exit /b 1
)

python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller

REM Hidden imports for pywin32/COM and Streamlit runtime
set HIDDEN=--hidden-import pythoncom --hidden-import pywintypes --hidden-import win32com --hidden-import win32com.client

REM Ensure Streamlit and big libs resources are bundled
set COLLECT=--collect-all streamlit --collect-all pyarrow --collect-all pandas --collect-all numpy

REM Include app sources as data so bootstrap can load from file path
set DATAS=--add-data "streamlit_app.py;." --add-data "app_core;app_core" --add-data "Normalizers.py;." --add-data "Extractors.py;."

REM Optional icon if app_icon.ico exists
set ICONFLAG=
if exist app_icon.ico (
  set ICONFLAG=--icon app_icon.ico
)

echo [INFO] Building EXE with PyInstaller ...
pyinstaller --noconsole --clean --name EmailPricerParser %ICONFLAG% %HIDDEN% %COLLECT% %DATAS% launch_streamlit.py

if errorlevel 1 (
  echo [ERROR] PyInstaller build failed.
  exit /b 1
)

echo.
echo [SUCCESS] Build complete.
echo Run: dist\EmailPricerParser\EmailPricerParser.exe

REM Also build a debug console variant for troubleshooting
echo [INFO] Building DEBUG variant with console window ...
pyinstaller --console --clean --name EmailPricerParser_debug %ICONFLAG% %HIDDEN% %COLLECT% %DATAS% launch_streamlit.py
if not errorlevel 1 (
  echo [SUCCESS] Debug build at dist\EmailPricerParser_debug\EmailPricerParser_debug.exe
) else (
  echo [WARN] Debug build failed; continuing.
)

endlocal
