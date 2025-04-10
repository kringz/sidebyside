"""
Script to create the Version Comparison table for caching breaking changes results.
This avoids having to scrape the Trino website on each request.
"""
import sys
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import app and db
try:
    from app import app, db
    from models import VersionComparison
except ImportError as e:
    logger.error(f"Error importing application modules: {str(e)}")
    sys.exit(1)

def create_version_comparison_table():
    """Create the VersionComparison table if it doesn't exist"""
    with app.app_context():
        try:
            # Check if table exists by querying for any records
            existing_records = VersionComparison.query.count()
            logger.info(f"Found {existing_records} existing version comparison records")
            
            # Create the table if it doesn't exist
            db.create_all()
            logger.info("Successfully created or verified VersionComparison table")
            
            return True
        except Exception as e:
            logger.error(f"Error creating VersionComparison table: {str(e)}")
            return False

if __name__ == "__main__":
    if create_version_comparison_table():
        logger.info("Version comparison table setup complete")
    else:
        logger.error("Failed to set up version comparison table")
        sys.exit(1)