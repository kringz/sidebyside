#!/usr/bin/env python3
"""
jQuery Fixer Script for Trino Local Lab
This script fixes the jQuery loading order in breaking_changes.html
"""

import os
import re

def fix_jquery_error():
    """Fix jQuery loading order in breaking_changes.html"""
    file_path = 'templates/breaking_changes.html'
    
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
    
    # Check if we need to wrap the document.ready script
    if '$(document).ready(' in content and 'window.addEventListener("load", function() {' not in content:
        print("Found jQuery usage, fixing loading order...")
        
        # Replace the jQuery document ready with a window load event wrapped script
        # Find the script section in the file
        script_section = re.search(r'{% block custom_scripts %}\s*<script>\s*(.*?)\s*</script>\s*{% endblock %}', 
                                 content, re.DOTALL)
        
        if script_section:
            # Extract the jQuery script
            jquery_script = script_section.group(1)
            
            # Create the new wrapped script with window.addEventListener
            wrapped_script = """{% block custom_scripts %}
<script>
// Wait for jQuery to be loaded first
window.addEventListener("load", function() {
    // Now jQuery is available
"""
            wrapped_script += jquery_script
            wrapped_script += """
});
</script>
{% endblock %}"""
            
            # Replace the old script with the new one
            new_content = content.replace(script_section.group(0), wrapped_script)
            
            # Write updated content back to file
            try:
                with open(file_path, 'w') as f:
                    f.write(new_content)
                print(f"Successfully updated {file_path}")
                return True
            except Exception as e:
                print(f"Error writing file: {e}")
                return False
        else:
            print("Script section not found in file")
            return False
    else:
        print("No jQuery loading issue found or already fixed")
        return True

if __name__ == "__main__":
    print("Trino Local Lab jQuery Fixer")
    print("=" * 30)
    current_dir = os.getcwd()
    print(f"Current directory: {current_dir}")
    
    success = fix_jquery_error()
    
    if success:
        print("\nJQuery fix applied successfully!")
        print("You can now run start_app.sh again to start the application.")
    else:
        print("\nFailed to apply jQuery fix automatically.")
        print("Please check the error messages above and try again.")