import os
import logging
import json
import traceback
from flask import Flask, request, render_template, jsonify, Blueprint

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create a Blueprint for the simple compare functionality
simple_compare = Blueprint('simple_compare', __name__, url_prefix='/simple_compare')

@simple_compare.route('/', methods=['GET'])
def simple_compare_page():
    """Simple comparison page for Trino versions"""
    # Basic version list for testing
    versions = [
        {"version": "406", "name": "Release 406"},
        {"version": "405", "name": "Release 405"},
        {"version": "404", "name": "Release 404"},
        {"version": "403", "name": "Release 403"},
        {"version": "402", "name": "Release 402"},
        {"version": "401", "name": "Release 401"},
        {"version": "398", "name": "Release 398"},
        {"version": "393", "name": "Release 393"},
        {"version": "389", "name": "Release 389"}
    ]
    
    # For a larger range of versions
    all_versions = []
    # Include older versions (0.x series)
    for v in range(52, 300):
        all_versions.append({"version": f"0.{v}", "name": f"Release 0.{v}"})
    
    # Include newer versions (300 to 500)
    for v in range(300, 500):
        all_versions.append({"version": str(v), "name": f"Release {v}"})
    
    # Sort versions in descending order
    all_versions.sort(key=lambda x: x["version"], reverse=True)
    
    # Use the shorter list for testing
    versions_json = json.dumps(versions)
    
    # Set default comparison versions
    from_version = "405"
    to_version = "406"
    
    # Render a simple template with the comparison form
    return render_template('simple_compare.html', 
                          versions=versions,
                          versions_json=versions_json,
                          from_version=from_version,
                          to_version=to_version)

@simple_compare.route('/compare', methods=['POST'])
def compare_versions():
    """Simple API endpoint to compare two Trino versions"""
    try:
        # Get form data
        from_version = request.form.get('from_version', '')
        to_version = request.form.get('to_version', '')
        
        logger.info(f"Compare request: from={from_version}, to={to_version}")
        
        if not from_version or not to_version:
            return jsonify({
                'success': False,
                'message': 'Both from_version and to_version are required'
            })
        
        # Create a test response with empty arrays
        response = {
            'success': True,
            'from_version': from_version,
            'to_version': to_version,
            'message': 'Versions compared successfully',
            'connector_changes': [
                {
                    'category': 'MySQL',
                    'version': from_version,
                    'title': 'Sample MySQL connector change',
                    'description': 'This is a sample change for testing purposes.'
                },
                {
                    'category': 'PostgreSQL',
                    'version': to_version,
                    'title': 'Sample PostgreSQL connector change',
                    'description': 'Another sample change for testing the UI.'
                }
            ],
            'general_changes': [
                {
                    'category': 'General',
                    'version': from_version,
                    'title': 'Sample general change',
                    'description': 'This is a sample general change for testing purposes.'
                }
            ],
            'versions_checked': [from_version, to_version]
        }
        
        logger.info("Successfully processed comparison")
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Error comparing versions: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'message': f"Error comparing versions: {str(e)}"
        })

def register_simple_compare(app):
    """Register the simple compare blueprint with the Flask app"""
    app.register_blueprint(simple_compare)