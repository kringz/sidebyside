import os
import logging
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import yaml
import time
import traceback

from config import load_config, save_config, get_default_config
from docker_manager import DockerManager
from trino_client import TrinoClient
from models import db, QueryHistory

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
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    logger.info(f"Database URL configured: {DATABASE_URL[:15]}...")
else:
    logger.warning("No DATABASE_URL environment variable found. Database functionality will be disabled.")

# Initialize the database
db.init_app(app)

# Initialize Docker manager
docker_manager = DockerManager()

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
    """Main page with cluster status and management"""
    config = load_config()
    cluster1_status = docker_manager.get_container_status(config['cluster1']['container_name'])
    cluster2_status = docker_manager.get_container_status(config['cluster2']['container_name'])
    
    return render_template('index.html', 
                           config=config, 
                           cluster1_status=cluster1_status,
                           cluster2_status=cluster2_status,
                           docker_available=docker_available)

@app.route('/save_config', methods=['POST'])
def save_configuration():
    """Save cluster configuration"""
    try:
        config = load_config()
        
        # Update cluster configurations
        config['cluster1']['version'] = request.form.get('cluster1_version')
        config['cluster1']['port'] = int(request.form.get('cluster1_port'))
        config['cluster1']['container_name'] = request.form.get('cluster1_container_name')
        
        config['cluster2']['version'] = request.form.get('cluster2_version')
        config['cluster2']['port'] = int(request.form.get('cluster2_port'))
        config['cluster2']['container_name'] = request.form.get('cluster2_container_name')
        
        # Save catalog configurations
        for catalog in ['hive', 'iceberg', 'delta-lake', 'mysql', 'mariadb', 'postgres', 'sqlserver', 'db2', 'clickhouse', 'pinot', 'elasticsearch']:
            config['catalogs'][catalog]['enabled'] = catalog in request.form.getlist('enabled_catalogs')
        
        save_config(config)
        flash('Configuration saved successfully!', 'success')
    except Exception as e:
        logger.error(f"Error saving configuration: {str(e)}")
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
        time.sleep(5)
        
        # Initialize Trino clients
        trino_clients['cluster1'] = TrinoClient(
            host='localhost',
            port=config['cluster1']['port'],
            user='trino',
            cluster_name=f"Trino {config['cluster1']['version']}"
        )
        
        trino_clients['cluster2'] = TrinoClient(
            host='localhost',
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
    
    return redirect(url_for('catalog_config_page'))

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
