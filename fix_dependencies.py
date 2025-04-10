#!/usr/bin/env python3
"""
Dependency Fixer Script for Trino Local Lab
This script automatically fixes the dependency issues in breaking_changes.py
"""

import os
import sys
import re

def fix_breaking_changes_file():
    """Fix the breaking_changes.py file by replacing problematic imports"""
    file_path = 'breaking_changes.py'
    
    # Check if file exists
    if not os.path.exists(file_path):
        print(f"Error: {file_path} not found in current directory")
        return False
    
    # Read current file content
    try:
        with open(file_path, 'r') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading file: {e}")
        return False
    
    # Replace the problematic imports
    if 'from distutils.version import LooseVersion' in content:
        print("Found distutils import, replacing with custom version_compare function...")
        # Replace distutils import with custom version comparison function
        content = content.replace(
            'from distutils.version import LooseVersion',
            '''
# Simple version comparison function to replace LooseVersion
def version_compare(v1, v2):
    """Compare two version strings"""
    def normalize(v):
        return [int(x) for x in re.sub(r'[^0-9]', '.', v).split('.') if x]
    
    v1_parts = normalize(v1)
    v2_parts = normalize(v2)
    
    for i in range(max(len(v1_parts), len(v2_parts))):
        v1_part = v1_parts[i] if i < len(v1_parts) else 0
        v2_part = v2_parts[i] if i < len(v2_parts) else 0
        if v1_part > v2_part:
            return 1
        elif v1_part < v2_part:
            return -1
    return 0
'''
        )
        
        # Replace all instances of LooseVersion with version_compare
        content = re.sub(r'LooseVersion\(([^)]+)\) ([<>=]+) LooseVersion\(([^)]+)\)', 
                         r'version_compare(\1, \3) \2 0', content)
        content = re.sub(r'from_v = LooseVersion\(([^)]+)\)', r'from_v = \1', content)
        content = re.sub(r'to_v = LooseVersion\(([^)]+)\)', r'to_v = \1', content)
        content = re.sub(r'if from_v > to_v:', r'if version_compare(from_version, to_version) > 0:', content)
        
        # Replace other LooseVersion references in version sorting 
        content = content.replace(
            'versions.sort(key=lambda x: LooseVersion(x))',
            'versions.sort(key=lambda v: [int(x) for x in re.findall(r\'\\d+\', v)])'
        )
    
    # Fix BeautifulSoup import
    if 'from bs4 import BeautifulSoup' in content:
        print("Found BeautifulSoup direct import, replacing with try-except block...")
        # Remove direct import
        content = content.replace('from bs4 import BeautifulSoup', '')
        
        # Add dummy class and try-except
        if 'class DummyBeautifulSoup' not in content:
            # Find a good insertion point - after imports but before functions
            insert_point = re.search(r'(import [^\n]+\n+)', content, re.DOTALL)
            if insert_point:
                insert_index = insert_point.end()
                dummy_class = '''
# Configure logging
logger = logging.getLogger(__name__)

# Define dummy BeautifulSoup class for when the actual package is not available
class DummyBeautifulSoup:
    def __init__(self, *args, **kwargs):
        pass
        
    def find(self, *args, **kwargs):
        return None
        
    def find_next(self, *args, **kwargs):
        return None
        
    def find_all(self, *args, **kwargs):
        return []
        
    def get_text(self, *args, **kwargs):
        return ""

# Set BeautifulSoup to the dummy implementation by default
BeautifulSoup = DummyBeautifulSoup

# Try to import the real BeautifulSoup if available
try:
    from bs4 import BeautifulSoup
    logger.info("BeautifulSoup4 is available for web scraping.")
except ImportError:
    logger.warning("BeautifulSoup4 is not installed. Web scraping functionality will be limited.")

'''
                content = content[:insert_index] + dummy_class + content[insert_index:]
    
    # Update the check for BeautifulSoup availability
    content = content.replace(
        "if not 'bs4' in sys.modules:",
        "if isinstance(BeautifulSoup, DummyBeautifulSoup):"
    )
    
    # Write updated content back to file
    try:
        with open(file_path, 'w') as f:
            f.write(content)
        print(f"Successfully updated {file_path}")
        return True
    except Exception as e:
        print(f"Error writing file: {e}")
        return False

if __name__ == "__main__":
    print("Trino Local Lab Dependency Fixer")
    print("=" * 30)
    current_dir = os.getcwd()
    print(f"Current directory: {current_dir}")
    
    success = fix_breaking_changes_file()
    
    if success:
        print("\nFixes applied successfully!")
        print("You can now run start_app.sh again to start the application.")
    else:
        print("\nFailed to apply fixes automatically.")
        print("Please check the error messages above and try again.")