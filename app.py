import os
import logging
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import yaml
import time
import traceback
import json

from config import load_config, save_config, get_default_config
from docker_manager import DockerManager
from trino_client import TrinoClient
from models import (
    db, QueryHistory, TrinoVersion, CatalogCompatibility, 
    BreakingChange, FeatureChange, BenchmarkQuery, BenchmarkResult
)
from datetime import datetime, date
from breaking_changes import register_breaking_changes_routes

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

# Seed predefined benchmark queries
def seed_benchmark_queries():
    """Seed predefined benchmark queries for the benchmark playground if none exist"""
    benchmark_count = BenchmarkQuery.query.count()
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


@app.route('/version_compatibility')
def version_compatibility():
    """Page for displaying Trino version compatibility information"""
    if not DATABASE_URL:
        flash('Database functionality is disabled.', 'warning')
        return redirect(url_for('index'))
    
    try:
        versions = TrinoVersion.query.order_by(TrinoVersion.version.desc()).all()
    except AttributeError:
        # Fix for SQLAlchemy ordering issue
        versions = TrinoVersion.query.all()
        # Sort manually 
        versions = sorted(versions, key=lambda x: x.version, reverse=True) if versions else []
    
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

@app.route('/benchmarks')
def benchmark_playground():
    """Page for performance benchmark playground with real-time comparison charts"""
    if not DATABASE_URL:
        flash('Database functionality is disabled. Benchmarking requires database access.', 'warning')
        return redirect(url_for('index'))
    
    config = load_config()
    cluster1_status = docker_manager.get_container_status(config['cluster1']['container_name'])
    cluster2_status = docker_manager.get_container_status(config['cluster2']['container_name'])
    
    # Get all benchmark queries
    benchmarks = BenchmarkQuery.query.filter_by(is_active=True).order_by(BenchmarkQuery.category, BenchmarkQuery.name).all()
    
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
    if not DATABASE_URL:
        flash('Database functionality is disabled. Benchmarking requires database access.', 'warning')
        return redirect(url_for('benchmarks'))
    
    benchmark_id = request.form.get('benchmark_id')
    
    if not benchmark_id:
        flash('No benchmark selected', 'warning')
        return redirect(url_for('benchmark_playground'))
    
    if not docker_available:
        flash('Docker is not available in this environment. Benchmark execution is disabled.', 'warning')
        return redirect(url_for('benchmark_playground'))
    
    try:
        # Load the benchmark query
        benchmark = BenchmarkQuery.query.get(benchmark_id)
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
        
        # Run the query on both clusters (if running)
        for cluster_name in ['cluster1', 'cluster2']:
            container_name = config[cluster_name]['container_name']
            if docker_manager.get_container_status(container_name) == 'running':
                if trino_clients[cluster_name]:
                    try:
                        # Execute the query with timing
                        start_time = time.time()
                        query_results = trino_clients[cluster_name].execute_query(benchmark.query_text)
                        end_time = time.time()
                        
                        # Save results
                        results[cluster_name] = query_results
                        timing[cluster_name] = end_time - start_time
                        
                        # Extract row count
                        row_counts[cluster_name] = len(query_results.get('rows', []))
                        
                        # Try to extract CPU time and memory usage from query stats if available
                        if 'stats' in query_results:
                            stats = query_results['stats']
                            cpu_time[cluster_name] = stats.get('cpu_time_ms', 0) / 1000.0  # Convert to seconds
                            memory_usage[cluster_name] = stats.get('peak_memory_bytes', 0) / (1024 * 1024)  # Convert to MB
                            
                            # Capture detailed timing for planning vs execution
                            timing_details[cluster_name] = {
                                'planning_time': stats.get('planning_time_ms', 0) / 1000.0,
                                'execution_time': stats.get('execution_time_ms', 0) / 1000.0,
                                'queued_time': stats.get('queued_time_ms', 0) / 1000.0
                            }
                        
                        # Set status to success
                        if cluster_name == 'cluster1':
                            benchmark_result.cluster1_status = 'Success'
                        else:
                            benchmark_result.cluster2_status = 'Success'
                            
                    except Exception as e:
                        logger.error(f"Error executing benchmark on {cluster_name}: {str(e)}")
                        errors[cluster_name] = str(e)
                        
                        # Set status to error
                        if cluster_name == 'cluster1':
                            benchmark_result.cluster1_status = 'Error'
                            benchmark_result.cluster1_error = str(e)
                        else:
                            benchmark_result.cluster2_status = 'Error'
                            benchmark_result.cluster2_error = str(e)
                else:
                    errors[cluster_name] = "Trino client not initialized"
                    if cluster_name == 'cluster1':
                        benchmark_result.cluster1_status = 'Error'
                        benchmark_result.cluster1_error = "Trino client not initialized"
                    else:
                        benchmark_result.cluster2_status = 'Error'
                        benchmark_result.cluster2_error = "Trino client not initialized"
            else:
                errors[cluster_name] = "Cluster not running"
                if cluster_name == 'cluster1':
                    benchmark_result.cluster1_status = 'Error'
                    benchmark_result.cluster1_error = "Cluster not running"
                else:
                    benchmark_result.cluster2_status = 'Error'
                    benchmark_result.cluster2_error = "Cluster not running"
        
        # Save timing and resource usage metrics
        if 'cluster1' in timing:
            benchmark_result.cluster1_timing = timing['cluster1']
        if 'cluster2' in timing:
            benchmark_result.cluster2_timing = timing['cluster2']
        if 'cluster1' in cpu_time:
            benchmark_result.cluster1_cpu_time = cpu_time['cluster1']
        if 'cluster2' in cpu_time:
            benchmark_result.cluster2_cpu_time = cpu_time['cluster2']
        if 'cluster1' in memory_usage:
            benchmark_result.cluster1_memory_usage = memory_usage['cluster1']
        if 'cluster2' in memory_usage:
            benchmark_result.cluster2_memory_usage = memory_usage['cluster2']
        if 'cluster1' in row_counts:
            benchmark_result.cluster1_row_count = row_counts['cluster1']
        if 'cluster2' in row_counts:
            benchmark_result.cluster2_row_count = row_counts['cluster2']
        if 'cluster1' in timing_details:
            benchmark_result.cluster1_timing_details = json.dumps(timing_details['cluster1'])
        if 'cluster2' in timing_details:
            benchmark_result.cluster2_timing_details = json.dumps(timing_details['cluster2'])
        
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
        return redirect(url_for('index'))
    
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
        return redirect(url_for('index'))
    
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
        return redirect(url_for('index'))
    
    # Get all benchmarks
    benchmarks = BenchmarkQuery.query.all()
    
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

# Register the breaking changes routes
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
