import os
import logging
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import yaml
import time
import traceback

from config import load_config, save_config, get_default_config
from docker_manager import DockerManager
from trino_client import TrinoClient
from models import db, QueryHistory, TrinoVersion, CatalogCompatibility, BreakingChange, FeatureChange
from datetime import datetime, date
import requests
from bs4 import BeautifulSoup

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Initialize Flask application
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev_secret_key")

# Configure the database
DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL:
    app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_recycle": 300,
        "pool_pre_ping": True,
    }
    logger.info(f"Database URL configured: {DATABASE_URL[:10]}...")
else:
    # Use SQLite as fallback
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///trino_comparison.db"
    logger.info("Using SQLite database as fallback")

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Initialize the database
db.init_app(app)

# Load configuration to get Docker settings
config = load_config()

# Initialize Docker manager with custom settings if available
docker_settings = config.get('docker', {})
docker_manager = DockerManager(
    socket_path=docker_settings.get('socket_path', None),
    timeout=int(docker_settings.get('timeout', 30)),
    trino_connect_host=docker_settings.get('trino_connect_host', 'localhost')
)

# Check Docker availability
docker_available = docker_manager.docker_available
if not docker_available:
    logger.warning("Docker is not available. Running in demo mode.")

# Initialize Trino clients (will be set up when clusters are started)
trino_clients = {
    "cluster1": None,
    "cluster2": None
}

@app.route('/')
def index():
    """Main page with cluster status and management and catalog configuration"""
    config = load_config()
    cluster1_status = docker_manager.get_container_status(config['cluster1']['container_name'])
    cluster2_status = docker_manager.get_container_status(config['cluster2']['container_name'])
    
    # Merged the catalog_config_page and index page
    return render_template('index.html', 
                           config=config, 
                           cluster1_status=cluster1_status,
                           cluster2_status=cluster2_status,
                           docker_available=docker_available)

@app.route('/pull_trino_images', methods=['POST'])
def pull_trino_images():
    """Pull Trino Docker images in advance"""
    try:
        if not docker_available:
            return jsonify({
                'success': False, 
                'message': 'Docker is not available in this environment. Image pulling is disabled.'
            })
            
        config = load_config()
        versions = [config['cluster1']['version'], config['cluster2']['version']]
        
        results = {}
        for version in versions:
            if version not in results:
                success = docker_manager.pull_trino_image(version)
                results[version] = success
        
        if all(results.values()):
            return jsonify({
                'success': True, 
                'message': f'Successfully pulled Trino images: {", ".join(versions)}'
            })
        else:
            failed = [v for v, success in results.items() if not success]
            return jsonify({
                'success': False, 
                'message': f'Failed to pull some Trino images: {", ".join(failed)}'
            })
            
    except Exception as e:
        logger.error(f"Error pulling Trino images: {str(e)}")
        return jsonify({
            'success': False, 
            'message': f'Error pulling Trino images: {str(e)}'
        })

@app.route('/save_config', methods=['POST'])
def save_configuration():
    """Save cluster configuration"""
    try:
        config = load_config()
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        # Check if this is a catalog-only form submission or full config
        if 'cluster1_version' in request.form:
            # Track if versions changed
            versions_changed = (
                config['cluster1']['version'] != request.form.get('cluster1_version') or
                config['cluster2']['version'] != request.form.get('cluster2_version')
            )
            
            # Update Docker configuration
            if 'docker' not in config:
                config['docker'] = {}
                
            config['docker']['trino_connect_host'] = request.form.get('docker_trino_connect_host', 'localhost')
            config['docker']['socket_path'] = request.form.get('docker_socket_path', '')
            config['docker']['auto_pull_images'] = 'docker_auto_pull_images' in request.form
            config['docker']['timeout'] = int(request.form.get('docker_timeout', 30))
            
            # Update cluster configurations (full form)
            config['cluster1']['version'] = request.form.get('cluster1_version')
            config['cluster1']['port'] = int(request.form.get('cluster1_port'))
            config['cluster1']['container_name'] = request.form.get('cluster1_container_name')
            
            config['cluster2']['version'] = request.form.get('cluster2_version')
            config['cluster2']['port'] = int(request.form.get('cluster2_port'))
            config['cluster2']['container_name'] = request.form.get('cluster2_container_name')
            
            # Automatically pull images if versions changed and Docker is available
            if versions_changed and docker_available and config['docker'].get('auto_pull_images', True):
                logger.info("Versions changed, automatically pulling images...")
                for version in [config['cluster1']['version'], config['cluster2']['version']]:
                    docker_manager.pull_trino_image(version)
        
        # Save catalog configurations (both forms include this)
        enabled_catalogs = []
        for catalog in ['hive', 'iceberg', 'delta-lake', 'mysql', 'mariadb', 'postgres', 'sqlserver', 'db2', 'clickhouse', 'pinot', 'elasticsearch']:
            # Check both methods of enabling catalogs (checkbox name or direct name)
            if catalog in request.form or catalog in request.form.getlist('enabled_catalogs'):
                enabled_catalogs.append(catalog)
                config['catalogs'][catalog]['enabled'] = True
            else:
                config['catalogs'][catalog]['enabled'] = False
        
        save_config(config)
        
        if is_ajax:
            # Return JSON response for AJAX request
            return jsonify({'success': True, 'message': 'Configuration saved successfully!'})
        else:
            # Return regular response with flash message
            flash('Configuration saved successfully!', 'success')
            return redirect(url_for('index'))
            
    except Exception as e:
        logger.error(f"Error saving configuration: {str(e)}")
        
        if is_ajax:
            return jsonify({'success': False, 'message': f'Error saving configuration: {str(e)}'})
        else:
            flash(f'Error saving configuration: {str(e)}', 'danger')
            return redirect(url_for('index'))

@app.route('/reset_config', methods=['POST'])
def reset_config():
    """Reset configuration to defaults"""
    try:
        default_config = get_default_config()
        save_config(default_config)
        flash('Configuration reset to defaults!', 'success')
    except Exception as e:
        logger.error(f"Error resetting configuration: {str(e)}")
        flash(f'Error resetting configuration: {str(e)}', 'danger')
    
    return redirect(url_for('index'))

@app.route('/start_clusters', methods=['POST'])
def start_clusters():
    """Start both Trino clusters"""
    try:
        config = load_config()
        
        if not docker_available:
            flash('Docker is not available in this environment. Cluster startup is disabled.', 'warning')
            return redirect(url_for('index'))
            
        # First, ensure images are pulled to avoid timeouts
        flash('Preparing Trino images...', 'info')
        
        versions = [config['cluster1']['version'], config['cluster2']['version']]
        image_results = {}
        
        # Pre-pull all necessary images
        for version in versions:
            if version not in image_results:
                logger.info(f"Ensuring Trino image {version} is pulled...")
                success = docker_manager.pull_trino_image(version)
                image_results[version] = success
                if success:
                    flash(f"Trino image version {version} ready", 'info')
                else:
                    flash(f"Failed to pull Trino image version {version}", 'warning')
        
        # Start first cluster
        flash(f"Starting Trino cluster 1 (version {config['cluster1']['version']})...", 'info')
        docker_manager.start_trino_cluster(
            config['cluster1']['container_name'],
            config['cluster1']['version'],
            config['cluster1']['port'],
            config['catalogs']
        )
        
        # Start second cluster
        flash(f"Starting Trino cluster 2 (version {config['cluster2']['version']})...", 'info')
        docker_manager.start_trino_cluster(
            config['cluster2']['container_name'],
            config['cluster2']['version'],
            config['cluster2']['port'],
            config['catalogs']
        )
        
        # Wait for clusters to initialize
        flash('Waiting for clusters to initialize...', 'info')
        time.sleep(5)
        
        # Initialize Trino clients using the configured host
        trino_host = config.get('docker', {}).get('trino_connect_host', 'localhost')
        trino_clients['cluster1'] = TrinoClient(
            host=trino_host,
            port=config['cluster1']['port'],
            user='trino',
            cluster_name=f"Trino {config['cluster1']['version']}"
        )
        
        trino_clients['cluster2'] = TrinoClient(
            host=trino_host,
            port=config['cluster2']['port'],
            user='trino',
            cluster_name=f"Trino {config['cluster2']['version']}"
        )
        
        flash('Both Trino clusters started successfully!', 'success')
    except Exception as e:
        logger.error(f"Error starting clusters: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f'Error starting clusters: {str(e)}', 'danger')
    
    return redirect(url_for('index'))

@app.route('/stop_clusters', methods=['POST'])
def stop_clusters():
    """Stop both Trino clusters"""
    try:
        config = load_config()
        
        docker_manager.stop_trino_cluster(config['cluster1']['container_name'])
        docker_manager.stop_trino_cluster(config['cluster2']['container_name'])
        
        # Reset Trino clients
        trino_clients['cluster1'] = None
        trino_clients['cluster2'] = None
        
        flash('Both Trino clusters stopped successfully!', 'success')
    except Exception as e:
        logger.error(f"Error stopping clusters: {str(e)}")
        flash(f'Error stopping clusters: {str(e)}', 'danger')
    
    return redirect(url_for('index'))

@app.route('/restart_clusters', methods=['POST'])
def restart_clusters():
    """Restart both Trino clusters"""
    try:
        stop_clusters()
        time.sleep(2)
        start_clusters()
        flash('Both Trino clusters restarted successfully!', 'success')
    except Exception as e:
        logger.error(f"Error restarting clusters: {str(e)}")
        flash(f'Error restarting clusters: {str(e)}', 'danger')
    
    return redirect(url_for('index'))

@app.route('/query')
def query_page():
    """Page for executing queries against clusters"""
    config = load_config()
    cluster1_status = docker_manager.get_container_status(config['cluster1']['container_name'])
    cluster2_status = docker_manager.get_container_status(config['cluster2']['container_name'])
    
    # Get list of catalogs
    catalogs = [catalog for catalog, settings in config['catalogs'].items() if settings['enabled']]
    
    # Check if a query is provided in the URL (e.g., when re-running a query from history)
    pre_populated_query = request.args.get('query', '')
    
    return render_template('query.html', 
                           config=config,
                           catalogs=catalogs,
                           cluster1_status=cluster1_status,
                           cluster2_status=cluster2_status,
                           docker_available=docker_available,
                           pre_populated_query=pre_populated_query)

@app.route('/run_query', methods=['POST'])
def run_query():
    """Execute a query on both clusters and compare results"""
    query = request.form.get('query')
    config = load_config()
    
    if not query:
        flash('Please enter a query', 'warning')
        return redirect(url_for('query_page'))
    
    if not docker_available:
        flash('Docker is not available in this environment. Query execution is disabled.', 'warning')
        return redirect(url_for('query_page'))
        
    try:
        results = {}
        errors = {}
        timing = {}
        
        # Create a new query history record
        query_history = QueryHistory(query_text=query)
        
        # Only run query against clusters that are running
        for cluster_name in ['cluster1', 'cluster2']:
            container_name = config[cluster_name]['container_name']
            if docker_manager.get_container_status(container_name) == 'running':
                if trino_clients[cluster_name]:
                    try:
                        start_time = time.time()
                        query_results = trino_clients[cluster_name].execute_query(query)
                        end_time = time.time()
                        
                        results[cluster_name] = query_results
                        timing[cluster_name] = end_time - start_time
                    except Exception as e:
                        logger.error(f"Error executing query on {cluster_name}: {str(e)}")
                        errors[cluster_name] = str(e)
                else:
                    errors[cluster_name] = "Trino client not initialized"
            else:
                errors[cluster_name] = "Cluster not running"
        
        # Save the results to the database if we have DATABASE_URL configured
        if DATABASE_URL:
            try:
                query_history.save_results(results, timing, errors)
                db.session.add(query_history)
                db.session.commit()
                logger.info(f"Saved query history for query: {query[:50]}...")
            except Exception as e:
                logger.error(f"Error saving query history: {str(e)}")
                db.session.rollback()
        
        return render_template('comparison.html',
                               query=query,
                               results=results,
                               errors=errors,
                               timing=timing,
                               config=config,
                               docker_available=docker_available)
    
    except Exception as e:
        logger.error(f"Error during query execution: {str(e)}")
        flash(f'Error during query execution: {str(e)}', 'danger')
        return redirect(url_for('query_page'))

@app.route('/history')
def query_history():
    """Page for viewing query history"""
    if not DATABASE_URL:
        flash('Database functionality is disabled.', 'warning')
        return redirect(url_for('index'))
        
    history = QueryHistory.query.order_by(QueryHistory.execution_time.desc()).all()
    return render_template('history.html', 
                           history=history,
                           docker_available=docker_available)

@app.route('/catalog_config')
def catalog_config_page():
    """Page for configuring catalogs"""
    config = load_config()
    return render_template('catalog_config.html', config=config, docker_available=docker_available)

@app.route('/save_catalog_config', methods=['POST'])
def save_catalog_config():
    """Save catalog configurations"""
    try:
        config = load_config()
        
        for catalog in config['catalogs']:
            if catalog in request.form:
                config['catalogs'][catalog]['enabled'] = True
                
                # Save catalog-specific configurations
                if catalog == 'hive' or catalog == 'iceberg' or catalog == 'delta-lake':
                    config['catalogs'][catalog]['metastore_host'] = request.form.get(f'{catalog}_metastore_host', 'localhost')
                    config['catalogs'][catalog]['metastore_port'] = request.form.get(f'{catalog}_metastore_port', '9083')
                elif catalog == 'mysql' or catalog == 'mariadb':
                    config['catalogs'][catalog]['host'] = request.form.get(f'{catalog}_host', 'localhost')
                    config['catalogs'][catalog]['port'] = request.form.get(f'{catalog}_port', '3306')
                    config['catalogs'][catalog]['user'] = request.form.get(f'{catalog}_user', 'root')
                    config['catalogs'][catalog]['password'] = request.form.get(f'{catalog}_password', '')
                elif catalog == 'postgres':
                    config['catalogs'][catalog]['host'] = request.form.get(f'{catalog}_host', 'localhost')
                    config['catalogs'][catalog]['port'] = request.form.get(f'{catalog}_port', '5432')
                    config['catalogs'][catalog]['database'] = request.form.get(f'{catalog}_database', 'postgres')
                    config['catalogs'][catalog]['user'] = request.form.get(f'{catalog}_user', 'postgres')
                    config['catalogs'][catalog]['password'] = request.form.get(f'{catalog}_password', '')
                elif catalog == 'sqlserver':
                    config['catalogs'][catalog]['host'] = request.form.get(f'{catalog}_host', 'localhost')
                    config['catalogs'][catalog]['port'] = request.form.get(f'{catalog}_port', '1433')
                    config['catalogs'][catalog]['database'] = request.form.get(f'{catalog}_database', 'master')
                    config['catalogs'][catalog]['user'] = request.form.get(f'{catalog}_user', 'sa')
                    config['catalogs'][catalog]['password'] = request.form.get(f'{catalog}_password', '')
                elif catalog == 'db2':
                    config['catalogs'][catalog]['host'] = request.form.get(f'{catalog}_host', 'localhost')
                    config['catalogs'][catalog]['port'] = request.form.get(f'{catalog}_port', '50000')
                    config['catalogs'][catalog]['database'] = request.form.get(f'{catalog}_database', 'sample')
                    config['catalogs'][catalog]['user'] = request.form.get(f'{catalog}_user', 'db2inst1')
                    config['catalogs'][catalog]['password'] = request.form.get(f'{catalog}_password', '')
                elif catalog == 'clickhouse':
                    config['catalogs'][catalog]['host'] = request.form.get(f'{catalog}_host', 'localhost')
                    config['catalogs'][catalog]['port'] = request.form.get(f'{catalog}_port', '8123')
                    config['catalogs'][catalog]['user'] = request.form.get(f'{catalog}_user', 'default')
                    config['catalogs'][catalog]['password'] = request.form.get(f'{catalog}_password', '')
                elif catalog == 'pinot':
                    config['catalogs'][catalog]['host'] = request.form.get(f'{catalog}_host', 'localhost')
                    config['catalogs'][catalog]['port'] = request.form.get(f'{catalog}_port', '9000')
                elif catalog == 'elasticsearch':
                    config['catalogs'][catalog]['host'] = request.form.get(f'{catalog}_host', 'localhost')
                    config['catalogs'][catalog]['port'] = request.form.get(f'{catalog}_port', '9200')
            else:
                config['catalogs'][catalog]['enabled'] = False
        
        save_config(config)
        flash('Catalog configuration saved!', 'success')
    except Exception as e:
        logger.error(f"Error saving catalog configuration: {str(e)}")
        flash(f'Error saving catalog configuration: {str(e)}', 'danger')
    
    return redirect(url_for('index'))

@app.route('/version_compatibility')
def version_compatibility():
    """Page for displaying Trino version compatibility information"""
    if not DATABASE_URL:
        flash('Database functionality is disabled.', 'warning')
        return redirect(url_for('index'))
    
    versions = TrinoVersion.query.order_by(TrinoVersion.version.desc()).all()
    catalogs = CatalogCompatibility.query.all()
    
    # Format versions for display
    catalog_data = {}
    for catalog in catalogs:
        if catalog.catalog_name not in catalog_data:
            catalog_data[catalog.catalog_name] = {
                'min_version': catalog.min_version,
                'max_version': catalog.max_version,
                'deprecated_in': catalog.deprecated_in,
                'removed_in': catalog.removed_in,
                'notes': catalog.notes
            }
    
    return render_template('version_compatibility.html',
                          versions=versions,
                          catalogs=catalogs,
                          catalog_data=catalog_data,
                          docker_available=docker_available)

@app.route('/add_version', methods=['POST'])
def add_version():
    """Add a new Trino version"""
    if not DATABASE_URL:
        flash('Database functionality is disabled.', 'warning')
        return redirect(url_for('index'))
    
    try:
        version = request.form.get('version')
        release_date_str = request.form.get('release_date')
        is_lts = 'is_lts' in request.form
        support_end_date_str = request.form.get('support_end_date')
        release_notes_url = request.form.get('release_notes_url')
        
        # Parse dates
        release_date = None
        if release_date_str:
            release_date = datetime.strptime(release_date_str, '%Y-%m-%d').date()
        
        support_end_date = None
        if support_end_date_str:
            support_end_date = datetime.strptime(support_end_date_str, '%Y-%m-%d').date()
        
        # Check if version already exists
        existing_version = TrinoVersion.query.filter_by(version=version).first()
        if existing_version:
            flash(f'Version {version} already exists.', 'warning')
            return redirect(url_for('version_compatibility'))
        
        # Create new version
        new_version = TrinoVersion(
            version=version,
            release_date=release_date,
            is_lts=is_lts,
            support_end_date=support_end_date,
            release_notes_url=release_notes_url
        )
        
        db.session.add(new_version)
        db.session.commit()
        
        flash(f'Version {version} added successfully!', 'success')
    except Exception as e:
        logger.error(f"Error adding version: {str(e)}")
        flash(f'Error adding version: {str(e)}', 'danger')
        db.session.rollback()
    
    return redirect(url_for('version_compatibility'))

@app.route('/add_catalog_compatibility', methods=['POST'])
def add_catalog_compatibility():
    """Add catalog compatibility information"""
    if not DATABASE_URL:
        flash('Database functionality is disabled.', 'warning')
        return redirect(url_for('index'))
    
    try:
        catalog_name = request.form.get('catalog_name')
        min_version = request.form.get('min_version')
        max_version = request.form.get('max_version')
        deprecated_in = request.form.get('deprecated_in')
        removed_in = request.form.get('removed_in')
        notes = request.form.get('notes')
        
        # Check if entry already exists
        existing_compat = CatalogCompatibility.query.filter_by(catalog_name=catalog_name).first()
        if existing_compat:
            # Update existing entry
            existing_compat.min_version = min_version
            existing_compat.max_version = max_version
            existing_compat.deprecated_in = deprecated_in
            existing_compat.removed_in = removed_in
            existing_compat.notes = notes
            
            db.session.commit()
            flash(f'Compatibility information for {catalog_name} updated!', 'success')
        else:
            # Create new entry
            new_compat = CatalogCompatibility(
                catalog_name=catalog_name,
                min_version=min_version,
                max_version=max_version,
                deprecated_in=deprecated_in,
                removed_in=removed_in,
                notes=notes
            )
            
            db.session.add(new_compat)
            db.session.commit()
            flash(f'Compatibility information for {catalog_name} added!', 'success')
    except Exception as e:
        logger.error(f"Error adding catalog compatibility: {str(e)}")
        flash(f'Error adding catalog compatibility: {str(e)}', 'danger')
        db.session.rollback()
    
    return redirect(url_for('version_compatibility'))

def seed_version_data():
    """Seed the database with initial version data if it's empty"""
    if TrinoVersion.query.count() == 0:
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
            },
            {
                'version': '403',
                'release_date': date(2023, 3, 10),
                'is_lts': False,
                'support_end_date': None,
                'release_notes_url': 'https://trino.io/docs/current/release/release-403.html'
            },
            {
                'version': '402',
                'release_date': date(2023, 2, 10),
                'is_lts': False,
                'support_end_date': None,
                'release_notes_url': 'https://trino.io/docs/current/release/release-402.html'
            },
            {
                'version': '401',
                'release_date': date(2023, 1, 13),
                'is_lts': False,
                'support_end_date': None,
                'release_notes_url': 'https://trino.io/docs/current/release/release-401.html'
            },
            {
                'version': '398',
                'release_date': date(2022, 11, 24),
                'is_lts': True,
                'support_end_date': date(2023, 11, 24),
                'release_notes_url': 'https://trino.io/docs/current/release/release-398.html'
            },
            {
                'version': '393',
                'release_date': date(2022, 9, 16),
                'is_lts': False,
                'support_end_date': None,
                'release_notes_url': 'https://trino.io/docs/current/release/release-393.html'
            },
            {
                'version': '389',
                'release_date': date(2022, 7, 22),
                'is_lts': False,
                'support_end_date': None,
                'release_notes_url': 'https://trino.io/docs/current/release/release-389.html'
            }
        ]
        
        for version_data in versions:
            version = TrinoVersion(**version_data)
            db.session.add(version)
        
        db.session.commit()
        logger.info("Seeded initial version data")

def seed_catalog_compatibility():
    """Seed the database with initial catalog compatibility data if it's empty"""
    if CatalogCompatibility.query.count() == 0:
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
            },
            {
                'catalog_name': 'mysql',
                'min_version': '350',
                'max_version': None,
                'deprecated_in': None,
                'removed_in': None,
                'notes': 'Well-supported across versions.'
            },
            {
                'catalog_name': 'mariadb',
                'min_version': '377',
                'max_version': None,
                'deprecated_in': None,
                'removed_in': None,
                'notes': 'Uses mysql connector prior to dedicated support.'
            },
            {
                'catalog_name': 'postgres',
                'min_version': '350',
                'max_version': None,
                'deprecated_in': None,
                'removed_in': None,
                'notes': 'Well-supported across versions.'
            },
            {
                'catalog_name': 'sqlserver',
                'min_version': '350',
                'max_version': None,
                'deprecated_in': None,
                'removed_in': None,
                'notes': 'Well-supported across versions.'
            },
            {
                'catalog_name': 'db2',
                'min_version': '386',
                'max_version': None,
                'deprecated_in': None,
                'removed_in': None,
                'notes': 'Added in version 386.'
            },
            {
                'catalog_name': 'clickhouse',
                'min_version': '392',
                'max_version': None,
                'deprecated_in': None,
                'removed_in': None,
                'notes': 'Added in version 392.'
            },
            {
                'catalog_name': 'pinot',
                'min_version': '355',
                'max_version': None,
                'deprecated_in': None,
                'removed_in': None,
                'notes': 'Added in version 355.'
            },
            {
                'catalog_name': 'elasticsearch',
                'min_version': '350',
                'max_version': None,
                'deprecated_in': None,
                'removed_in': None,
                'notes': 'Well-supported across versions.'
            }
        ]
        
        for catalog in catalog_data:
            compat = CatalogCompatibility(**catalog)
            db.session.add(compat)
        
        db.session.commit()
        logger.info("Seeded initial catalog compatibility data")

# Initialize application
# Flask 2.x doesn't have before_first_request anymore
# Use with app.app_context() instead
with app.app_context():
    # Create all database tables
    db.create_all()
    
    # Make sure config exists
    if not os.path.exists('config/config.yaml'):
        default_config = get_default_config()
        save_config(default_config)
    
    # Seed initial data if database is available
    if DATABASE_URL:
        seed_version_data()
        seed_catalog_compatibility()
