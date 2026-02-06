@echo off
REM Setup script for FreeJobAlert Scraper (Windows)

echo ========================================
echo FreeJobAlert Scraper Setup (Windows)
echo ========================================
echo.

REM Check Python installation
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python 3 is not installed or not in PATH.
    echo Please install Python 3.8 or higher from python.org
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo [OK] Python version: %PYTHON_VERSION%

REM Create virtual environment
echo.
echo Creating virtual environment...
python -m venv venv

if errorlevel 1 (
    echo [ERROR] Failed to create virtual environment
    pause
    exit /b 1
)

echo [OK] Virtual environment created

REM Activate virtual environment
echo.
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Upgrade pip
echo.
echo Upgrading pip...
python -m pip install --upgrade pip

REM Install dependencies
echo.
echo Installing dependencies...
pip install -r requirements.txt

if errorlevel 1 (
    echo [ERROR] Failed to install dependencies
    pause
    exit /b 1
)

echo [OK] Dependencies installed successfully

REM Create necessary directories
echo.
echo Creating directories...
if not exist "pdfs" mkdir pdfs
if not exist "logs" mkdir logs
echo [OK] Directories created

REM Create .env file if it doesn't exist
if not exist ".env" (
    echo.
    echo Creating .env file from template...
    copy .env.example .env
    echo [OK] .env file created
    echo.
    echo [WARNING] IMPORTANT: Please edit .env file and add your credentials:
    echo    - SUPABASE_URL
    echo    - SUPABASE_KEY
    echo    - GOOGLE_DRIVE_FOLDER_ID
    echo.
) else (
    echo.
    echo [OK] .env file already exists
)

REM Check for Google credentials
if not exist "credentials.json" (
    echo.
    echo [WARNING] credentials.json not found
    echo    Please download your Google Drive API credentials and save as credentials.json
    echo.
) else (
    echo [OK] Google credentials found
)

echo.
echo ========================================
echo Setup Complete!
echo ========================================
echo.
echo Next steps:
echo 1. Edit .env file with your credentials
echo 2. Add credentials.json for Google Drive API
echo 3. Run: venv\Scripts\activate
echo 4. Run: python main.py
echo.
echo For more information, see README.md
echo.
pause