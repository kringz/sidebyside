#!/usr/bin/env python3
"""
Script to check all possible Trino versions more efficiently and add them to the database
"""
from main import app
from models import db, TrinoVersion
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_version_exists(version):
    """Check if a specific Trino version exists"""
    url = f"https://trino.io/docs/current/release/release-{version}.html"
    try:
        response = requests.head(url, timeout=5)  # Using HEAD request for efficiency
        if response.status_code == 200:
            logger.info(f"Found valid version: {version}")
            return {
                'version': version,
                'exists': True,
                'url': url
            }
    except Exception as e:
        logger.debug(f"Error checking version {version}: {str(e)}")
    
    return {
        'version': version,
        'exists': False,
        'url': url
    }

def check_all_trino_versions():
    """Check all possible Trino versions in parallel"""
    # Current Trino versions range approximately from 300 to 480
    # Adjust the range as needed
    versions_to_check = list(range(300, 480))
    
    # Use ThreadPoolExecutor for parallel requests
    valid_versions = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        # Submit all version checks to the executor
        future_to_version = {executor.submit(check_version_exists, str(v)): v for v in versions_to_check}
        
        # Process results as they complete
        for future in as_completed(future_to_version):
            result = future.result()
            if result['exists']:
                valid_versions.append(result)
    
    # Sort by version number (descending)
    valid_versions.sort(key=lambda x: int(x['version']), reverse=True)
    logger.info(f"Found {len(valid_versions)} valid Trino versions")
    
    return valid_versions

def update_database_with_all_versions():
    """Update the database with all found Trino versions"""
    with app.app_context():
        # Get current versions in the database
        current_versions = set(v.version for v in TrinoVersion.query.all())
        logger.info(f"Current versions in database: {sorted(current_versions)}")
        
        # Check all possible versions
        valid_versions = check_all_trino_versions()
        
        # Add versions that don't already exist
        versions_added = 0
        for version_info in valid_versions:
            version = version_info['version']
            if version not in current_versions:
                # Add with basic data (we don't have exact release dates)
                version_data = {
                    'version': version,
                    'release_notes_url': version_info['url']
                }
                
                new_version = TrinoVersion(**version_data)
                db.session.add(new_version)
                versions_added += 1
                logger.info(f"Adding version {version}")
        
        # Commit changes if any versions were added
        if versions_added > 0:
            db.session.commit()
            logger.info(f"Added {versions_added} new Trino versions to the database")
        else:
            logger.info("No new versions to add")
        
        # Log all versions
        all_versions = [v.version for v in TrinoVersion.query.order_by(TrinoVersion.version.desc()).all()]
        logger.info(f"All versions in database now: {all_versions}")

if __name__ == "__main__":
    update_database_with_all_versions()