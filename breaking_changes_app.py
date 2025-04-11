import os
import logging
from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
import re

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create the Flask application
class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
app = Flask(__name__)
# Set a secure secret key - change this in production!
app.secret_key = os.environ.get("SESSION_SECRET", "breaking-changes-secret-key")

# Configure the database - supports SQLite by default or use DATABASE_URL env var for other databases
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///instance/breaking_changes.db")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

# Define database models
class TrinoVersion(db.Model):
    """Model for tracking available Trino versions"""
    id = db.Column(db.Integer, primary_key=True)
    version = db.Column(db.String(20), unique=True, nullable=False)
    create_date = db.Column(db.DateTime, default=datetime.utcnow)

class VersionComparison(db.Model):
    """Model for caching version comparison results"""
    id = db.Column(db.Integer, primary_key=True)
    from_version = db.Column(db.String(20), nullable=False)
    to_version = db.Column(db.String(20), nullable=False)
    comparison_data = db.Column(db.Text, nullable=True)
    create_date = db.Column(db.DateTime, default=datetime.utcnow)
    expire_date = db.Column(db.DateTime, default=lambda: datetime.utcnow() + timedelta(days=30))

    __table_args__ = (
        db.UniqueConstraint('from_version', 'to_version', name='unique_version_comparison'),
    )

# Helper functions
def version_compare(v1, v2):
    """Compare two version strings"""
    def normalize(v):
        return [int(x) for x in v.split('.')]
    
    v1_parts = normalize(v1)
    v2_parts = normalize(v2)
    
    for i in range(max(len(v1_parts), len(v2_parts))):
        v1_part = v1_parts[i] if i < len(v1_parts) else 0
        v2_part = v2_parts[i] if i < len(v2_parts) else 0
        
        if v1_part < v2_part:
            return -1
        elif v1_part > v2_part:
            return 1
    
    return 0

def fetch_trino_changes(from_version, to_version):
    """Fetch breaking changes and feature differences from Trino website release notes"""
    changes = {
        'breaking_changes': [],
        'new_features': [],
        'fixed_issues': [],
        'performance_improvements': []
    }
    
    # Determine version order
    if version_compare(from_version, to_version) > 0:
        # Swap versions if from_version is newer than to_version
        logger.info(f"Swapping from_version {from_version} and to_version {to_version} to maintain chronological order")
        from_version, to_version = to_version, from_version

    # Check if we have a cached result
    cached_comparison = VersionComparison.query.filter_by(
        from_version=from_version, 
        to_version=to_version
    ).first()
    
    if cached_comparison and cached_comparison.expire_date > datetime.utcnow():
        logger.info(f"Using cached comparison data for {from_version} to {to_version}")
        if cached_comparison.comparison_data:
            import json
            return json.loads(cached_comparison.comparison_data)
        return changes

    # Get all versions between from_version and to_version
    try:
        versions = []
        for v in range(int(from_version), int(to_version) + 1):
            versions.append(str(v))
        
        logger.info(f"Fetching changes between versions: {from_version} and {to_version}")
        logger.info(f"Processing versions: {versions}")
        
        for version in versions:
            if version == from_version:
                continue  # Skip the starting version
                
            url = f"https://trino.io/docs/current/release/release-{version}.html"
            logger.info(f"Fetching release notes from {url}")
            
            try:
                response = requests.get(url, timeout=10)
                if response.status_code != 200:
                    logger.warning(f"Failed to fetch release notes for version {version}, status code: {response.status_code}")
                    continue
                    
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Extract breaking changes
                breaking_section = soup.find('h2', text=re.compile(r'breaking changes', re.IGNORECASE))
                if breaking_section:
                    breaking_list = []
                    current = breaking_section.find_next(['p', 'ul', 'h2'])
                    while current and current.name != 'h2':
                        if current.name == 'ul':
                            for li in current.find_all('li'):
                                breaking_list.append(li.get_text(strip=True))
                        elif current.name == 'p':
                            text = current.get_text(strip=True)
                            if text and not text.lower().startswith(('note:', 'warning:')):
                                breaking_list.append(text)
                        current = current.find_next(['p', 'ul', 'h2'])
                    
                    if breaking_list:
                        changes['breaking_changes'].append({
                            'version': version,
                            'items': breaking_list
                        })
                
                # Extract new features
                feature_section = soup.find(['h2', 'h3'], text=re.compile(r'new features|feature changes', re.IGNORECASE))
                if feature_section:
                    feature_list = []
                    current = feature_section.find_next(['p', 'ul', 'h2', 'h3'])
                    while current and current.name not in ['h2', 'h3']:
                        if current.name == 'ul':
                            for li in current.find_all('li'):
                                feature_list.append(li.get_text(strip=True))
                        current = current.find_next(['p', 'ul', 'h2', 'h3'])
                    
                    if feature_list:
                        changes['new_features'].append({
                            'version': version,
                            'items': feature_list
                        })
            
            except Exception as e:
                logger.error(f"Error processing version {version}: {str(e)}")
                continue
        
        # Cache the result
        import json
        cached_data = json.dumps(changes)
        
        # Check if we already have a record
        existing_comparison = VersionComparison.query.filter_by(
            from_version=from_version, 
            to_version=to_version
        ).first()
        
        if existing_comparison:
            existing_comparison.comparison_data = cached_data
            existing_comparison.expire_date = datetime.utcnow() + timedelta(days=30)
        else:
            new_comparison = VersionComparison(
                from_version=from_version,
                to_version=to_version,
                comparison_data=cached_data,
                expire_date=datetime.utcnow() + timedelta(days=30)
            )
            db.session.add(new_comparison)
        
        db.session.commit()
        logger.info(f"Cached comparison data for {from_version} to {to_version}")
        
        return changes
    except Exception as e:
        logger.error(f"Error fetching changes: {str(e)}")
        return changes

# Routes
@app.route('/')
def index():
    """Redirect root to breaking changes page"""
    return breaking_changes()

@app.route('/breaking_changes')
def breaking_changes():
    """Page for displaying breaking changes and feature comparisons between Trino versions"""
    # Directly define common versions to ensure they're always available
    common_versions = ['401', '406', '414', '424', '438', '442', '446', '451', '458', '465', '473', '474']
    
    # Ensure these versions exist in the database
    for version in common_versions:
        existing = TrinoVersion.query.filter_by(version=version).first()
        if not existing:
            db.session.add(TrinoVersion(version=version))
    
    try:
        db.session.commit()
    except:
        db.session.rollback()
        logger.warning("Failed to commit version additions, rolling back")
    
    # Get all versions from database
    versions = [v.version for v in TrinoVersion.query.order_by(TrinoVersion.version.desc()).all()]
    
    # If there's still no versions in the database for some reason, use the common ones directly
    if not versions:
        logger.warning("No versions found in database, using predefined list")
        versions = common_versions
    
    return render_template('breaking_changes.html', versions=versions)

@app.route('/api/compare_versions', methods=['POST'])
def compare_versions():
    """API endpoint to compare breaking changes and features between two Trino versions"""
    from_version = request.form.get('from_version', '')
    to_version = request.form.get('to_version', '')
    
    if not from_version or not to_version:
        return jsonify({'error': 'Both from_version and to_version are required'}), 400
    
    # Get the comparison data
    comparison_data = fetch_trino_changes(from_version, to_version)
    
    return jsonify({
        'breaking_changes': comparison_data.get('breaking_changes', []),
        'new_features': comparison_data.get('new_features', []),
        'fixed_issues': comparison_data.get('fixed_issues', []),
        'performance_improvements': comparison_data.get('performance_improvements', [])
    })

# Initialize database
def init_db():
    with app.app_context():
        db.create_all()
        logger.info("Database tables created")
        
        # Seed initial versions to ensure they're available
        common_versions = ['401', '406', '414', '424', '438', '442', '446', '451', '458', '465', '473', '474']
        
        for version in common_versions:
            existing = TrinoVersion.query.filter_by(version=version).first()
            if not existing:
                db.session.add(TrinoVersion(version=version))
        
        try:
            db.session.commit()
            logger.info("Database seeded with initial Trino versions")
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error seeding database: {str(e)}")

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)