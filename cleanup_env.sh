#!/bin/bash
# Cleanup script for Trino Local Lab environment

echo "========================================================"
echo "   Cleaning up Trino Local Lab environment"
echo "========================================================"

# Stop all running Docker containers
echo "Stopping and removing all Docker containers..."
docker stop $(docker ps -a -q) 2>/dev/null || echo "No containers to stop"
docker rm $(docker ps -a -q) 2>/dev/null || echo "No containers to remove"

# Remove Docker volumes
echo "Removing Docker volumes..."
docker volume prune -f

# Clean up Python cache files
echo "Cleaning up Python cache..."
find . -type d -name "__pycache__" -exec rm -rf {} +  2>/dev/null || true
find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
find . -name "*.pyc" -delete

# Clean up virtual environment
echo "Removing virtual environment..."
rm -rf .venv 2>/dev/null || true

# Clean up database files
echo "Removing database files..."
rm -f *.db 2>/dev/null || true
rm -f *.sqlite 2>/dev/null || true
rm -f *.sqlite3 2>/dev/null || true

# Clear config files
echo "Clearing configuration files..."
rm -f config.json 2>/dev/null || true

# Remove logs
echo "Cleaning up log files..."
rm -f *.log 2>/dev/null || true

echo "========================================================"
echo "   Environment cleanup complete"
echo "========================================================"
echo "To rebuild the environment:"
echo "1. Create a new virtual environment: python -m venv .venv"
echo "2. Activate it: source .venv/bin/activate (Linux/Mac) or .venv\\Scripts\\activate (Windows)"
echo "3. Install dependencies: pip install -r requirements.txt"
echo "4. Initialize the database: python init_db.py"
echo "5. Start the application: python app.py"
echo "========================================================"