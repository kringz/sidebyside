import os
from app import app, db
from models import QueryHistory, TrinoVersion, CatalogCompatibility
from config import get_default_config, save_config
from datetime import datetime, date

def initialize_database():
    with app.app_context():
        print("Creating database tables...")
        db.create_all()
        
        # Create default config if it doesn't exist
        if not os.path.exists('config/config.yaml'):
            print("Creating default configuration...")
            default_config = get_default_config()
            save_config(default_config)
        
        # Seed initial data if tables are empty
        if TrinoVersion.query.count() == 0:
            print("Seeding version data...")
            # Add some initial version data
            versions = [
                {
                    'version': '406',
                    'release_date': date(2023, 6, 2),
                    'is_lts': True,
                    'support_end_date': date(2024, 6, 2),
                    'release_notes_url': 'https://trino.io/docs/current/release/release-406.html'
                },
                {
                    'version': '405',
                    'release_date': date(2023, 5, 5),
                    'is_lts': False,
                    'support_end_date': None,
                    'release_notes_url': 'https://trino.io/docs/current/release/release-405.html'
                },
                {
                    'version': '404',
                    'release_date': date(2023, 4, 7),
                    'is_lts': False,
                    'support_end_date': None,
                    'release_notes_url': 'https://trino.io/docs/current/release/release-404.html'
                }
            ]
            
            for version_data in versions:
                version = TrinoVersion(**version_data)
                db.session.add(version)
            
            db.session.commit()
        
        if CatalogCompatibility.query.count() == 0:
            print("Seeding catalog compatibility data...")
            # Add some initial catalog compatibility data
            catalog_data = [
                {
                    'catalog_name': 'hive',
                    'min_version': '350',
                    'max_version': None,
                    'deprecated_in': None,
                    'removed_in': None,
                    'notes': 'Core connector widely supported across versions.'
                },
                {
                    'catalog_name': 'iceberg',
                    'min_version': '351',
                    'max_version': None,
                    'deprecated_in': None,
                    'removed_in': None,
                    'notes': 'Support improved significantly in versions 380+'
                },
                {
                    'catalog_name': 'delta-lake',
                    'min_version': '383',
                    'max_version': None,
                    'deprecated_in': None,
                    'removed_in': None,
                    'notes': 'Experimental in early versions, stable in 393+'
                }
            ]
            
            for catalog in catalog_data:
                compat = CatalogCompatibility(**catalog)
                db.session.add(compat)
            
            db.session.commit()
        
        print("Database initialization complete!")

if __name__ == "__main__":
    initialize_database()