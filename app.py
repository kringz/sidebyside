import os
import logging
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
import yaml
import time
import traceback
import json
import random

from config import load_config, save_config, get_default_config
from docker_manager import DockerManager
from trino_client import TrinoClient
from models import (
    db, QueryHistory, TrinoVersion, CatalogCompatibility, 
    BreakingChange, FeatureChange, BenchmarkQuery, BenchmarkResult
)
from datetime import datetime, date
from breaking_changes_v2 import register_breaking_changes_routes

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Initialize Flask application
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev_secret_key")

# Global variable to track image pull progress
image_pull_progress = {}

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
    
    # Force enable TPC-H catalog in demo mode
    try:
        config = load_config()
        if 'tpch' in config['catalogs']:
            config['catalogs']['tpch']['enabled'] = True
            save_config(config)
            logger.info("TPC-H catalog enabled for demo mode")
    except Exception as e:
        logger.error(f"Error enabling TPC-H in demo mode: {str(e)}")
else:
    # Check for and clean up stale containers on startup
    try:
        config = load_config()
        container_names = [config['cluster1']['container_name'], config['cluster2']['container_name']]
        cleaned_containers = docker_manager.cleanup_stale_containers(container_names)
        if cleaned_containers:
            logger.info(f"Cleaned up stale containers on startup: {', '.join(cleaned_containers)}")
    except Exception as e:
        logger.error(f"Error checking for stale containers on startup: {str(e)}")

# Initialize Trino clients (will be set up when clusters are started)
trino_clients = {
    "cluster1": None,
    "cluster2": None
}

@app.route('/')
def landing():
    """Landing page for selecting software to compare"""
    # Get selected software from session or set default
    selected_software = session.get('selected_software', 'trino')
    
    # List of available software options
    software_options = [
        {'id': 'trino', 'name': 'Trino:Trino', 'description': 'Compare different versions of Trino distributed SQL query engine'},
        # Future options will be added here
        {'id': 'spark', 'name': 'Spark:Spark', 'description': 'Compare different versions of Apache Spark (Coming Soon)', 'disabled': True},
        {'id': 'kafka', 'name': 'Kafka:Kafka', 'description': 'Compare different versions of Apache Kafka (Coming Soon)', 'disabled': True}
    ]
    
    return render_template('landing.html', 
                          software_options=software_options,
                          selected_software=selected_software)

@app.route('/select_software', methods=['POST'])
def select_software():
    """Handle software selection from the landing page"""
    software = request.form.get('software')
    if software:
        session['selected_software'] = software
        flash(f'Selected {software} for comparison', 'success')
    
    # Currently we only have Trino implemented, so always redirect to trino_dashboard
    return redirect(url_for('trino_dashboard'))

@app.route('/trino')
def trino_dashboard():
    """Main page with Trino cluster status and management and catalog configuration"""
    config = load_config()
    cluster1_status = docker_manager.get_container_status(config['cluster1']['container_name'])
    cluster2_status = docker_manager.get_container_status(config['cluster2']['container_name'])
    
    # Verify containers are truly running if they report as running
    if docker_available:
        if cluster1_status == 'running' and not docker_manager.verify_container_running(config['cluster1']['container_name']):
            logger.warning(f"Container {config['cluster1']['container_name']} reports as running but is not functional")
            flash(f"Container {config['cluster1']['container_name']} reports as running but might not be functional. Consider restarting.", 'warning')
            # Don't change status here, but show warning to user
            
        if cluster2_status == 'running' and not docker_manager.verify_container_running(config['cluster2']['container_name']):
            logger.warning(f"Container {config['cluster2']['container_name']} reports as running but is not functional")
            flash(f"Container {config['cluster2']['container_name']} reports as running but might not be functional. Consider restarting.", 'warning')
            # Don't change status here, but show warning to user
    
    # Get available Trino images if Docker is available
    available_trino_images = []
    if docker_available:
        available_trino_images = docker_manager.get_available_trino_images()
    
    # Merged the catalog_config_page and index page
    return render_template('index.html', 
                           config=config, 
                           cluster1_status=cluster1_status,
                           cluster2_status=cluster2_status,
                           docker_available=docker_available,
                           available_trino_images=available_trino_images)

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
        version_to_pull = request.form.get('version')
        
        # If a specific version is requested, only pull that one
        if version_to_pull:
            versions = [version_to_pull]
            
        # Global variable to track progress of pulling images
        # Store progress data in a global dictionary
        # This enables us to check progress later via AJAX
        global image_pull_progress
        if 'image_pull_progress' not in globals():
            image_pull_progress = {}
        
        progress_data = {}
        for version in versions:
            progress_data[version] = 0.0
            image_pull_progress[version] = 0.0
            
        # Create a progress tracker callback function with byte information
        def update_progress(version):
            def callback(value, bytes_downloaded=None, total_bytes=None):
                progress_data[version] = value
                image_pull_progress[version] = value
                
                # Store byte information in session for UI display
                if 'pull_details' not in session:
                    session['pull_details'] = {}
                
                if version not in session['pull_details']:
                    session['pull_details'][version] = {
                        'current_bytes': 0,
                        'total_bytes': 0
                    }
                
                # Update byte information if provided
                if bytes_downloaded is not None and total_bytes is not None:
                    session['pull_details'][version]['current_bytes'] = bytes_downloaded
                    session['pull_details'][version]['total_bytes'] = total_bytes
                    logger.debug(f"Pull progress for Trino {version}: {value:.1%} ({bytes_downloaded/(1024*1024):.1f}MB / {total_bytes/(1024*1024):.1f}MB)")
                else:
                    logger.debug(f"Pull progress for Trino {version}: {value:.1%}")
                
                # We don't actually need to return anything, the progress is stored in the shared dict
            return callback
        
        results = {}
        for version in versions:
            if version not in results:
                # Pass the progress callback function for this version
                progress_callback = update_progress(version)
                success = docker_manager.pull_trino_image(version, progress_callback)
                results[version] = success
                
                # If success is immediate (image already existed), mark progress as complete
                if success and progress_data[version] == 0.0:
                    progress_data[version] = 1.0
                    image_pull_progress[version] = 1.0
        
        # Include progress information in the response
        response_data = {
            'progress': progress_data
        }
        
        if all(results.values()):
            response_data.update({
                'success': True, 
                'message': f'Successfully pulled Trino images: {", ".join(versions)}'
            })
            return jsonify(response_data)
        else:
            failed = [v for v, success in results.items() if not success]
            response_data.update({
                'success': False, 
                'message': f'Failed to pull some Trino images: {", ".join(failed)}'
            })
            return jsonify(response_data)
            
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
        for catalog in ['tpch', 'hive', 'iceberg', 'delta-lake', 'mysql', 'mariadb', 'postgres', 'sqlserver', 'db2', 'clickhouse', 'pinot', 'elasticsearch']:
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
            return redirect(url_for('trino_dashboard'))
            
    except Exception as e:
        logger.error(f"Error saving configuration: {str(e)}")
        
        if is_ajax:
            return jsonify({'success': False, 'message': f'Error saving configuration: {str(e)}'})
        else:
            flash(f'Error saving configuration: {str(e)}', 'danger')
            return redirect(url_for('trino_dashboard'))

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
    
    return redirect(url_for('trino_dashboard'))

@app.route('/check_pull_progress')
def check_pull_progress():
    """API endpoint to check the progress of image pulls"""
    global image_pull_progress
    
    if 'image_pull_progress' not in globals():
        image_pull_progress = {}
    
    # Add extended information for progress display
    progress_with_bytes = {}
    for version, progress in image_pull_progress.items():
        # Check if we have detailed information in session
        if 'pull_details' not in session:
            session['pull_details'] = {}
            
        if version not in session['pull_details']:
            session['pull_details'][version] = {
                'current_bytes': 0,
                'total_bytes': 0
            }
            
        # For simplicity in demo mode, use simulated values
        if not docker_available:
            # Simulate download sizes - approximately 500MB images
            total_bytes = 500 * 1024 * 1024
            current_bytes = int(progress * total_bytes)
            
            # Store these in the session for consistency
            session['pull_details'][version]['current_bytes'] = current_bytes
            session['pull_details'][version]['total_bytes'] = total_bytes
            
            # Log the simulation data for debugging
            app.logger.debug(f"Simulated progress for {version}: {progress:.1%} ({current_bytes/(1024*1024):.1f}MB / {total_bytes/(1024*1024):.1f}MB)")
        else:
            # Get detailed information from the session if available
            current_bytes = session['pull_details'][version].get('current_bytes', 0)
            total_bytes = session['pull_details'][version].get('total_bytes', 0)
            
            # If we have a progress value but no bytes (shouldn't happen),
            # simulate it for display purposes
            if progress > 0 and total_bytes == 0:
                total_bytes = 500 * 1024 * 1024  # Assume ~500MB image
                current_bytes = int(progress * total_bytes)
                session['pull_details'][version]['current_bytes'] = current_bytes
                session['pull_details'][version]['total_bytes'] = total_bytes
        
        # Add extended information to response
        progress_with_bytes[version] = {
            'progress': progress,
            'current_bytes': current_bytes,
            'total_bytes': total_bytes
        }
    
    # Add debug logging to see what we're returning
    app.logger.debug(f"Returning progress data: {progress_with_bytes}")
    session.modified = True  # Ensure session changes are saved
    
    return jsonify({
        'progress': image_pull_progress,
        'progress_details': progress_with_bytes
    })

@app.route('/start_clusters', methods=['POST'])
def start_clusters():
    """Start both Trino clusters"""
    try:
        config = load_config()
        
        if not docker_available:
            flash('Docker is not available in this environment. Cluster startup is disabled.', 'warning')
            return redirect(url_for('trino_dashboard'))
        
        # Always ensure TPC-H is enabled before starting clusters
        if 'tpch' in config['catalogs'] and not config['catalogs']['tpch']['enabled']:
            config['catalogs']['tpch']['enabled'] = True
            config['catalogs']['tpch']['column_naming'] = 'SIMPLIFIED'  # Use simplified naming
            save_config(config)
            logger.info("TPC-H catalog enabled for cluster start")
            
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
    
    return redirect(url_for('trino_dashboard'))

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
    
    return redirect(url_for('trino_dashboard'))

@app.route('/clean_shutdown', methods=['POST'])
def clean_shutdown():
    """Perform a clean shutdown of Trino clusters before app exit"""
    try:
        config = load_config()
        
        # Attempt to stop both clusters gracefully
        if docker_available:
            logger.info("Performing clean shutdown of all Trino clusters...")
            docker_manager.stop_trino_cluster(config['cluster1']['container_name'])
            docker_manager.stop_trino_cluster(config['cluster2']['container_name'])
            
            # Reset Trino clients
            trino_clients['cluster1'] = None
            trino_clients['cluster2'] = None
            
            flash('Clean shutdown completed. All Trino clusters have been stopped.', 'success')
        else:
            flash('Docker is not available, no cleanup needed.', 'info')
            
        return redirect(url_for('trino_dashboard'))
    except Exception as e:
        logger.error(f"Error stopping clusters: {str(e)}")
        flash(f'Error stopping clusters: {str(e)}', 'danger')
    
    return redirect(url_for('trino_dashboard'))

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
    
    return redirect(url_for('trino_dashboard'))

@app.route('/query')
def query_page():
    """Page for executing queries against clusters"""
    config = load_config()
    cluster1_status = docker_manager.get_container_status(config['cluster1']['container_name'])
    cluster2_status = docker_manager.get_container_status(config['cluster2']['container_name'])
    
    # Force-enable TPC-H in demo mode
    if not docker_available and 'tpch' in config['catalogs']:
        config['catalogs']['tpch']['enabled'] = True
        
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
    import threading
    import queue
    import random
    
    query = request.form.get('query')
    config = load_config()
    
    if not query:
        flash('Please enter a query', 'warning')
        return redirect(url_for('query_page'))
    
    # Demo mode for query execution when Docker is not available
    is_demo_mode = not docker_available
    if is_demo_mode:
        # Ensure TPC-H is enabled in demo mode for TPC-H queries
        if 'tpch' in query.lower() and 'tpch' in config['catalogs']:
            config['catalogs']['tpch']['enabled'] = True
            save_config(config)
            logger.info("Enabled TPC-H catalog for demo mode query")
        
        flash('Running in demo mode. Query results will be simulated for demonstration purposes.', 'info')
        
    try:
        results = {}
        errors = {}
        timing = {}
        
        # Create a new query history record
        query_history = QueryHistory(query_text=query)
        
        # Create thread-safe queues for collecting results from both clusters
        result_queue = queue.Queue()
        
        # Define worker function to execute queries
        def execute_cluster_query(cluster_name):
            container_name = config[cluster_name]['container_name']
            cluster_result = {}
            
            # Special handling for demo mode
            if is_demo_mode and 'tpch' in query.lower():
                # Simulate a successful TPC-H query in demo mode
                query_lower = query.lower()
                
                # Check for common TPC-H query mistakes and show better error messages
                if ('system.runtime.tpch' in query_lower or 
                    'system.tpch' in query_lower or 
                    'runtime.tpch' in query_lower):
                    cluster_result = {
                        'cluster_name': cluster_name,
                        'error': "Table not found. Please use 'tpch.tiny.customer' format instead of 'system.runtime.tpch'."
                    }
                    result_queue.put(cluster_result)
                    return
                
                start_time = time.time()
                time.sleep(0.5)  # Simulate query execution time
                end_time = time.time()
                
                # Create mock results based on the query
                if 'customer' in query_lower:
                    mock_columns = ['custkey', 'name', 'address', 'nationkey', 'phone', 'acctbal', 'mktsegment', 'comment']
                    mock_rows = []
                    for i in range(10):  # Generate 10 sample rows
                        mock_rows.append([i+1, f'Customer #{i+1}', f'Address #{i+1}', i % 25, f'PHONE#{i+1}', 1000.0 + i*100, f'SEGMENT{i%5}', 'Sample comment'])
                    
                    # Create simulated query results
                    query_results = {
                        'columns': mock_columns,
                        'rows': mock_rows,
                        'stats': {
                            'cpu_time_ms': 150 + (100 * random.random()),
                            'planning_time_ms': 20 + (10 * random.random()),
                            'execution_time_ms': 130 + (90 * random.random()),
                            'queued_time_ms': 5 + (5 * random.random()),
                            'peak_memory_bytes': 1024 * 1024 * (10 + 5 * random.random())
                        }
                    }
                elif 'orders' in query_lower:
                    mock_columns = ['orderkey', 'custkey', 'orderstatus', 'totalprice', 'orderdate', 'orderpriority', 'clerk', 'shippriority', 'comment']
                    mock_rows = []
                    for i in range(10):
                        mock_rows.append([i+100000, i+1, 'O', 10000.0 + i*1000, '2023-01-0'+str(i%9+1), f'Priority {i%5}', f'Clerk#{i}', i%3, 'Order comment'])
                    
                    query_results = {
                        'columns': mock_columns,
                        'rows': mock_rows,
                        'stats': {
                            'cpu_time_ms': 180 + (120 * random.random()),
                            'planning_time_ms': 25 + (15 * random.random()),
                            'execution_time_ms': 155 + (105 * random.random()),
                            'queued_time_ms': 5 + (5 * random.random()),
                            'peak_memory_bytes': 1024 * 1024 * (12 + 6 * random.random())
                        }
                    }
                else:
                    # For other TPC-H queries, create generic results
                    query_results = {
                        'columns': ['column1', 'column2', 'column3'],
                        'rows': [[i, f'Value {i}', i*100] for i in range(5)],
                        'stats': {
                            'cpu_time_ms': 200 + (150 * random.random()),
                            'planning_time_ms': 25 + (15 * random.random()),
                            'execution_time_ms': 175 + (135 * random.random()),
                            'queued_time_ms': 5 + (5 * random.random()),
                            'peak_memory_bytes': 1024 * 1024 * (15 + 10 * random.random())
                        }
                    }
                
                # Save results
                cluster_result = {
                    'cluster_name': cluster_name,
                    'result': query_results,
                    'timing': end_time - start_time
                }
                
            elif docker_manager.get_container_status(container_name) == 'running':
                if trino_clients[cluster_name]:
                    try:
                        # Check for common TPC-H query mistakes before sending to Trino
                        query_lower = query.lower()
                        if ('system.runtime.tpch' in query_lower or 
                            'system.tpch' in query_lower or 
                            'runtime.tpch' in query_lower):
                            cluster_result = {
                                'cluster_name': cluster_name,
                                'error': "Table not found. Please use 'tpch.tiny.customer' format instead of 'system.runtime.tpch'."
                            }
                            result_queue.put(cluster_result)
                            return
                        
                        start_time = time.time()
                        query_results = trino_clients[cluster_name].execute_query(query)
                        end_time = time.time()
                        
                        cluster_result = {
                            'cluster_name': cluster_name,
                            'result': query_results,
                            'timing': end_time - start_time
                        }
                    except Exception as e:
                        logger.error(f"Error executing query on {cluster_name}: {str(e)}")
                        cluster_result = {
                            'cluster_name': cluster_name,
                            'error': str(e)
                        }
                else:
                    cluster_result = {
                        'cluster_name': cluster_name,
                        'error': "Trino client not initialized"
                    }
            else:
                cluster_result = {
                    'cluster_name': cluster_name,
                    'error': "Cluster not running"
                }
            
            # Put the result in the thread-safe queue
            result_queue.put(cluster_result)
        
        # Create and start threads for each cluster to execute queries in parallel
        threads = []
        for cluster_name in ['cluster1', 'cluster2']:
            thread = threading.Thread(target=execute_cluster_query, args=(cluster_name,))
            thread.start()
            threads.append(thread)
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Collect results from the queue
        while not result_queue.empty():
            result = result_queue.get()
            cluster_name = result['cluster_name']
            
            if 'error' in result:
                errors[cluster_name] = result['error']
            else:
                results[cluster_name] = result['result']
                timing[cluster_name] = result['timing']
        
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
        return redirect(url_for('trino_dashboard'))
        
    try:
        history = db.session.query(QueryHistory).order_by(QueryHistory.execution_time.desc()).all()
    except Exception as e:
        app.logger.error(f"Error querying history: {str(e)}")
        history = []
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
        
        # Check cluster status
        cluster1_status = docker_manager.get_container_status(config['cluster1']['container_name'])
        cluster2_status = docker_manager.get_container_status(config['cluster2']['container_name'])
        clusters_running = (cluster1_status == 'running' or cluster2_status == 'running')
        
        # Always enable TPC-H in demo mode or when clusters are running
        if not docker_available or clusters_running:
            config['catalogs']['tpch']['enabled'] = True
            logger.info("TPC-H catalog enforced as enabled (demo mode or clusters running)")
        
        for catalog in config['catalogs']:
            # Always include TPC-H catalog (form has a hidden field to ensure it's sent)
            if catalog in request.form or (catalog == 'tpch' and clusters_running):
                config['catalogs'][catalog]['enabled'] = True
                
                # Save catalog-specific configurations
                if catalog == 'tpch':
                    # Save TPC-H specific settings
                    column_naming = request.form.get('tpch_column_naming', 'SIMPLIFIED')
                    if column_naming in ['SIMPLIFIED', 'STANDARD']:
                        config['catalogs'][catalog]['column_naming'] = column_naming
                elif catalog == 'hive' or catalog == 'iceberg' or catalog == 'delta-lake':
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
    
    return redirect(url_for('trino_dashboard'))

# Seed predefined benchmark queries
def seed_benchmark_queries():
    """Seed predefined benchmark queries for the benchmark playground if none exist"""
    try:
        benchmark_count = db.session.query(BenchmarkQuery).count()
    except Exception as e:
        app.logger.error(f"Error counting benchmark queries: {str(e)}")
        benchmark_count = 0
    if benchmark_count == 0:
        logger.info("Seeding benchmark queries...")
        benchmarks = [
            {
                'name': 'Simple SELECT',
                'description': 'A simple SELECT query with a filter',
                'query_text': 'SELECT * FROM tpch.tiny.customer WHERE nationkey = 1 LIMIT 10',
                'category': 'Basic',
                'complexity': 'Simple',
                'expected_runtime': 0.5
            },
            {
                'name': 'Aggregation',
                'description': 'GROUP BY aggregation query',
                'query_text': 'SELECT nationkey, count(*) FROM tpch.tiny.customer GROUP BY nationkey ORDER BY nationkey',
                'category': 'Aggregation',
                'complexity': 'Simple',
                'expected_runtime': 1.0
            },
            {
                'name': 'Simple Join',
                'description': 'Basic join between customer and orders',
                'query_text': 'SELECT c.name, o.orderkey, o.orderdate FROM tpch.tiny.customer c JOIN tpch.tiny.orders o ON c.custkey = o.custkey LIMIT 20',
                'category': 'Join',
                'complexity': 'Medium',
                'expected_runtime': 1.5
            },
            {
                'name': 'Window Function',
                'description': 'Query with window functions for analytics',
                'query_text': 'SELECT orderkey, clerk, totalprice, rank() OVER (PARTITION BY clerk ORDER BY totalprice DESC) as price_rank FROM tpch.tiny.orders LIMIT 100',
                'category': 'Window Function',
                'complexity': 'Medium',
                'expected_runtime': 2.0
            },
            {
                'name': 'Complex Join',
                'description': 'Multi-table join with aggregation',
                'query_text': '''
                    SELECT
                        n.name as nation,
                        r.name as region,
                        count(c.custkey) as customer_count,
                        sum(o.totalprice) as total_sales
                    FROM
                        tpch.tiny.customer c
                        JOIN tpch.tiny.orders o ON c.custkey = o.custkey
                        JOIN tpch.tiny.nation n ON c.nationkey = n.nationkey
                        JOIN tpch.tiny.region r ON n.regionkey = r.regionkey
                    GROUP BY
                        n.name, r.name
                    ORDER BY
                        total_sales DESC
                ''',
                'category': 'Join',
                'complexity': 'Complex',
                'expected_runtime': 3.0
            },
            {
                'name': 'Subquery',
                'description': 'Query with a subquery in the WHERE clause',
                'query_text': '''
                    SELECT c.name, c.custkey, c.nationkey
                    FROM tpch.tiny.customer c
                    WHERE c.custkey IN (
                        SELECT o.custkey
                        FROM tpch.tiny.orders o
                        WHERE o.totalprice > 150000
                    )
                    LIMIT 20
                ''',
                'category': 'Subquery',
                'complexity': 'Medium',
                'expected_runtime': 2.5
            },
            {
                'name': 'Advanced Aggregation',
                'description': 'Query with multiple aggregations and HAVING clause',
                'query_text': '''
                    SELECT
                        l.suppkey,
                        sum(l.extendedprice) as total_price,
                        avg(l.extendedprice) as avg_price,
                        count(*) as item_count
                    FROM
                        tpch.tiny.lineitem l
                    GROUP BY
                        l.suppkey
                    HAVING
                        count(*) > 300
                    ORDER BY
                        total_price DESC
                    LIMIT 10
                ''',
                'category': 'Aggregation',
                'complexity': 'Complex',
                'expected_runtime': 2.5
            },
            {
                'name': 'Date Functions',
                'description': 'Query with date and time functions',
                'query_text': '''
                    SELECT
                        year(o.orderdate) as order_year,
                        month(o.orderdate) as order_month,
                        count(*) as order_count,
                        sum(o.totalprice) as monthly_sales
                    FROM
                        tpch.tiny.orders o
                    GROUP BY
                        year(o.orderdate),
                        month(o.orderdate)
                    ORDER BY
                        order_year, order_month
                ''',
                'category': 'Date Functions',
                'complexity': 'Medium',
                'expected_runtime': 1.5
            },
            {
                'name': 'Common Table Expression (CTE)',
                'description': 'Query using a CTE for improved readability',
                'query_text': '''
                    WITH high_value_orders AS (
                        SELECT custkey, count(*) as order_count
                        FROM tpch.tiny.orders
                        WHERE totalprice > 150000
                        GROUP BY custkey
                    )
                    SELECT
                        c.name,
                        c.nationkey,
                        hvo.order_count
                    FROM
                        tpch.tiny.customer c
                        JOIN high_value_orders hvo ON c.custkey = hvo.custkey
                    ORDER BY
                        hvo.order_count DESC
                    LIMIT 10
                ''',
                'category': 'CTE',
                'complexity': 'Complex',
                'expected_runtime': 2.0
            },
            {
                'name': 'Nested Subqueries',
                'description': 'Complex query with nested subqueries',
                'query_text': '''
                    SELECT
                        s.name as supplier,
                        n.name as nation,
                        (
                            SELECT avg(ps.supplycost)
                            FROM tpch.tiny.partsupp ps
                            WHERE ps.suppkey = s.suppkey
                        ) as avg_cost,
                        (
                            SELECT count(*)
                            FROM tpch.tiny.lineitem l
                            WHERE l.suppkey = s.suppkey
                        ) as lineitem_count
                    FROM
                        tpch.tiny.supplier s
                        JOIN tpch.tiny.nation n ON s.nationkey = n.nationkey
                    ORDER BY
                        lineitem_count DESC
                    LIMIT 10
                ''',
                'category': 'Subquery',
                'complexity': 'Complex',
                'expected_runtime': 3.5
            }
        ]
        
        for benchmark_data in benchmarks:
            benchmark = BenchmarkQuery(**benchmark_data)
            db.session.add(benchmark)
        
        db.session.commit()
        logger.info(f"Added {len(benchmarks)} benchmark queries to the database")
        return len(benchmarks)
    
    return benchmark_count




@app.route('/add_version', methods=['POST'])
def add_version():
    """Add a new Trino version"""
    if not DATABASE_URL:
        flash('Database functionality is disabled.', 'warning')
        return redirect(url_for('trino_dashboard'))
    
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
            return redirect(url_for('trino_dashboard'))
        
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
    
    return redirect(url_for('trino_dashboard'))

@app.route('/benchmarks')
def benchmark_playground():
    """Page for performance benchmark playground with real-time comparison charts"""
    if not DATABASE_URL:
        flash('Database functionality is disabled. Benchmarking requires database access.', 'warning')
        return redirect(url_for('trino_dashboard'))
    
    config = load_config()
    
    # Ensure TPC-H is enabled for benchmarks, as all benchmark queries use TPC-H
    if 'tpch' in config['catalogs'] and not config['catalogs']['tpch']['enabled']:
        config['catalogs']['tpch']['enabled'] = True
        save_config(config)
        logger.info("Enabled TPC-H catalog for benchmark playground")
    cluster1_status = docker_manager.get_container_status(config['cluster1']['container_name'])
    cluster2_status = docker_manager.get_container_status(config['cluster2']['container_name'])
    
    # Get all benchmark queries
    try:
        benchmarks = db.session.query(BenchmarkQuery).filter_by(is_active=True).order_by(BenchmarkQuery.category, BenchmarkQuery.name).all()
    except Exception as e:
        app.logger.error(f"Error querying benchmark queries: {str(e)}")
        benchmarks = []
    
    # Group benchmarks by category for easier display
    benchmark_categories = {}
    for benchmark in benchmarks:
        if benchmark.category not in benchmark_categories:
            benchmark_categories[benchmark.category] = []
        benchmark_categories[benchmark.category].append(benchmark)
    
    # Get recent benchmark results (last 10)
    try:
        recent_results = db.session.query(BenchmarkResult).order_by(BenchmarkResult.execution_time.desc()).limit(10).all()
    except Exception as e:
        # Log the error
        app.logger.error(f"Error querying benchmark results: {str(e)}")
        # Provide empty results as fallback
        recent_results = []
    
    return render_template('benchmark_playground.html',
                           benchmarks=benchmarks,
                           benchmark_categories=benchmark_categories,
                           recent_results=recent_results,
                           config=config,
                           cluster1_status=cluster1_status,
                           cluster2_status=cluster2_status,
                           docker_available=docker_available)

@app.route('/run_benchmark', methods=['POST'])
def run_benchmark():
    """Run a benchmark query and record results"""
    import threading
    import queue
    import random
    
    if not DATABASE_URL:
        flash('Database functionality is disabled. Benchmarking requires database access.', 'warning')
        return redirect(url_for('benchmarks'))
    
    benchmark_id = request.form.get('benchmark_id')
    
    if not benchmark_id:
        flash('No benchmark selected', 'warning')
        return redirect(url_for('benchmark_playground'))
    
    # Demo mode warning but allow benchmarks to run with simulated results
    is_demo_mode = not docker_available
    if is_demo_mode:
        flash('Running in demo mode. Results will be simulated for demonstration purposes.', 'info')
    
    try:
        # Load the benchmark query
        try:
            benchmark = db.session.query(BenchmarkQuery).get(benchmark_id)
        except Exception as e:
            app.logger.error(f"Error retrieving benchmark query: {str(e)}")
            benchmark = None
        if not benchmark:
            flash('Benchmark not found', 'warning')
            return redirect(url_for('benchmark_playground'))
        
        config = load_config()
        results = {}
        errors = {}
        timing = {}
        cpu_time = {}
        memory_usage = {}
        row_counts = {}
        timing_details = {}
        
        # Create a new benchmark result record
        benchmark_result = BenchmarkResult(
            benchmark_query_id=benchmark.id,
            cluster1_version=config['cluster1']['version'],
            cluster2_version=config['cluster2']['version'],
            cluster1_config=json.dumps(config['cluster1']),
            cluster2_config=json.dumps(config['cluster2'])
        )
        
        # Create thread-safe queue for collecting results from both clusters
        result_queue = queue.Queue()
        
        # Define worker function to execute benchmark query
        def execute_benchmark_query(cluster_name):
            container_name = config[cluster_name]['container_name']
            cluster_result = {
                'cluster_name': cluster_name
            }
            
            # Handle demo mode for TPC-H queries specially
            if is_demo_mode and 'tpch' in benchmark.query_text.lower():
                # Simulate a successful TPC-H query in demo mode
                query_text = benchmark.query_text.lower()
                start_time = time.time()
                time.sleep(0.5)  # Simulate query execution time
                end_time = time.time()
                
                # Create mock results based on the query
                if 'customer' in query_text:
                    mock_columns = ['custkey', 'name', 'address', 'nationkey', 'phone', 'acctbal', 'mktsegment', 'comment']
                    mock_rows = []
                    for i in range(10):  # Generate 10 sample rows
                        mock_rows.append([i+1, f'Customer #{i+1}', f'Address #{i+1}', i % 25, f'PHONE#{i+1}', 1000.0 + i*100, f'SEGMENT{i%5}', 'Sample comment'])
                    
                    # Create simulated query results
                    query_results = {
                        'columns': mock_columns,
                        'rows': mock_rows,
                        'stats': {
                            'cpu_time_ms': 150 + (100 * random.random()),
                            'planning_time_ms': 20 + (10 * random.random()),
                            'execution_time_ms': 130 + (90 * random.random()),
                            'queued_time_ms': 5 + (5 * random.random()),
                            'peak_memory_bytes': 1024 * 1024 * (10 + 5 * random.random())
                        }
                    }
                    
                    # Add results to the dictionary
                    cluster_result['result'] = query_results
                    cluster_result['timing'] = end_time - start_time
                    cluster_result['status'] = 'Success'
                    cluster_result['row_count'] = len(query_results.get('rows', []))
                    
                    # Add CPU time and memory usage
                    stats = query_results['stats']
                    cluster_result['cpu_time'] = stats.get('cpu_time_ms', 0) / 1000.0  # Convert to seconds
                    cluster_result['memory_usage'] = stats.get('peak_memory_bytes', 0) / (1024 * 1024)  # Convert to MB
                    
                    # Add timing details
                    cluster_result['timing_details'] = {
                        'planning_time': stats.get('planning_time_ms', 0) / 1000.0,
                        'execution_time': stats.get('execution_time_ms', 0) / 1000.0,
                        'queued_time': stats.get('queued_time_ms', 0) / 1000.0
                    }
                else:
                    # For other TPC-H queries, create generic results
                    query_results = {
                        'columns': ['column1', 'column2', 'column3'],
                        'rows': [[i, f'Value {i}', i*100] for i in range(5)],
                        'stats': {
                            'cpu_time_ms': 200 + (150 * random.random()),
                            'planning_time_ms': 25 + (15 * random.random()),
                            'execution_time_ms': 175 + (135 * random.random()),
                            'queued_time_ms': 5 + (5 * random.random()),
                            'peak_memory_bytes': 1024 * 1024 * (15 + 10 * random.random())
                        }
                    }
                    
                    # Add results to the dictionary
                    cluster_result['result'] = query_results
                    cluster_result['timing'] = end_time - start_time
                    cluster_result['status'] = 'Success'
                    cluster_result['row_count'] = len(query_results.get('rows', []))
                    
                    # Add CPU time and memory usage
                    stats = query_results['stats']
                    cluster_result['cpu_time'] = stats.get('cpu_time_ms', 0) / 1000.0
                    cluster_result['memory_usage'] = stats.get('peak_memory_bytes', 0) / (1024 * 1024)
                    
                    # Add timing details
                    cluster_result['timing_details'] = {
                        'planning_time': stats.get('planning_time_ms', 0) / 1000.0,
                        'execution_time': stats.get('execution_time_ms', 0) / 1000.0,
                        'queued_time': stats.get('queued_time_ms', 0) / 1000.0
                    }
            elif docker_manager.get_container_status(container_name) == 'running':
                if trino_clients[cluster_name]:
                    try:
                        # Execute the query with timing
                        start_time = time.time()
                        query_results = trino_clients[cluster_name].execute_query(benchmark.query_text)
                        end_time = time.time()
                        
                        # Add results to the dictionary
                        cluster_result['result'] = query_results
                        cluster_result['timing'] = end_time - start_time
                        cluster_result['status'] = 'Success'
                        cluster_result['row_count'] = len(query_results.get('rows', []))
                        
                        # Try to extract CPU time and memory usage from query stats if available
                        if 'stats' in query_results:
                            stats = query_results['stats']
                            cluster_result['cpu_time'] = stats.get('cpu_time_ms', 0) / 1000.0  # Convert to seconds
                            cluster_result['memory_usage'] = stats.get('peak_memory_bytes', 0) / (1024 * 1024)  # Convert to MB
                            
                            # Add timing details
                            cluster_result['timing_details'] = {
                                'planning_time': stats.get('planning_time_ms', 0) / 1000.0,
                                'execution_time': stats.get('execution_time_ms', 0) / 1000.0,
                                'queued_time': stats.get('queued_time_ms', 0) / 1000.0
                            }
                    except Exception as e:
                        logger.error(f"Error executing benchmark on {cluster_name}: {str(e)}")
                        cluster_result['error'] = str(e)
                        cluster_result['status'] = 'Error'
                else:
                    cluster_result['error'] = "Trino client not initialized"
                    cluster_result['status'] = 'Error'
            else:
                cluster_result['error'] = "Cluster not running"
                cluster_result['status'] = 'Error'
                
            # Put the result in the queue
            result_queue.put(cluster_result)
            
        # Create and start threads for each cluster to execute queries in parallel
        threads = []
        for cluster_name in ['cluster1', 'cluster2']:
            thread = threading.Thread(target=execute_benchmark_query, args=(cluster_name,))
            thread.start()
            threads.append(thread)
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Collect results from the queue
        while not result_queue.empty():
            result = result_queue.get()
            cluster_name = result['cluster_name']
            
            if 'error' in result:
                errors[cluster_name] = result['error']
                if cluster_name == 'cluster1':
                    benchmark_result.cluster1_status = 'Error'
                    benchmark_result.cluster1_error = result['error']
                else:
                    benchmark_result.cluster2_status = 'Error'
                    benchmark_result.cluster2_error = result['error']
            else:
                # Store the results
                results[cluster_name] = result['result']
                timing[cluster_name] = result['timing']
                
                # Update the benchmark result with status
                if cluster_name == 'cluster1':
                    benchmark_result.cluster1_status = result['status']
                    benchmark_result.cluster1_timing = result['timing']
                    if 'row_count' in result:
                        benchmark_result.cluster1_row_count = result['row_count']
                    if 'cpu_time' in result:
                        benchmark_result.cluster1_cpu_time = result['cpu_time']
                    if 'memory_usage' in result:
                        benchmark_result.cluster1_memory_usage = result['memory_usage']
                    if 'timing_details' in result:
                        benchmark_result.cluster1_timing_details = json.dumps(result['timing_details'])
                else:
                    benchmark_result.cluster2_status = result['status']
                    benchmark_result.cluster2_timing = result['timing']
                    if 'row_count' in result:
                        benchmark_result.cluster2_row_count = result['row_count']
                    if 'cpu_time' in result:
                        benchmark_result.cluster2_cpu_time = result['cpu_time']
                    if 'memory_usage' in result:
                        benchmark_result.cluster2_memory_usage = result['memory_usage']
                    if 'timing_details' in result:
                        benchmark_result.cluster2_timing_details = json.dumps(result['timing_details'])
        
        # Save results to the database
        db.session.add(benchmark_result)
        db.session.commit()
        logger.info(f"Saved benchmark result for query: {benchmark.name}")
        
        return render_template('benchmark_result.html',
                               benchmark=benchmark,
                               result=benchmark_result,
                               results=results,
                               errors=errors,
                               config=config,
                               docker_available=docker_available)
                               
    except Exception as e:
        logger.error(f"Error during benchmark execution: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f'Error during benchmark execution: {str(e)}', 'danger')
        return redirect(url_for('benchmark_playground'))

@app.route('/benchmark_results')
def benchmark_results():
    """Page for viewing all benchmark results"""
    if not DATABASE_URL:
        flash('Database functionality is disabled. Benchmarking requires database access.', 'warning')
        return redirect(url_for('trino_dashboard'))
    
    # Get all benchmark results with their queries
    try:
        results = db.session.query(BenchmarkResult).order_by(BenchmarkResult.execution_time.desc()).all()
    except Exception as e:
        # Log the error
        app.logger.error(f"Error querying benchmark results: {str(e)}")
        # Provide empty results as fallback
        results = []
    
    # Group by query for easier analysis
    results_by_query = {}
    for result in results:
        query_id = result.benchmark_query_id
        if query_id not in results_by_query:
            results_by_query[query_id] = []
        results_by_query[query_id].append(result)
    
    return render_template('benchmark_results.html',
                           results=results,
                           results_by_query=results_by_query,
                           docker_available=docker_available)

@app.route('/benchmark_result/<int:result_id>')
def view_benchmark_result(result_id):
    """View a specific benchmark result"""
    if not DATABASE_URL:
        flash('Database functionality is disabled. Benchmarking requires database access.', 'warning')
        return redirect(url_for('trino_dashboard'))
    
    try:
        result = db.session.query(BenchmarkResult).get_or_404(result_id)
        benchmark = db.session.query(BenchmarkQuery).get(result.benchmark_query_id)
    except Exception as e:
        app.logger.error(f"Error retrieving benchmark result: {str(e)}")
        flash(f"Error retrieving benchmark result: {str(e)}", "danger")
        return redirect(url_for('benchmark_results'))
    
    return render_template('benchmark_result_detail.html',
                           result=result,
                           benchmark=benchmark,
                           docker_available=docker_available)

@app.route('/benchmark_comparison')
def benchmark_comparison():
    """Compare benchmark results across versions"""
    if not DATABASE_URL:
        flash('Database functionality is disabled. Benchmarking requires database access.', 'warning')
        return redirect(url_for('trino_dashboard'))
    
    # Get all benchmarks
    try:
        benchmarks = db.session.query(BenchmarkQuery).all()
    except Exception as e:
        app.logger.error(f"Error querying benchmarks: {str(e)}")
        benchmarks = []
    
    # Get version info
    try:
        versions = db.session.query(TrinoVersion).order_by(TrinoVersion.version.desc()).all()
    except Exception as e:
        # Log the error
        app.logger.error(f"Error querying Trino versions: {str(e)}")
        # Provide empty results as fallback
        versions = []
    
    # For each benchmark, get performance across versions
    comparison_data = {}
    for benchmark in benchmarks:
        comparison_data[benchmark.id] = {
            'name': benchmark.name,
            'category': benchmark.category,
            'versions': {},
            'chart_data': {
                'labels': [],
                'cluster1': [],
                'cluster2': []
            }
        }
        
        # Get results for this benchmark
        try:
            results = db.session.query(BenchmarkResult).filter_by(benchmark_query_id=benchmark.id).order_by(BenchmarkResult.execution_time).all()
        except Exception as e:
            # Log the error
            app.logger.error(f"Error querying benchmark results: {str(e)}")
            # Provide empty results as fallback
            results = []
        
        for result in results:
            version_pair = f"{result.cluster1_version}-{result.cluster2_version}"
            if version_pair not in comparison_data[benchmark.id]['versions']:
                comparison_data[benchmark.id]['versions'][version_pair] = []
            
            comparison_data[benchmark.id]['versions'][version_pair].append(result)
            
            # Add to chart data
            if result.cluster1_timing or result.cluster2_timing:
                comparison_data[benchmark.id]['chart_data']['labels'].append(version_pair)
                comparison_data[benchmark.id]['chart_data']['cluster1'].append(result.cluster1_timing or 0)
                comparison_data[benchmark.id]['chart_data']['cluster2'].append(result.cluster2_timing or 0)
    
    return render_template('benchmark_comparison.html',
                           benchmarks=benchmarks,
                           versions=versions,
                           comparison_data=comparison_data,
                           docker_available=docker_available)

@app.route('/add_catalog_compatibility', methods=['POST'])
def add_catalog_compatibility():
    """Add catalog compatibility information"""
    if not DATABASE_URL:
        flash('Database functionality is disabled.', 'warning')
        return redirect(url_for('trino_dashboard'))
    
    try:
        catalog_name = request.form.get('catalog_name')
        min_version = request.form.get('min_version')
        max_version = request.form.get('max_version')
        deprecated_in = request.form.get('deprecated_in')
        removed_in = request.form.get('removed_in')
        notes = request.form.get('notes')
        
        # Check if entry already exists
        try:
            existing_compat = db.session.query(CatalogCompatibility).filter_by(catalog_name=catalog_name).first()
        except Exception as e:
            app.logger.error(f"Error querying catalog compatibility: {str(e)}")
            existing_compat = None
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
    
    return redirect(url_for('trino_dashboard'))

def seed_version_data():
    """Seed the database with initial version data if it's empty"""
    try:
        version_count = db.session.query(TrinoVersion).count()
    except Exception as e:
        app.logger.error(f"Error counting Trino versions: {str(e)}")
        version_count = 0
        
    if version_count == 0:
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
    try:
        catalog_count = db.session.query(CatalogCompatibility).count()
    except Exception as e:
        app.logger.error(f"Error counting catalog compatibility records: {str(e)}")
        catalog_count = 0
        
    if catalog_count == 0:
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

# Register the breaking changes routes (using v2 version)
from breaking_changes_v2 import register_breaking_changes_routes
register_breaking_changes_routes(app)

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
    
    # Set the current config for breaking_changes module to access
    app.config['CURRENT_CONFIG'] = load_config()
    
    # Seed initial data if database is available
    if DATABASE_URL:
        seed_version_data()
        seed_catalog_compatibility()
        seed_benchmark_queries()
