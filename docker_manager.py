import os
import yaml
import logging
import tempfile
import time
import json
import threading
import random
import subprocess
from pathlib import Path
from minitrino import components
from minitrino import utils
from minitrino import settings
import docker

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DockerManager:
    """Manages Trino clusters using Minitrino"""
    
    def __init__(self, socket_path=None, timeout=30, trino_connect_host='localhost'):
        """Initialize the Docker manager with configurable connection options
        
        Args:
            socket_path (str, optional): Custom Docker socket path
            timeout (int, optional): Timeout for operations in seconds, defaults to 30
            trino_connect_host (str, optional): Hostname used by Trino clients to connect to Trino servers
        """
        self.timeout = timeout
        self.trino_connect_host = trino_connect_host
        self.demo_mode = False
        
        try:
            # Use unix:// prefix for Unix socket paths
            if socket_path and socket_path.startswith('/'):
                socket_path = f"unix://{socket_path}"
            self.minitrino_manager = MinitrinoManager(socket_path=socket_path)
            logger.info("Docker manager initialized successfully")
            self.docker_available = self.minitrino_manager.docker_available
            self.client = self.minitrino_manager.client
        except Exception as e:
            logger.error(f"Minitrino initialization failed: {str(e)}")
            raise Exception("Minitrino initialization failed. Docker is required for this application to work.")
    
    def get_container_status(self, container_name):
        """Get the status of a container
        
        Args:
            container_name (str): Name of the container
            
        Returns:
            dict: Status information including running state and version
        """
        try:
            status = self.minitrino_manager.get_cluster_status(container_name)
            return {
                "status": status,
                "version": self.minitrino_manager.get_cluster_version(container_name),
                "port": self.minitrino_manager.get_cluster_port(container_name)
            }
        except Exception as e:
            logger.error(f"Error getting container status: {str(e)}")
            return {"status": "error", "version": "unknown", "port": 0}
    
    def start_trino_clusters(self, cluster1_config, cluster2_config):
        """Start two Trino clusters for side-by-side comparison
        
        Args:
            cluster1_config (dict): Configuration for first cluster
            cluster2_config (dict): Configuration for second cluster
        """
        logger.info("Starting Trino clusters...")
        logger.info(f"Cluster 1 config: {json.dumps(cluster1_config, indent=2)}")
        logger.info(f"Cluster 2 config: {json.dumps(cluster2_config, indent=2)}")
        return self.minitrino_manager.start_clusters(cluster1_config, cluster2_config)
    
    def start_trino_cluster(self, container_name, version, port, catalogs_config, pending_properties=None):
        """Start a single Trino cluster
        
        Args:
            container_name (str): Name for the container
            version (str): Trino version to use
            port (int): Port to expose Trino on
            catalogs_config (dict): Catalog configuration
            pending_properties (dict, optional): Pending catalog properties to apply
        """
        logger.info(f"Starting Trino cluster {container_name}...")
        logger.info(f"Version: {version}, Port: {port}")
        logger.info(f"Catalogs config: {json.dumps(catalogs_config, indent=2)}")
        if pending_properties:
            logger.info(f"Pending properties: {json.dumps(pending_properties, indent=2)}")
        
        config = {
            'version': version,
            'port': port,
            'catalogs': catalogs_config,
            'pending_properties': pending_properties
        }
        return self.minitrino_manager._start_cluster(container_name, config)
    
    def stop_trino_cluster(self, container_name):
        """Stop a Trino cluster
        
        Args:
            container_name (str): Name of the container to stop
        """
        return self.minitrino_manager.stop_cluster(container_name)
    
    def verify_container_running(self, container_name):
        """Verify if a container is running
        
        Args:
            container_name (str): Name of the container to verify
            
        Returns:
            bool: True if container is running, False otherwise
        """
        status = self.minitrino_manager.get_cluster_status(container_name)
        return status == "running"
    
    def cleanup_stale_containers(self, container_names):
        """Clean up stale containers
        
        Args:
            container_names (list): List of container names to clean up
        """
        self.minitrino_manager.cleanup()
    
    def pull_trino_image(self, version, progress_callback=None):
        """Pull a Trino image
        
        Args:
            version (str): Version of Trino to pull
            progress_callback (callable, optional): Callback for progress updates
            
        Returns:
            bool: True if successful, False otherwise
        """
        return self.minitrino_manager.pull_image(version, progress_callback)
    
    def get_available_trino_images(self):
        """Get list of available Trino images
        
        Returns:
            list: List of available Trino versions
        """
        return self.minitrino_manager.get_available_images()

class MinitrinoManager:
    """Manages Trino clusters using Minitrino"""
    
    def __init__(self, socket_path=None):
        """Initialize the Minitrino manager
        
        Args:
            socket_path (str, optional): Path to Docker socket
        """
        self.docker_available = False
        self.client = None
        self.clusters = {}  # Track cluster configurations
        
        try:
            # Format socket path correctly
            if socket_path:
                if socket_path.startswith('/'):
                    socket_path = f"unix://{socket_path}"
                elif not socket_path.startswith('unix://'):
                    socket_path = f"unix://{socket_path}"
            
            # Initialize Docker client with proper socket path
            self.client = docker.DockerClient(base_url=socket_path or 'unix:///var/run/docker.sock')
            
            # Test connection
            self.client.containers.list()
            self.docker_available = True
            logger.info("Minitrino manager initialized successfully with Docker client")
        except Exception as e:
            logger.error(f"Cannot connect to Docker in MinitrinoManager: {str(e)}")
            self.docker_available = False
            self.client = None
    
    def _run_minitrino_command(self, command, args=None, env_vars=None):
        """Run a minitrino command
        
        Args:
            command (str): The minitrino command to run
            args (list, optional): Additional arguments
            env_vars (dict, optional): Environment variables
            
        Returns:
            tuple: (success, output)
        """
        if not self.docker_available:
            raise Exception("Docker is not available. Minitrino requires Docker to be running and accessible.")
        
        cmd = ['minitrino', '-v']  # Add verbose flag
        if command:
            cmd.append(command)
        if args:
            cmd.extend(args)
        
        env = os.environ.copy()
        if env_vars:
            env.update(env_vars)
        
        try:
            logger.info(f"Running minitrino command: {' '.join(cmd)}")
            logger.info(f"With environment: {env_vars}")
            
            result = subprocess.run(cmd, env=env, check=True, capture_output=True, text=True)
            logger.info(f"Command output: {result.stdout}")
            return True, result.stdout
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else str(e)
            logger.error(f"Minitrino command failed: {error_msg}")
            return False, error_msg
        except Exception as e:
            logger.error(f"Error running minitrino command: {str(e)}")
            return False, str(e)
    
    def get_cluster_status(self, cluster_name):
        """Get the status of a cluster
        
        Args:
            cluster_name (str): Name of the cluster
            
        Returns:
            str: Status of the cluster ('running', 'not_found', or 'error')
        """
        if not self.docker_available:
            logger.error("Docker is not available")
            return 'error'
            
        try:
            # Get container status using Docker client
            container = self.client.containers.get(cluster_name)
            if container.status == 'running':
                return 'running'
            return 'not_found'
        except docker.errors.NotFound:
            return 'not_found'
        except Exception as e:
            logger.error(f"Error getting status for cluster {cluster_name}: {str(e)}")
            return 'error'
    
    def get_cluster_version(self, cluster_name):
        """Get the version of a cluster
        
        Args:
            cluster_name (str): Name of the cluster
            
        Returns:
            str: Version of the cluster
        """
        return self.clusters.get(cluster_name, {}).get('version', 'unknown')
    
    def get_cluster_port(self, cluster_name):
        """Get the port of a cluster
        
        Args:
            cluster_name (str): Name of the cluster
            
        Returns:
            int: Port number or 0 if not found
        """
        return self.clusters.get(cluster_name, {}).get('port', 0)
    
    def start_clusters(self, cluster1_config, cluster2_config):
        """Start two Trino clusters
        
        Args:
            cluster1_config (dict): Configuration for first cluster
            cluster2_config (dict): Configuration for second cluster
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.docker_available:
            logger.error("Cannot start clusters: Docker is not available")
            return False
            
        try:
            # Clean up any existing clusters first
            self.cleanup()
            
            logger.info("Starting first Trino cluster (trino1)...")
            success1 = self._start_cluster('trino1', cluster1_config)
            if not success1:
                logger.error("Failed to start first cluster")
                self.cleanup()
                return False
            
            logger.info("Starting second Trino cluster (trino2)...")
            success2 = self._start_cluster('trino2', cluster2_config)
            if not success2:
                logger.error("Failed to start second cluster")
                self.cleanup()
                return False
            
            logger.info("Both clusters started successfully")
            return True
        except Exception as e:
            logger.error(f"Error starting clusters: {str(e)}")
            self.cleanup()
            return False
    
    def _start_cluster(self, cluster_name, config):
        """Start a single cluster using Minitrino
        
        Args:
            cluster_name (str): Name for the cluster
            config (dict): Cluster configuration
        
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.docker_available:
            logger.error("Docker is not available")
            return False
        
        logger.info(f"Starting cluster {cluster_name}...")
        
        try:
            # Store cluster configuration
            self.clusters[cluster_name] = config
            
            # Set up environment variables as a dictionary
            env_vars = {
                "MINITRINO_ENV_NAME": cluster_name,
                "TRINO_VERSION": str(config['version']),
                "TRINO_PORT": str(config['port'])
            }
            
            logger.info(f"Using environment variables: {env_vars}")
            
            # Start base Trino cluster
            logger.info(f"Provisioning base cluster {cluster_name}...")
            success, output = self._run_minitrino_command('provision', env_vars=env_vars)
            if not success:
                logger.error(f"Failed to provision base cluster {cluster_name}: {output}")
                # Try to get container logs if it exists
                try:
                    container = self.client.containers.get(cluster_name)
                    logs = container.logs(tail=100).decode('utf-8')
                    logger.error(f"Container logs for {cluster_name}:\n{logs}")
                except Exception as log_error:
                    logger.error(f"Could not retrieve logs for {cluster_name}: {str(log_error)}")
                return False
                
            # Wait for container to be healthy
            try:
                container = self.client.containers.get(cluster_name)
                logger.info(f"Waiting for {cluster_name} to be healthy...")
                start_time = time.time()
                while time.time() - start_time < 60:  # 60 second timeout
                    container.reload()
                    if container.status == 'running':
                        logs = container.logs(tail=20).decode('utf-8')
                        if "SERVER STARTED" in logs:
                            logger.info(f"Container {cluster_name} is healthy")
                            break
                    time.sleep(2)
                else:
                    logs = container.logs(tail=100).decode('utf-8')
                    logger.error(f"Container {cluster_name} failed to become healthy. Logs:\n{logs}")
                    return False
            except Exception as e:
                logger.error(f"Error waiting for {cluster_name} to be healthy: {str(e)}")
                return False
                
            # Configure catalogs
            for catalog, settings in config.get('catalogs', {}).items():
                if not settings.get('enabled', False):
                    continue
                    
                module = self._get_minitrino_module_name(catalog)
                if not module:
                    logger.warning(f"No Minitrino module found for catalog: {catalog}")
                    continue
                                
                logger.info(f"Provisioning {catalog} catalog for {cluster_name}...")
                success, output = self._run_minitrino_command('provision', ['-m', module], env_vars=env_vars)
                if not success:
                    logger.error(f"Failed to provision {catalog} catalog for {cluster_name}: {output}")
                    # Get container logs after catalog provisioning failure
                    try:
                        container = self.client.containers.get(cluster_name)
                        logs = container.logs(tail=100).decode('utf-8')
                        logger.error(f"Container logs after catalog provisioning failure:\n{logs}")
                    except Exception as log_error:
                        logger.error(f"Could not retrieve logs after catalog failure: {str(log_error)}")
                    return False
                
            logger.info(f"Successfully started cluster {cluster_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error starting cluster {cluster_name}: {str(e)}")
            # Try to get final container logs
            try:
                container = self.client.containers.get(cluster_name)
                logs = container.logs(tail=100).decode('utf-8')
                logger.error(f"Final container logs for {cluster_name}:\n{logs}")
            except Exception as log_error:
                logger.error(f"Could not retrieve final logs: {str(log_error)}")
            return False
    
    def stop_cluster(self, cluster_name):
        """Stop a single cluster
        
        Args:
            cluster_name (str): Name of the cluster to stop
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            logger.info(f"Stopping cluster {cluster_name}...")
            env_vars = {"MINITRINO_ENV_NAME": cluster_name}
            success, output = self._run_minitrino_command('down', env_vars=env_vars)
            if success:
                self.clusters.pop(cluster_name, None)
                logger.info(f"Successfully stopped cluster {cluster_name}")
            else:
                logger.error(f"Failed to stop cluster {cluster_name}: {output}")
            return success
        except Exception as e:
            logger.error(f"Error stopping cluster {cluster_name}: {str(e)}")
            return False
    
    def stop_clusters(self):
        """Stop all clusters
        
        Returns:
            bool: True if successful, False otherwise
        """
        success = True
        for cluster_name in list(self.clusters.keys()):
            if not self.stop_cluster(cluster_name):
                success = False
        return success
    
    def cleanup(self):
        """Clean up all resources"""
        if not self.docker_available:
            return
            
        try:
            # Stop all clusters
            self.stop_clusters()
            
            # Remove any remaining containers
            for container in self.client.containers.list(all=True):
                if container.name.startswith('trino'):
                    try:
                        container.remove(force=True)
                        logger.info(f"Removed container {container.name}")
                    except Exception as e:
                        logger.error(f"Error removing container {container.name}: {str(e)}")
                        
            # Clear cluster configurations
            self.clusters.clear()
            logger.info("Cleanup completed successfully")
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")
    
    def _get_minitrino_module_name(self, catalog_name):
        """Convert catalog name to Minitrino module name
        
        Args:
            catalog_name (str): Name of the catalog
            
        Returns:
            str: Minitrino module name or None if not supported
        """
        # Map catalog names to Minitrino module names
        catalog_modules = {
            'tpch': 'tpch',
            'postgres': 'postgresql',
            'mysql': 'mysql',
            'elasticsearch': 'elasticsearch',
            'iceberg': 'iceberg',
            'hive': 'hive'
        }
        return catalog_modules.get(catalog_name)
    
    def pull_image(self, version, progress_callback=None):
        """Pull a Trino image
        
        Args:
            version (str): Version to pull
            progress_callback (callable, optional): Progress callback
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            env_vars = {f"TRINO_VERSION={version}"}
            success, _ = self._run_minitrino_command('pull', env_vars=env_vars)
            return success
        except Exception as e:
            logger.error(f"Error pulling image: {str(e)}")
            return False
    
    def get_available_images(self):
        """Get list of available Trino images
        
        Returns:
            list: List of available versions
        """
        try:
            success, output = self._run_minitrino_command('list', check_output=True)
            if success and output:
                # Parse output to extract versions
                versions = []
                for line in output.splitlines():
                    if 'trino:' in line:
                        version = line.split('trino:')[1].strip()
                        versions.append(version)
                return versions
            return []
        except Exception as e:
            logger.error(f"Error getting available images: {str(e)}")
            return []
