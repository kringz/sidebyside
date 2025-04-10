#!/bin/bash

# Script to set up and run the Trino Comparison Tool

# Color output for better readability
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}==================================${NC}"
echo -e "${BLUE}  Trino Version Comparison Tool  ${NC}"
echo -e "${BLUE}==================================${NC}"

# Check if Python is installed
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    # Check if the python command is actually Python 3
    PYTHON_VER=$(python --version 2>&1)
    if [[ $PYTHON_VER == *"Python 3"* ]]; then
        PYTHON_CMD="python"
    else
        echo -e "${YELLOW}Python 3 is not installed. Please install Python 3 first.${NC}"
        exit 1
    fi
else
    echo -e "${YELLOW}Python 3 is not installed. Please install Python 3 first.${NC}"
    exit 1
fi

echo -e "\n${GREEN}1. Creating Python virtual environment...${NC}"
# Check if virtual environment exists
if [ ! -d "venv" ]; then
    $PYTHON_CMD -m venv venv
else
    echo -e "${YELLOW}Virtual environment already exists. Using existing venv.${NC}"
fi

# Activate virtual environment (platform dependent)
if [[ "$OSTYPE" == "darwin"* || "$OSTYPE" == "linux-gnu"* ]]; then
    echo -e "${GREEN}Activating virtual environment (Unix/Mac)...${NC}"
    source venv/bin/activate
elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" || "$OSTYPE" == "cygwin" ]]; then
    echo -e "${GREEN}Activating virtual environment (Windows)...${NC}"
    source venv/Scripts/activate
else
    echo -e "${YELLOW}Unknown OS type: $OSTYPE. Trying Unix-style activation...${NC}"
    # Try both Unix and Windows styles
    if [ -f "venv/bin/activate" ]; then
        source venv/bin/activate
    elif [ -f "venv/Scripts/activate" ]; then
        source venv/Scripts/activate
    else
        echo -e "${YELLOW}Warning: Could not find activation script. Continuing anyway...${NC}"
    fi
fi

echo -e "\n${GREEN}2. Installing required dependencies...${NC}"
# Run the dependency installer script directly
python install_dependencies.py

echo -e "\n${GREEN}3. Initializing the database...${NC}"
# Set DATABASE_URL environment variable to use SQLite if not set
if [ -z "$DATABASE_URL" ]; then
    echo -e "${YELLOW}DATABASE_URL not set, using SQLite database${NC}"
    export DATABASE_URL="sqlite:///trino_comparison.db"
fi

python init_db.py

echo -e "\n${GREEN}4. Starting the application...${NC}"
echo -e "${YELLOW}The application will be available at: http://localhost:5000${NC}"

# Try to open browser automatically (platform dependent)
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo -e "${GREEN}Opening browser automatically...${NC}"
    (sleep 2 && open http://localhost:5000) &
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    # Check for different Linux browser openers
    if command -v xdg-open &> /dev/null; then
        (sleep 2 && xdg-open http://localhost:5000) &
    elif command -v gnome-open &> /dev/null; then
        (sleep 2 && gnome-open http://localhost:5000) &
    elif command -v firefox &> /dev/null; then
        (sleep 2 && firefox http://localhost:5000) &
    elif command -v google-chrome &> /dev/null; then
        (sleep 2 && google-chrome http://localhost:5000) &
    else
        echo -e "${YELLOW}Could not find a browser opener. Please manually navigate to:${NC}"
        echo -e "${YELLOW}http://localhost:5000${NC}"
    fi
elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" || "$OSTYPE" == "cygwin" ]]; then
    echo -e "${GREEN}Opening browser automatically...${NC}"
    (sleep 2 && start http://localhost:5000) &
else
    echo -e "${YELLOW}Could not detect OS type to open browser automatically.${NC}"
    echo -e "${YELLOW}Please open http://localhost:5000 in your browser.${NC}"
fi

# Set Flask environment for development mode
export FLASK_ENV="development"

# Run the application
python run.py