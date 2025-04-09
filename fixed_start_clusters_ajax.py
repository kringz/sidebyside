from flask import jsonify
import time
import logging

from app import app
from config import load_config
from docker_manager import DockerManager
from trino_client import TrinoClient

# Get the Docker manager instance used by your app
docker_manager = None  # This will be imported from app.py
docker_available = False  # This will be imported from app.py
trino_clients = {}  # This will be imported from app.py
logger = logging.getLogger(__name__)

@app.route('/start_clusters_ajax', methods=['POST'])
def start_clusters_ajax():
    """Start both Trino clusters with AJAX progress feedback"""
    if not docker_available:
        return jsonify({
            'success': False, 
            'message': 'Docker is not available in this environment. Cluster startup is disabled.',
            'progress': 100,
            'status': 'error'
        })
        
    config = load_config()
    
    try:
        # Step 1: Pull images (20% of progress)
        versions = [config['cluster1']['version'], config['cluster2']['version']]
        image_results = {}
        
        # Pre-pull all necessary images
        for version in versions:
            if version not in image_results:
                logger.info(f"Ensuring Trino image {version} is pulled...")
                success = docker_manager.pull_trino_image(version)
                image_results[version] = success
                
        # Step 2: Start first cluster
        logger.info(f"Starting Trino cluster 1 (version {config['cluster1']['version']})...")
        docker_manager.start_trino_cluster(
            config['cluster1']['container_name'],
            config['cluster1']['version'],
            config['cluster1']['port'],
            config['catalogs']
        )
        
        # Step 3: Start second cluster
        logger.info(f"Starting Trino cluster 2 (version {config['cluster2']['version']})...")
        docker_manager.start_trino_cluster(
            config['cluster2']['container_name'],
            config['cluster2']['version'],
            config['cluster2']['port'],
            config['catalogs']
        )
        
        # Step 4: Wait for clusters to initialize and set up clients
        # Wait to give time for clusters to initialize
        time.sleep(5)
        
        # Initialize Trino clients using the configured host
        trino_host = config.get('docker', {}).get('trino_connect_host', 'localhost')
        trino_clients['cluster1'] = TrinoClient(
            host=trino_host,
            port=config['cluster1']['port'],
            user='trino',
            cluster_name='Cluster 1'
        )
        
        trino_clients['cluster2'] = TrinoClient(
            host=trino_host,
            port=config['cluster2']['port'],
            user='trino',
            cluster_name='Cluster 2'
        )
        
        return jsonify({
            'success': True, 
            'progress': 100,
            'status': 'complete',
            'message': 'Trino clusters started successfully!'
        })
        
    except Exception as e:
        logger.error(f"Error starting Trino clusters: {str(e)}")
        error_message = f'Error starting Trino clusters: {str(e)}'
        return jsonify({
            'success': False, 
            'progress': 100,
            'status': 'error',
            'message': error_message
        })