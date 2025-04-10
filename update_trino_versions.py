#!/usr/bin/env python3
"""
Script to update the Trino versions in the database with newer releases
"""
from main import app
from models import db, TrinoVersion
from datetime import date
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def add_new_versions():
    """Add newer Trino versions to the database"""
    with app.app_context():
        # Get current versions in the database
        current_versions = set(v.version for v in TrinoVersion.query.all())
        logger.info(f"Current versions in database: {sorted(current_versions)}")
        
        # Define newer versions to add
        # Format: version, release_date, is_lts, support_end_date, release_notes_url
        new_versions = [
            {
                'version': '474',
                'release_date': date(2024, 3, 29),  # Estimated - replace with actual date
                'is_lts': False,
                'support_end_date': None,
                'release_notes_url': 'https://trino.io/docs/current/release/release-474.html'
            },
            {
                'version': '440',
                'release_date': date(2023, 12, 15),  # Estimated - replace with actual date
                'is_lts': False,
                'support_end_date': None,
                'release_notes_url': 'https://trino.io/docs/current/release/release-440.html'
            },
            {
                'version': '430',
                'release_date': date(2023, 10, 20),  # Estimated - replace with actual date
                'is_lts': False,
                'support_end_date': None,
                'release_notes_url': 'https://trino.io/docs/current/release/release-430.html'
            },
            {
                'version': '420',
                'release_date': date(2023, 9, 1),  # Estimated - replace with actual date
                'is_lts': False,
                'support_end_date': None,
                'release_notes_url': 'https://trino.io/docs/current/release/release-420.html'
            },
            {
                'version': '410',
                'release_date': date(2023, 7, 15),  # Estimated - replace with actual date
                'is_lts': False,
                'support_end_date': None,
                'release_notes_url': 'https://trino.io/docs/current/release/release-410.html'
            }
        ]
        
        # Add versions that don't already exist
        versions_added = 0
        for version_data in new_versions:
            if version_data['version'] not in current_versions:
                version = TrinoVersion(**version_data)
                db.session.add(version)
                versions_added += 1
                logger.info(f"Adding version {version_data['version']}")
        
        # Commit changes if any versions were added
        if versions_added > 0:
            db.session.commit()
            logger.info(f"Added {versions_added} new Trino versions to the database")
        else:
            logger.info("No new versions to add")

if __name__ == "__main__":
    add_new_versions()