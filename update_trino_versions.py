#!/usr/bin/env python3
"""
Script to update the database with all available Trino versions
"""
from main import app
from models import db, TrinoVersion
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def update_trino_versions():
    """Update the database with all available Trino versions"""
    with app.app_context():
        # All versions from the list provided
        all_versions = [
            # 2025 versions
            "474", "473", "472", "471", "470", "469",
            # 2024 versions
            "468", "467", "466", "465", "464", "463", "462", "461", "460",
            "459", "458", "457", "456", "455", "454", "453", "452", "451",
            "450", "449", "448", "447", "446", "445", "444", "443", "442",
            "441", "440", "439", "438", "437", "436", "435", "434", "433",
            "432", "431", "430", "429", "428", "427", "426", "425", "424",
            "423", "422", "421", "420", "419", "418", "417", "416", "415",
            "414", "413", "412", "411", "410",
            # Existing versions we already have in our database (for completeness)
            "406", "405", "404", "403", "402", "401", "398", "393", "389"
        ]
        
        # Get existing versions
        existing_versions = set(v.version for v in TrinoVersion.query.all())
        logger.info(f"Current versions in DB: {sorted(existing_versions)}")
        
        # Add versions that don't exist yet
        added_count = 0
        for version in all_versions:
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
        all_versions_in_db = [v.version for v in TrinoVersion.query.order_by(TrinoVersion.version.desc()).all()]
        logger.info(f"All versions now: {all_versions_in_db}")
        
        return all_versions_in_db

if __name__ == "__main__":
    update_trino_versions()