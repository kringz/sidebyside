#!/usr/bin/env python3
"""
Script to directly add version 474 and other recent versions to the database
"""
from main import app
from models import db, TrinoVersion
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def add_version_474():
    """Add version 474 and other recent versions to the database"""
    with app.app_context():
        # Versions to add
        versions_to_add = ["474", "470", "460", "450", "440", "430", "420", "410"]
        
        # Get existing versions
        existing_versions = set(v.version for v in TrinoVersion.query.all())
        logger.info(f"Current versions in DB: {existing_versions}")
        
        # Add versions that don't exist yet
        added_count = 0
        for version in versions_to_add:
            if version not in existing_versions:
                new_version = TrinoVersion(
                    version=version,
                    release_notes_url=f"https://trino.io/docs/current/release/release-{version}.html"
                )
                db.session.add(new_version)
                logger.info(f"Adding version {version}")
                added_count += 1
        
        # Save changes
        if added_count > 0:
            db.session.commit()
            logger.info(f"Added {added_count} new versions")
        else:
            logger.info("No new versions added")
        
        # Get updated list of versions
        all_versions = [v.version for v in TrinoVersion.query.order_by(TrinoVersion.version.desc()).all()]
        logger.info(f"All versions now: {all_versions}")
        
        return all_versions

if __name__ == "__main__":
    add_version_474()