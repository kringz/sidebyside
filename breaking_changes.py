from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import traceback
import logging
import requests
import re
import sys
from distutils.version import LooseVersion

# Configure logging
logger = logging.getLogger(__name__)

# Set up BeautifulSoup handling without direct imports
BEAUTIFULSOUP_AVAILABLE = False

# Define dummy BeautifulSoup class for when the actual package is not available
class DummyBeautifulSoup:
    def __init__(self, *args, **kwargs):
        pass
        
    def find(self, *args, **kwargs):
        return None
        
    def find_next(self, *args, **kwargs):
        return None
        
    def find_all(self, *args, **kwargs):
        return []
        
    def get_text(self, *args, **kwargs):
        return ""

# Check if BeautifulSoup is available without importing it directly
try:
    # Try to import BeautifulSoup to check if it's available
    import bs4
    BEAUTIFULSOUP_AVAILABLE = True
    logger.info("BeautifulSoup4 is available for web scraping.")
    # Immediately remove it from imported modules to prevent conflicts
    if 'bs4' in sys.modules:
        del sys.modules['bs4']
except ImportError:
    logger.warning("BeautifulSoup4 is not installed. Web scraping functionality will be limited.")

from models import db, BreakingChange, FeatureChange, TrinoVersion

# Configure logging
logger = logging.getLogger(__name__)

def register_breaking_changes_routes(app):
    @app.route('/breaking_changes')
    def breaking_changes():
        """Page for displaying breaking changes and feature comparisons between Trino versions"""
        # Get all available versions
        versions = TrinoVersion.query.order_by(TrinoVersion.version.desc()).all()
        config = app.config.get('CURRENT_CONFIG', {})
        
        # Set default comparison to be between the two configured clusters
        cluster1_version = config.get('cluster1', {}).get('version', '406')
        cluster2_version = config.get('cluster2', {}).get('version', '405')
        
        return render_template('breaking_changes.html',
                            available_versions=versions,
                            cluster1_version=cluster1_version,
                            cluster2_version=cluster2_version)


    @app.route('/compare_versions', methods=['POST'])
    def compare_versions():
        """API endpoint to compare breaking changes and features between two Trino versions"""
        from_version = request.form.get('from_version')
        to_version = request.form.get('to_version')
        
        if not from_version or not to_version:
            return jsonify({
                'success': False,
                'message': 'Both from_version and to_version are required'
            })
        
        try:
            # Convert version strings to LooseVersion for proper comparison
            from_v = LooseVersion(from_version)
            to_v = LooseVersion(to_version)
            
            # Ensure from_version is less than to_version
            if from_v > to_v:
                from_version, to_version = to_version, from_version
                from_v, to_v = to_v, from_v
            
            # Query the database for breaking changes between these versions
            breaking_changes = BreakingChange.query.filter(
                BreakingChange.version >= from_version,
                BreakingChange.version <= to_version
            ).order_by(BreakingChange.version.asc()).all()
            
            # Query for feature changes between these versions
            feature_changes = FeatureChange.query.filter(
                FeatureChange.version >= from_version,
                FeatureChange.version <= to_version
            ).order_by(FeatureChange.version.asc()).all()
            
            # Organize the feature changes by type
            new_features = [f for f in feature_changes if f.change_type == 'new']
            deprecated_removed = [f for f in feature_changes if f.change_type in ('deprecated', 'removed')]
            other_changes = [f for f in feature_changes if f.change_type not in ('new', 'deprecated', 'removed')]
            
            # If we don't have data in the database for these versions, fetch it from the Trino website
            if not breaking_changes and not feature_changes:
                # Fetch data from Trino website
                changes_data = fetch_trino_changes(from_version, to_version)
                
                # Store the fetched data in the database
                for change in changes_data.get('breaking_changes', []):
                    db_change = BreakingChange(
                        version=change['version'],
                        title=change['title'],
                        description=change['description'],
                        workaround=change.get('workaround'),
                        component=change.get('component'),
                        impacts_performance=change.get('impacts_performance', False),
                        impacts_compatibility=True
                    )
                    db.session.add(db_change)
                    
                for feature in changes_data.get('new_features', []):
                    db_feature = FeatureChange(
                        version=feature['version'],
                        title=feature['title'],
                        description=feature['description'],
                        change_type='new',
                        component=feature.get('component'),
                        example=feature.get('example')
                    )
                    db.session.add(db_feature)
                    
                for item in changes_data.get('deprecated_removed', []):
                    db_item = FeatureChange(
                        version=item['version'],
                        title=item.get('name', 'Unnamed feature'),
                        description=item['description'],
                        change_type=item['status'].lower(),
                        alternative=item.get('alternative')
                    )
                    db.session.add(db_item)
                    
                for change in changes_data.get('other_changes', []):
                    db_change = FeatureChange(
                        version=change['version'],
                        title=change['title'],
                        description=change['description'],
                        change_type='modified',
                        component=change.get('category')
                    )
                    db.session.add(db_change)
                    
                db.session.commit()
                
                # Use the fetched data directly in the response
                return jsonify(changes_data)
            
            # Format the database results for the response
            result = {
                'breaking_changes': [
                    {
                        'version': change.version,
                        'title': change.title,
                        'description': change.description,
                        'workaround': change.workaround,
                        'component': change.component,
                        'impacts_performance': change.impacts_performance,
                        'impacts_compatibility': change.impacts_compatibility
                    }
                    for change in breaking_changes
                ],
                'new_features': [
                    {
                        'version': feature.version,
                        'title': feature.title,
                        'description': feature.description,
                        'component': feature.component,
                        'example': feature.example
                    }
                    for feature in new_features
                ],
                'deprecated_removed': [
                    {
                        'name': feature.title,
                        'status': feature.change_type.capitalize(),
                        'version': feature.version,
                        'description': feature.description,
                        'alternative': feature.alternative
                    }
                    for feature in deprecated_removed
                ],
                'other_changes': [
                    {
                        'version': feature.version,
                        'title': feature.title,
                        'description': feature.description,
                        'category': feature.component
                    }
                    for feature in other_changes
                ]
            }
            
            return jsonify(result)
            
        except Exception as e:
            logger.error(f"Error comparing versions: {str(e)}")
            logger.error(traceback.format_exc())
            return jsonify({
                'success': False,
                'message': f"Error comparing versions: {str(e)}"
            })


def fetch_trino_changes(from_version, to_version):
    """Fetch breaking changes and feature differences from Trino website release notes"""
    try:
        # If BeautifulSoup is not available, return an empty result with a message
        if not BEAUTIFULSOUP_AVAILABLE:
            logger.warning("BeautifulSoup4 is not installed. Cannot scrape Trino release notes.")
            return {
                'breaking_changes': [{
                    'version': 'N/A',
                    'title': 'Web scraping functionality unavailable',
                    'description': 'The BeautifulSoup4 library is required for scraping release notes. Please install it with pip: pip install beautifulsoup4',
                    'workaround': 'Install BeautifulSoup4 or manually check release notes at https://trino.io/docs/current/release/',
                    'component': 'System',
                    'impacts_performance': False
                }],
                'new_features': [],
                'deprecated_removed': [],
                'other_changes': []
            }
        
        # Base URL for Trino release notes
        base_url = "https://trino.io/docs/current/release"
        
        # Find all version numbers between from_version and to_version
        # This could be optimized with a more direct approach for known versions
        versions = []
        
        # For demo purposes, handle some common versions
        for major in range(3, 5):  # 300-499
            for minor in range(0, 10):
                version = f"{major}{minor}0"
                if LooseVersion(from_version) <= LooseVersion(version) <= LooseVersion(to_version):
                    versions.append(version)
        
        # Add specific versions not captured by the pattern above
        specific_versions = ["351", "352", "353", "354", "355", "356", "357", "358", "359", 
                        "360", "361", "362", "363", "364", "365", "366", "367", "368", "369",
                        "370", "371", "372", "373", "374", "375", "376", "377", "378", "379",
                        "380", "381", "382", "383", "384", "385", "386", "387", "388", "389",
                        "390", "391", "392", "393", "394", "395", "396", "397", "398", "399",
                        "400", "401", "402", "403", "404", "405", "406", "407", "408", "409",
                        "410", "411", "412", "413", "414", "415", "416", "417", "418", "419"]
        
        for version in specific_versions:
            if LooseVersion(from_version) <= LooseVersion(version) <= LooseVersion(to_version):
                if version not in versions:
                    versions.append(version)
        
        # Sort versions
        versions.sort(key=lambda x: LooseVersion(x))
        
        # Result structure
        result = {
            'breaking_changes': [],
            'new_features': [],
            'deprecated_removed': [],
            'other_changes': []
        }
        
        # Process each version
        for version in versions:
            try:
                # Form the URL for this version's release notes
                release_url = f"{base_url}/{version}.html"
                response = requests.get(release_url, timeout=10)
                
                if response.status_code == 200:
                    # Parse the HTML content - import BeautifulSoup only when needed
                    try:
                        from bs4 import BeautifulSoup
                        soup = BeautifulSoup(response.text, 'html.parser')
                    except ImportError:
                        # Use dummy implementation if import fails
                        soup = DummyBeautifulSoup(response.text, 'html.parser')
                    
                    # Find breaking changes section
                    breaking_changes_section = soup.find('h2', string=re.compile('Breaking Changes', re.I))
                    if breaking_changes_section:
                        # Find all list items under breaking changes
                        ul = breaking_changes_section.find_next('ul')
                        if ul:
                            for li in ul.find_all('li', recursive=False):
                                title = li.get_text().strip()
                                # Extract the first sentence as the title and the rest as description
                                title_parts = title.split('.', 1)
                                if len(title_parts) > 1:
                                    title, description = title_parts[0] + '.', title_parts[1].strip()
                                else:
                                    title, description = title, ""
                                
                                result['breaking_changes'].append({
                                    'version': version,
                                    'title': title,
                                    'description': description,
                                    'workaround': None
                                })
                    
                    # Find new features section
                    new_features_section = soup.find('h2', string=re.compile('New Features', re.I))
                    if new_features_section:
                        # Find all list items under new features
                        ul = new_features_section.find_next('ul')
                        if ul:
                            for li in ul.find_all('li', recursive=False):
                                title = li.get_text().strip()
                                # Extract the first sentence as the title and the rest as description
                                title_parts = title.split('.', 1)
                                if len(title_parts) > 1:
                                    title, description = title_parts[0] + '.', title_parts[1].strip()
                                else:
                                    title, description = title, ""
                                
                                result['new_features'].append({
                                    'version': version,
                                    'title': title,
                                    'description': description,
                                    'example': None
                                })
                    
                    # Find deprecated/removed features section
                    deprecated_section = soup.find('h2', string=re.compile('(Deprecated|Removed) Features', re.I))
                    if deprecated_section:
                        # Find all list items under deprecated/removed features
                        ul = deprecated_section.find_next('ul')
                        if ul:
                            for li in ul.find_all('li', recursive=False):
                                text = li.get_text().strip()
                                
                                # Determine if it's deprecated or removed
                                status = "Deprecated" if "deprecated" in text.lower() else "Removed"
                                
                                # Try to extract the feature name
                                name_match = re.search(r'`([^`]+)`', text)
                                name = name_match.group(1) if name_match else "Feature"
                                
                                result['deprecated_removed'].append({
                                    'name': name,
                                    'status': status,
                                    'version': version,
                                    'description': text,
                                    'alternative': None
                                })
                    
                    # Other changes: bug fixes, performance improvements, etc.
                    for section_title in ['Bug Fixes', 'Performance Improvements', 'General Changes']:
                        section = soup.find('h2', string=re.compile(section_title, re.I))
                        if section:
                            ul = section.find_next('ul')
                            if ul:
                                for li in ul.find_all('li', recursive=False):
                                    title = li.get_text().strip()
                                    # Extract the first sentence as the title and the rest as description
                                    title_parts = title.split('.', 1)
                                    if len(title_parts) > 1:
                                        title, description = title_parts[0] + '.', title_parts[1].strip()
                                    else:
                                        title, description = title, ""
                                    
                                    result['other_changes'].append({
                                        'version': version,
                                        'title': title,
                                        'description': description,
                                        'category': section_title
                                    })
            
            except Exception as e:
                logger.error(f"Error processing version {version}: {str(e)}")
                continue
        
        return result
        
    except Exception as e:
        logger.error(f"Error fetching Trino changes: {str(e)}")
        return {
            'breaking_changes': [],
            'new_features': [],
            'deprecated_removed': [],
            'other_changes': []
        }