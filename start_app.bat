@echo off
echo ================================== 
echo   Trino Version Comparison Tool   
echo ================================== 
echo.

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python is not installed or not in PATH. Please install Python first.
    exit /b 1
)

echo 1. Creating Python virtual environment...
if not exist venv (
    python -m venv venv
) else (
    echo Virtual environment already exists. Using existing venv.
)

echo.
echo 2. Activating virtual environment...
call venv\Scripts\activate.bat

echo.
echo 3. Installing required dependencies...
pip install --upgrade pip
pip install flask flask-sqlalchemy gunicorn psycopg2-binary pyyaml docker trafilatura trino email-validator

echo.
echo 4. Initializing the database...
python init_db.py

echo.
echo 5. Starting the application...
echo The application will be available at: http://localhost:5000

REM Open browser automatically
start "" http://localhost:5000

REM Run the application
python run.py