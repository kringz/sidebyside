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
if ! command -v python3 &> /dev/null; then
    echo -e "${YELLOW}Python 3 is not installed. Please install Python 3 first.${NC}"
    exit 1
fi

echo -e "\n${GREEN}1. Creating Python virtual environment...${NC}"
# Check if virtual environment exists
if [ ! -d "venv" ]; then
    python3 -m venv venv
else
    echo -e "${YELLOW}Virtual environment already exists. Using existing venv.${NC}"
fi

# Activate virtual environment (platform dependent)
if [[ "$OSTYPE" == "darwin"* || "$OSTYPE" == "linux-gnu"* ]]; then
    echo -e "${GREEN}Activating virtual environment (Unix/Mac)...${NC}"
    source venv/bin/activate
elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    echo -e "${GREEN}Activating virtual environment (Windows)...${NC}"
    source venv/Scripts/activate
else
    echo -e "${YELLOW}Unknown OS. Trying Unix-style activation...${NC}"
    source venv/bin/activate
fi

echo -e "\n${GREEN}2. Installing required dependencies...${NC}"
pip install --upgrade pip
pip install flask flask-sqlalchemy gunicorn psycopg2-binary pyyaml docker trafilatura trino email-validator

echo -e "\n${GREEN}3. Initializing the database...${NC}"
python init_db.py

echo -e "\n${GREEN}4. Starting the application...${NC}"
echo -e "${YELLOW}The application will be available at: http://localhost:5000${NC}"

# Try to open browser automatically (platform dependent)
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo -e "${GREEN}Opening browser automatically...${NC}"
    (sleep 2 && open http://localhost:5000) &
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    echo -e "${GREEN}Opening browser automatically...${NC}"
    (sleep 2 && xdg-open http://localhost:5000) &
elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    echo -e "${GREEN}Opening browser automatically...${NC}"
    (sleep 2 && start http://localhost:5000) &
else
    echo -e "${YELLOW}Could not detect OS type to open browser automatically.${NC}"
    echo -e "${YELLOW}Please open http://localhost:5000 in your browser.${NC}"
fi

# Run the application
python run.py