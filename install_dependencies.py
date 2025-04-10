#!/usr/bin/env python
"""
Install script for Trino Comparison Tool Dependencies
This script checks for and installs required dependencies for the Trino Comparison Tool
"""

import sys
import subprocess
import importlib.util

# Color output for better readability
class Colors:
    GREEN = '\033[0;32m'
    BLUE = '\033[0;34m'
    YELLOW = '\033[1;33m' 
    RED = '\033[0;31m'
    NC = '\033[0m'  # No Color

def print_c(text, color=Colors.NC):
    """Print colored text to console"""
    print(f"{color}{text}{Colors.NC}")

def is_package_installed(package_name):
    """Check if a package is installed"""
    try:
        spec = importlib.util.find_spec(package_name)
        return spec is not None
    except (ImportError, AttributeError):
        return False

def install_dependencies():
    """Install all required dependencies"""
    print_c("Checking and installing required dependencies...", Colors.BLUE)
    
    # Core dependencies
    dependencies = [
        ("flask", "Flask"),
        ("flask_sqlalchemy", "Flask-SQLAlchemy"),
        ("gunicorn", "gunicorn"),
        ("pyyaml", "PyYAML"),
        ("docker", "docker"),
        ("trafilatura", "trafilatura"),
        ("trino", "trino"),
        ("email_validator", "email-validator"),
        ("bs4", "beautifulsoup4"),
        ("requests", "requests")
    ]
    
    for module_name, package_name in dependencies:
        if not is_package_installed(module_name):
            print_c(f"Installing {package_name}...", Colors.YELLOW)
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])
                print_c(f"Successfully installed {package_name}", Colors.GREEN)
            except subprocess.CalledProcessError:
                print_c(f"Failed to install {package_name}. Please install it manually.", Colors.RED)
        else:
            print_c(f"{package_name} is already installed.", Colors.GREEN)
    
    print_c("\nAll dependencies checked and installed!", Colors.BLUE)

if __name__ == "__main__":
    # Print header
    print_c("=================================", Colors.BLUE)
    print_c("  Trino Comparison Dependencies  ", Colors.BLUE)
    print_c("=================================", Colors.BLUE)
    print()
    
    # Install dependencies
    install_dependencies()