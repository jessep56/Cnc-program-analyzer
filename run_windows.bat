@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    set PYTHON=py -3
) else (
    set PYTHON=python
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating Python environment...
    %PYTHON% -m venv .venv
    if errorlevel 1 goto :error
)

call .venv\Scripts\activate.bat
if not exist ".venv\.cnc_analyzer_deps_v1_1_0" (
    echo Installing/updating analyzer dependencies...
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
    if errorlevel 1 goto :error
    type nul > ".venv\.cnc_analyzer_deps_v1_1_0"
)

python -m streamlit run app.py
exit /b 0

:error
echo.
echo Setup failed. Make sure Python 3.10 or newer is installed.
pause
exit /b 1
