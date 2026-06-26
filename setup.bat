@echo off
echo ================================================
echo  Stock Dashboard — First Time Setup
echo ================================================
echo.
echo This will set up everything needed to run the app.
echo This only needs to be done once.
echo.

:: Check Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not on PATH.
    echo Please download and install Python 3.10 or higher from:
    echo https://www.python.org/downloads/
    echo.
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

echo Python found. Creating virtual environment...
python -m venv venv
if errorlevel 1 (
    echo ERROR: Failed to create virtual environment.
    pause
    exit /b 1
)

echo Activating virtual environment...
call venv\Scripts\activate

echo Installing required packages...
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install packages.
    pause
    exit /b 1
)

echo.
echo ================================================
echo  Setup complete!
echo  You can now launch the app by double-clicking:
echo  run_dashboard.vbs
echo ================================================
echo.
pause