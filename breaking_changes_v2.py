from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import traceback
import logging
import requests
import re
import sys
from web_scraper import scrape_trino_release_page, get_all_changes_between_versions, version_compare, fetch_all_trino_versions

# Configure logging
logger = logging.getLogger(__name__)

# Import models if available
try:
    from models import db, TrinoVersion
except ImportError:
    logger.warning("Models not available, running in standalone mode")
    db = None
    TrinoVersion = None

def register_breaking_changes_routes(app):
    # Create a test function to fetch versions 
    @app.route('/test_fetch_versions')
    def test_fetch_versions():
        try:
            logger.info("TEST: Explicitly fetching all Trino versions")
            versions = fetch_all_trino_versions()
            logger.info(f"TEST: Successfully fetched {len(versions)} versions")
            logger.info(f"TEST: First 10 versions: {versions[:10]}")
            return jsonify({
                'success': True,
                'versions': versions
            })
        except Exception as e:
            logger.error(f"TEST: Error fetching versions: {str(e)}")
            logger.error(traceback.format_exc())
            return jsonify({
                'success': False,
                'error': str(e)
            })
    
    @app.route('/breaking_changes')
    def breaking_changes():
        """Page for displaying changes for all releases between two Trino versions"""
        # Get all available versions if database is configured
        versions = []
        if db and TrinoVersion:
            try:
                versions = TrinoVersion.query.order_by(TrinoVersion.version.desc()).all()
            except Exception as e:
                logger.error(f"Error querying versions: {str(e)}")
                
        # If no versions in database or database not configured, fetch all available versions from the Trino website
        if not versions:
            try:
                logger.info("Fetching all available Trino versions from official website")
                versions = fetch_all_trino_versions()
                logger.info(f"Successfully fetched {len(versions)} versions from Trino website")
                
                # Print the first 5 versions to debug
                logger.info(f"First 5 versions: {versions[:5] if len(versions) >= 5 else versions}")
                
                # If versions is empty, raise an exception to fall back to the default
                if not versions:
                    raise ValueError("No versions fetched from website")
                    
            except Exception as e:
                logger.error(f"Error fetching Trino versions: {str(e)}")
                logger.error(traceback.format_exc())
                # Fallback to default version range if fetch fails
                default_versions = range(400, 475)
                versions = [{"version": str(v)} for v in default_versions]
            
        # Get configured versions from application config
        config = app.config.get('CURRENT_CONFIG', {})
        
        # Set default comparison to be between the two configured clusters
        cluster1_version = config.get('cluster1', {}).get('version', '406')
        cluster2_version = config.get('cluster2', {}).get('version', '405')
        
        # Use completely new template with entirely different loading approach
        return render_template('breaking_changes_v3.html',
                           available_versions=versions,
                           cluster1_version=cluster1_version,
                           cluster2_version=cluster2_version)


    @app.route('/compare_versions_v2', methods=['POST'])
    def compare_versions_v2():
        """API endpoint to compare changes between two Trino versions"""
        from_version = request.form.get('from_version')
        to_version = request.form.get('to_version')
        
        if not from_version or not to_version:
            return jsonify({
                'success': False,
                'message': 'Both from_version and to_version are required'
            })
        
        try:
            # Fetch all changes between versions
            changes = get_all_changes_between_versions(from_version, to_version)
            
            return jsonify({
                'success': True,
                'from_version': changes['from_version'],
                'to_version': changes['to_version'],
                'versions_checked': changes['versions_checked'],
                'total_versions': len(changes['versions_checked']),
                'connector_changes': changes['connector_changes'],
                'general_changes': changes['general_changes'],
                'processed_count': len(set([change.get('version') for change in changes['connector_changes'] + changes['general_changes']]))
            })
            
        except Exception as e:
            logger.error(f"Error comparing versions: {str(e)}")
            logger.error(traceback.format_exc())
            return jsonify({
                'success': False,
                'message': f"Error comparing versions: {str(e)}"
            })