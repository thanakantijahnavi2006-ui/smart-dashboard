@echo off
setlocal
cd /d "%~dp0"
title Smart Data Dashboard

echo ============================================
echo   Smart Data Dashboard - starting up
echo ============================================

set "PYEXE="
set "PYARG="

rem 1) py launcher
py -3 --version >nul 2>nul
if not errorlevel 1 (
    set "PYEXE=py"
    set "PYARG=-3"
)

rem 2) python on PATH (the Microsoft Store stub fails this test)
if not defined PYEXE (
    python --version >nul 2>nul
    if not errorlevel 1 set "PYEXE=python"
)

rem 3) common install folders
if not defined PYEXE (
    for %%P in (
        "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
        "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
        "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
        "%ProgramFiles%\Python313\python.exe"
        "%ProgramFiles%\Python312\python.exe"
        "C:\Python313\python.exe"
    ) do (
        if not defined PYEXE if exist %%P set "PYEXE=%%~P"
    )
)

if not defined PYEXE (
    echo.
    echo Python was not found on this computer.
    echo Install Python 3.13 from python.org and tick Add python.exe to PATH,
    echo then double-click run.bat again.
    pause
    exit /b 1
)

echo Using Python: %PYEXE% %PYARG%

if not exist "venv\Scripts\python.exe" (
    echo Creating virtual environment...
    "%PYEXE%" %PYARG% -m venv venv
    if errorlevel 1 (
        echo Could not create the virtual environment.
        pause
        exit /b 1
    )
)

if not exist "venv\installed.flag" (
    echo Installing libraries - this takes 1 to 3 minutes the first time...
    "venv\Scripts\python.exe" -m pip install --disable-pip-version-check --upgrade pip
    "venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
    if errorlevel 1 (
        echo Library install failed. Check your internet connection and run again.
        pause
        exit /b 1
    )
    echo ok> "venv\installed.flag"
)

if not exist "sample_data\messy_sales_sample.xlsx" "venv\Scripts\python.exe" make_sample.py

rem Skip the Streamlit email prompt
if not exist "%USERPROFILE%\.streamlit\credentials.toml" (
    mkdir "%USERPROFILE%\.streamlit" >nul 2>nul
    > "%USERPROFILE%\.streamlit\credentials.toml" echo [general]
    >> "%USERPROFILE%\.streamlit\credentials.toml" echo email = ""
)

echo.
echo Opening the app in your browser. Keep this window open.
"venv\Scripts\python.exe" -m streamlit run app.py
pause
