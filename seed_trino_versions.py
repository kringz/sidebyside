#!/usr/bin/env python3
"""
Script to seed the database with Trino versions
This can be run independently or included in your application startup
"""
from main import app
from models import db, TrinoVersion
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def seed_trino_versions():
    """Seed the database with all Trino versions if they don't exist"""
    with app.app_context():
        # Get existing versions
        existing_versions = set(v.version for v in TrinoVersion.query.all())
        
        # All versions to ensure are in the database
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
            "414", "413", "412", "411", "410", "409", "408", "407",
            # Older versions
            "406", "405", "404", "403", "402", "401", "400", "399", "398",
            "397", "396", "395", "394", "393", "392", "391", "390", "389"
        ]
        
        # Check if we need to add any versions
        missing_versions = set(all_versions) - existing_versions
        
        if missing_versions:
            logger.info(f"Found {len(missing_versions)} missing Trino versions to add")
            
            # Add missing versions
            for version in missing_versions:
                new_version = TrinoVersion(
                    version=version,
                    release_notes_url=f"https://trino.io/docs/current/release/release-{version}.html"
                )
                db.session.add(new_version)
                logger.info(f"Adding version {version}")
            
            # Commit changes
            db.session.commit()
            logger.info(f"Added {len(missing_versions)} new Trino versions to the database")
        else:
            logger.info("No new versions to add - database already contains all versions")
        
        # Log all versions
        all_versions_in_db = [v.version for v in TrinoVersion.query.order_by(TrinoVersion.version.desc()).all()]
        logger.info(f"All versions in database: {all_versions_in_db}")
        
        return all_versions_in_db

if __name__ == "__main__":
    seed_trino_versions()