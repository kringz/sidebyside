#!/usr/bin/env python3
"""
Script to scrape Trino versions from the official release page and add them to the database
"""
from main import app
from models import db, TrinoVersion
from datetime import date
import requests
from bs4 import BeautifulSoup
import re
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def scrape_trino_releases():
    """Scrape Trino versions from the official release page"""
    releases_url = "https://trino.io/docs/current/release/"
    
    try:
        logger.info(f"Scraping Trino releases from {releases_url}")
        response = requests.get(releases_url)
        
        if response.status_code != 200:
            logger.error(f"Failed to fetch releases page: {response.status_code}")
            # Try to check if individual pages are accessible despite index error
            test_version = "474"
            test_url = f"https://trino.io/docs/current/release/release-{test_version}.html"
            test_response = requests.get(test_url)
            logger.info(f"Testing direct access to version {test_version}: {test_response.status_code}")
            versions = extract_versions_from_direct_access()
            return versions
        
        # Parse the HTML content
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Look for links to release pages
        version_links = []
        release_pattern = re.compile(r'release-(\d+)\.html')
        
        for link in soup.find_all('a', href=True):
            match = release_pattern.search(link['href'])
            if match:
                version = match.group(1)
                version_links.append({
                    'version': version,
                    'url': f"https://trino.io/docs/current/release/release-{version}.html"
                })
        
        logger.info(f"Found {len(version_links)} Trino versions on the release page")
        return version_links
    
    except Exception as e:
        logger.error(f"Error scraping Trino releases: {str(e)}")
        logger.info("Falling back to direct access method")
        versions = extract_versions_from_direct_access()
        return versions

def extract_versions_from_direct_access():
    """Extract versions by direct access to known version URLs"""
    versions = []
    # Test a range of possible version numbers
    # Current latest is around 474, so test up to 480 to be safe
    for version_number in range(380, 481):
        version = str(version_number)
        url = f"https://trino.io/docs/current/release/release-{version}.html"
        try:
            response = requests.get(url)
            if response.status_code == 200:
                logger.info(f"Found valid version: {version}")
                versions.append({
                    'version': version,
                    'url': url
                })
        except Exception:
            pass
    
    return versions

def update_trino_versions_in_db():
    """Update the database with Trino versions scraped from the website"""
    with app.app_context():
        # Get current versions in the database
        current_versions = set(v.version for v in TrinoVersion.query.all())
        logger.info(f"Current versions in database: {sorted(current_versions)}")
        
        # Scrape versions from the website
        scraped_versions = scrape_trino_releases()
        
        # Add versions that don't already exist
        versions_added = 0
        for version_info in scraped_versions:
            version = version_info['version']
            if version not in current_versions:
                # Add with placeholder data - in a real system you would
                # scrape additional details like release dates
                version_data = {
                    'version': version,
                    'release_date': None,  # We don't know the exact release date
                    'is_lts': False,       # Would need additional logic to identify LTS
                    'support_end_date': None,
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
        
        # Return list of all versions now in database
        all_versions = [v.version for v in TrinoVersion.query.order_by(TrinoVersion.version.desc()).all()]
        logger.info(f"All versions in database now: {all_versions}")
        return all_versions

if __name__ == "__main__":
    update_trino_versions_in_db()