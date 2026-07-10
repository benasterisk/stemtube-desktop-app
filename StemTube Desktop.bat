@echo off
title StemTube Desktop
cd /d "%~dp0"

:: Check if venv exists
if not exist "venv\Scripts\python.exe" (
    echo.
    echo  StemTube Desktop - First Time Setup Required
    echo  =========================================
    echo.
    echo  Virtual environment not found. Running setup...
    echo.
    python setup_desktop.py
    if errorlevel 1 (
        echo.
        echo  Setup failed. Please check the error messages above.
        echo  Make sure Python 3.12+ is installed from python.org
        pause
        exit /b 1
    )
)

:: Activate venv and launch
call venv\Scripts\activate.bat
python launcher.py %*

:: If launcher exits with error, pause so user can see the message
if errorlevel 1 (
    echo.
    echo  StemTube Desktop has stopped. Press any key to close.
    pause >nul
)
