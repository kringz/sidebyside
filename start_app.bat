@echo off
echo ================================== 
echo   Trino Version Comparison Tool   
echo ================================== 
echo.

REM Check if Python is installed (prefer python3 command if available)
python3 --version >nul 2>&1
if %errorlevel% equ 0 (
    set PYTHON_CMD=python3
    goto PYTHON_FOUND
)

REM Try regular python command
python --version >nul 2>&1
if %errorlevel% equ 0 (
    REM Check if this is Python 3
    for /f "tokens=2" %%a in ('python --version 2^>^&1') do set PYTHON_VER=%%a
    echo Python version detected: %PYTHON_VER%
    if "%PYTHON_VER:~0,1%"=="3" (
        set PYTHON_CMD=python
        goto PYTHON_FOUND
    ) else (
        echo Python 3 is required but Python 2 was found.
        exit /b 1
    )
) else (
    echo Python is not installed or not in PATH. Please install Python first.
    exit /b 1
)

:PYTHON_FOUND
echo 1. Creating Python virtual environment...
if not exist venv (
    %PYTHON_CMD% -m venv venv
) else (
    echo Virtual environment already exists. Using existing venv.
)

echo.
echo 2. Activating virtual environment...
call venv\Scripts\activate.bat || (
    echo Warning: Could not activate virtual environment. 
    echo Continuing without activation, but this may cause issues.
)

echo.
echo 3. Installing required dependencies...
pip install --upgrade pip
pip install flask flask-sqlalchemy gunicorn pyyaml docker trafilatura trino email-validator

echo.
echo 4. Initializing the database...
REM Set DATABASE_URL environment variable to use SQLite if not set
if "%DATABASE_URL%"=="" (
    echo DATABASE_URL not set, using SQLite database
    set DATABASE_URL=sqlite:///trino_comparison.db
)

python init_db.py

echo.
echo 5. Starting the application...
echo The application will be available at: http://localhost:5000

REM Open browser automatically
start "" http://localhost:5000

REM Set Flask environment for development mode
set FLASK_ENV=development

REM Run the application
python run.py