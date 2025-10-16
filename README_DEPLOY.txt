How to run this Streamlit app on Windows
=======================================

Prerequisites
- Windows 10/11
- Python 3.10+ installed and on PATH (the Windows Python launcher `py` or `python`)
- (Optional) Microsoft Outlook installed if you plan to use the "Outlook Folder" input source

Quick Start
1) Copy the entire folder (including this README, run_app.bat, requirements.txt, streamlit_app.py, and the app_core folder) to the target Windows machine.
2) Double-click run_app.bat.
   - The script creates a local virtual environment in .venv, upgrades pip, installs dependencies from requirements.txt, and launches the app.
3) Your browser should open automatically. If not, open http://localhost:8501/ manually.

Notes
- Outlook features require pywin32 and a local Outlook installation configured on the target machine. If Outlook is not installed or configured, you can still use the "Paste HTML" or "Upload File" sources within the app.
- If you have multiple Python versions installed and the launcher `py` is present, the script will try `py -3`. Otherwise it falls back to `python`.
- If a firewall prompt appears the first time Streamlit runs, allow access to localhost.

Troubleshooting
- "python is not recognized": Install Python from https://www.python.org/downloads/ and ensure "Add Python to PATH" is checked during installation.
- "Failed building wheel" or install errors: Update pip (`python -m pip install --upgrade pip`) and retry run_app.bat. Corporate proxies may require additional pip configuration.
- Outlook automation errors: Ensure Outlook is installed, running, and a profile/mailbox is configured. You can still use the non-Outlook input modes.


Build a self-contained EXE (PyInstaller)
----------------------------------------
This creates a distributable folder that does NOT require a Python installation on the target PC (Outlook still required).

Steps to build on your machine:
- Double-click `build_exe.bat` (or run it from a terminal).
- It creates a `.venv`, installs deps + PyInstaller, and builds into `dist/EmailPricerParser/`.
- Launch the app by running `dist\EmailPricerParser\EmailPricerParser.exe`.

What’s inside the EXE build:
- `EmailPricerParser.exe`: a launcher that starts Streamlit in-process via `launch_streamlit.py`.
- Your app code (`streamlit_app.py`, `app_core`, `Normalizers.py`, `Extractors.py`) is included as data so the launcher can load the script by path.
- Hidden imports are included for Outlook COM (pywin32).

Notes for EXE usage:
- The first run may be slower while Streamlit initializes.
- If Windows SmartScreen shows a warning, click “More info” → “Run anyway” (unsigned EXE).
- Outlook (classic desktop) must be installed and configured on the target PC; the “New Outlook” Store app does not support COM automation.
