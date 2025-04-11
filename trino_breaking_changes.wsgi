#!/usr/bin/env python3
import sys
import os

# Add the application directory to the Python path
sys.path.insert(0, os.path.dirname(__file__))

# Import the Flask application
from breaking_changes_app import app as application