import os
import yaml
import logging
import tempfile

logger = logging.getLogger(__name__)

# Try to import docker, but handle when it's not available
try:
    import docker
    from docker.errors import DockerException
    docker_imported = True
except ImportError:
    logger.warning("Docker package not installed or not available")
    docker_imported = False
    # Define placeholder for DockerException
    class DockerException(Exception):
        pass

class DockerManager:
    """Manages Docker containers for Trino clusters"""
    
    def __init__(self, socket_path=None, timeout=30, trino_connect_host='localhost'):
        """Initialize the Docker client with configurable connection options
        
        Args:
            socket_path (str, optional): Custom Docker socket path, e.g. 'unix:///var/run/docker.sock' or 'tcp://localhost:2375'
            timeout (int, optional): Timeout for Docker operations in seconds, defaults to 30
            trino_connect_host (str, optional): Hostname used by Trino clients to connect to Trino servers
        """
        self.docker_available = False
        self.client = None
        self.timeout = timeout
        self.trino_connect_host = trino_connect_host
        
        if not docker_imported:
            logger.warning("Docker package not available. Running in demo mode.")
            return
        
        # If a custom socket path is provided, try that first
        if socket_path and socket_path.strip():
            try:
                logger.info(f"Attempting to connect to Docker using custom socket path: {socket_path}")
                self.client = docker.DockerClient(base_url=socket_path, timeout=timeout)
                # Test connection
                self.client.containers.list()
                self.docker_available = True
                logger.info(f"Docker client initialized successfully using custom socket path: {socket_path}")
                return
            except Exception as e:
                logger.warning(f"Cannot connect to Docker using custom socket path ({socket_path}): {str(e)}")
            
        # Try multiple methods to connect to Docker
        # Method 1: Default environment (typically works on Linux with standard Docker setup)
        try:
            self.client = docker.from_env(timeout=timeout)
            # Test connection by listing containers
            self.client.containers.list()
            self.docker_available = True
            logger.info("Docker client initialized successfully using default environment")
            return
        except Exception as e:
            logger.warning(f"Cannot connect to Docker using default environment: {str(e)}")
            
        # Method 2: Try using Docker host from environment variable (common for Docker Machine/Docker Desktop)
        docker_host = os.environ.get('DOCKER_HOST')
        if docker_host:
            try:
                self.client = docker.DockerClient(base_url=docker_host, timeout=timeout)
                # Test connection
                self.client.containers.list()
                self.docker_available = True
                logger.info(f"Docker client initialized successfully using DOCKER_HOST: {docker_host}")
                return
            except Exception as e:
                logger.warning(f"Cannot connect to Docker using DOCKER_HOST ({docker_host}): {str(e)}")
        
        # Method 3: Try common Docker socket paths (macOS, Windows with WSL)
        socket_paths = [
            'unix:///var/run/docker.sock',      # Standard Linux/macOS
            'unix:///run/docker.sock',          # Some Linux distros
            'tcp://localhost:2375',             # Docker without TLS
            'tcp://127.0.0.1:2375',             # Alternative localhost format
            'tcp://host.docker.internal:2375',  # Docker Desktop for Mac/Windows
            'npipe:////./pipe/docker_engine'    # Windows named pipe
        ]
        
        for socket_path in socket_paths:
            try:
                self.client = docker.DockerClient(base_url=socket_path, timeout=timeout)
                # Test connection
                self.client.containers.list()
                self.docker_available = True
                logger.info(f"Docker client initialized successfully using socket: {socket_path}")
                return
            except Exception:
                # Just try the next path without logging each failure
                continue
        
        # If we get here, Docker is not available
        logger.error("Docker not available: Could not connect to Docker with any method")
        logger.info("Running in demo mode (Docker functionality disabled)")
    
    def get_container_status(self, container_name):
        """Get the status of a container"""
        if not self.docker_available:
            return "not_available"
            
        try:
            container = self.client.containers.get(container_name)
            return container.status
        except docker.errors.NotFound:
            return "not_found"
        except Exception as e:
            logger.error(f"Error getting container status for {container_name}: {str(e)}")
            return "error"
    
    def start_trino_cluster(self, container_name, version, port, catalogs_config):
        """Start a Trino cluster with the specified version and catalogs"""
        if not self.docker_available:
            logger.warning(f"Docker not available, cannot start Trino cluster {container_name}")
            raise RuntimeError("Docker is not available in this environment")
            
        try:
            # Always ensure TPC-H catalog is enabled
            if 'tpch' not in catalogs_config:
                logger.info(f"Adding missing TPC-H catalog to configuration for {container_name}")
                catalogs_config['tpch'] = {
                    'enabled': True,
                    'column_naming': 'SIMPLIFIED'
                }
            elif not catalogs_config['tpch'].get('enabled', False):
                logger.info(f"Enabling TPC-H catalog for {container_name}")
                catalogs_config['tpch']['enabled'] = True
                
            # Check if container already exists
            try:
                container = self.client.containers.get(container_name)
                # If it exists, remove it
                logger.info(f"Container {container_name} already exists, removing it...")
                container.remove(force=True)
                logger.info(f"Container {container_name} removed")
            except docker.errors.NotFound:
                pass
            
            # Create temp directory for config
            config_dir = tempfile.mkdtemp(prefix="trino_")
            
            # Create necessary directories
            os.makedirs(f"{config_dir}/catalog", exist_ok=True)
            
            # Create Trino config files
            with open(f"{config_dir}/config.properties", "w") as f:
                f.write("coordinator=true\n")
                f.write("node-scheduler.include-coordinator=true\n")
                f.write("http-server.http.port=8080\n")
                f.write("discovery-server.enabled=true\n")
                f.write("discovery.uri=http://localhost:8080\n")
            
            # Create JVM config
            with open(f"{config_dir}/jvm.config", "w") as f:
                f.write("-server\n")
                f.write("-Xmx4G\n")
                f.write("-XX:+UseG1GC\n")
                f.write("-XX:G1HeapRegionSize=32M\n")
                f.write("-XX:+UseGCOverheadLimit\n")
                f.write("-XX:+ExplicitGCInvokesConcurrent\n")
                f.write("-XX:+HeapDumpOnOutOfMemoryError\n")
                f.write("-XX:+ExitOnOutOfMemoryError\n")
            
            # Create node properties
            with open(f"{config_dir}/node.properties", "w") as f:
                f.write("node.environment=test\n")
                f.write(f"node.id={container_name}\n")
                f.write("node.data-dir=/data/trino\n")
            
            # Create catalog config files
            for catalog_name, catalog_config in catalogs_config.items():
                if catalog_config.get('enabled', False):
                    catalog_file_path = f"{config_dir}/catalog/{catalog_name}.properties"
                    
                    # Generate catalog properties based on catalog type
                    if catalog_name == 'hive':
                        with open(catalog_file_path, "w") as f:
                            f.write("connector.name=hive\n")
                            f.write(f"hive.metastore.uri=thrift://{catalog_config.get('metastore_host', 'localhost')}:{catalog_config.get('metastore_port', '9083')}\n")
                            f.write("hive.allow-drop-table=true\n")
                            f.write("hive.allow-rename-table=true\n")
                    
                    elif catalog_name == 'mysql':
                        with open(catalog_file_path, "w") as f:
                            f.write("connector.name=mysql\n")
                            f.write(f"connection-url=jdbc:mysql://{catalog_config.get('host', 'localhost')}:{catalog_config.get('port', '3306')}\n")
                            f.write(f"connection-user={catalog_config.get('user', 'root')}\n")
                            if catalog_config.get('password'):
                                f.write(f"connection-password={catalog_config.get('password')}\n")
                    
                    elif catalog_name == 'elasticsearch':
                        with open(catalog_file_path, "w") as f:
                            f.write("connector.name=elasticsearch\n")
                            f.write(f"elasticsearch.host={catalog_config.get('host', 'localhost')}\n")
                            f.write(f"elasticsearch.port={catalog_config.get('port', '9200')}\n")
                            f.write("elasticsearch.default-schema-name=default\n")
                    
                    elif catalog_name == 'tpch':
                        with open(catalog_file_path, "w") as f:
                            f.write("connector.name=tpch\n")
                            # Optional configuration for column naming
                            if catalog_config.get('column_naming'):
                                f.write(f"tpch.column-naming={catalog_config.get('column_naming')}\n")
                            # Output debug information about the TPC-H catalog creation
                            logger.info(f"Created TPC-H catalog configuration with column naming: {catalog_config.get('column_naming', 'DEFAULT')}")
                    
                    logger.info(f"Created catalog config for {catalog_name}")
            
            # Start Trino container
            logger.info(f"Starting Trino {version} container {container_name} on port {port}...")
            container = self.client.containers.run(
                f"trinodb/trino:{version}",
                name=container_name,
                ports={'8080/tcp': port},
                volumes={
                    config_dir: {'bind': '/etc/trino', 'mode': 'rw'}
                },
                detach=True
            )
            
            logger.info(f"Trino container {container_name} started successfully")
            return container
        
        except Exception as e:
            logger.error(f"Error starting Trino container {container_name}: {str(e)}")
            raise RuntimeError(f"Failed to start Trino container: {str(e)}")
    
    def pull_trino_image(self, version, progress_callback=None):
        """Pull a Trino Docker image in advance
        
        Args:
            version (str): The Trino version to pull
            progress_callback (function, optional): A callback function to report progress.
                The function should accept a float between 0 and 1 representing progress percentage.
        
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.docker_available:
            logger.warning(f"Docker not available, cannot pull Trino image {version}")
            if progress_callback:
                # Even in demo mode, send some progress
                import threading
                import time
                
                def simulate_progress():
                    # Simulate progress in demo mode
                    for i in range(11):
                        progress = i / 10.0
                        progress_callback(progress)
                        time.sleep(0.5)
                
                # Start a thread to simulate progress
                thread = threading.Thread(target=simulate_progress)
                thread.daemon = True
                thread.start()
                
            return False
            
        try:
            logger.info(f"Pulling Trino image version {version}...")
            
            # Check if image already exists
            existing_images = self.get_available_trino_images()
            if version in existing_images:
                logger.info(f"Trino image version {version} already exists, skipping pull")
                if progress_callback:
                    progress_callback(1.0)  # Complete
                return True
            
            # Pull with progress tracking if callback provided
            if progress_callback:
                # Send initial progress
                progress_callback(0.0)
                
                try:
                    # Using low-level API to get progress updates
                    last_progress = 0.0
                    total_layers = 0
                    completed_layers = 0
                    layer_progress = {}
                    
                    for line in self.client.api.pull(f"trinodb/trino:{version}", stream=True, decode=True):
                        # Skip empty lines
                        if not line:
                            continue
                            
                        # Log the raw line for debugging
                        logger.debug(f"Docker pull progress: {line}")
                        
                        # Handle status updates
                        if 'id' in line and 'status' in line:
                            layer_id = line['id']
                            status = line['status']
                            
                            # Track layer count
                            if layer_id not in layer_progress:
                                layer_progress[layer_id] = 0.0
                                total_layers += 1
                            
                            # Update layer progress
                            if 'progressDetail' in line and 'current' in line['progressDetail'] and 'total' in line['progressDetail']:
                                current = float(line['progressDetail']['current'])
                                total = float(line['progressDetail']['total'])
                                if total > 0:
                                    layer_progress[layer_id] = current / total
                            
                            # Mark completed layers
                            if status in ['Download complete', 'Pull complete', 'Already exists', 'Verifying Checksum']:
                                layer_progress[layer_id] = 1.0
                                completed_layers += 1
                        
                        # Calculate overall progress
                        if total_layers > 0:
                            if completed_layers == total_layers:
                                overall_progress = 1.0
                            else:
                                # Average progress of all layers
                                overall_progress = sum(layer_progress.values()) / total_layers
                            
                            # Only update if progress has changed significantly
                            if overall_progress - last_progress >= 0.01 or overall_progress >= 1.0:
                                last_progress = overall_progress
                                logger.debug(f"Pull progress for {version}: {overall_progress:.1%}")
                                progress_callback(overall_progress)
                    
                    # Final update to ensure 100% is reported
                    progress_callback(1.0)
                    
                except Exception as e:
                    logger.error(f"Error tracking pull progress: {str(e)}")
                    # Continue with standard pull
                    image = self.client.images.pull(f"trinodb/trino:{version}")
                    progress_callback(1.0)  # Mark as complete
            else:
                # Standard pull without progress tracking
                image = self.client.images.pull(f"trinodb/trino:{version}")
                
            logger.info(f"Successfully pulled Trino image version {version}")
            return True
        except Exception as e:
            logger.error(f"Error pulling Trino image version {version}: {str(e)}")
            if progress_callback:
                # Send final error status
                progress_callback(0.0)  # Reset to 0 to indicate failure
            return False
            
    def get_available_trino_images(self):
        """Get a list of available Trino Docker images"""
        if not self.docker_available:
            logger.warning("Docker not available, cannot get list of Trino images")
            return []
            
        try:
            logger.info("Getting list of available Trino images...")
            images = self.client.images.list(name="trinodb/trino")
            # Extract tags from images
            trino_versions = []
            for image in images:
                if image.tags:
                    for tag in image.tags:
                        if 'trinodb/trino:' in tag:
                            version = tag.split(':')[1]
                            trino_versions.append(version)
            
            logger.info(f"Found {len(trino_versions)} Trino images: {', '.join(trino_versions)}")
            return trino_versions
        except Exception as e:
            logger.error(f"Error getting list of Trino images: {str(e)}")
            return []
    
    def stop_trino_cluster(self, container_name):
        """Stop and remove a Trino cluster"""
        if not self.docker_available:
            logger.warning(f"Docker not available, cannot stop Trino cluster {container_name}")
            return
            
        try:
            container = self.client.containers.get(container_name)
            logger.info(f"Stopping Trino container {container_name}...")
            container.stop()
            container.remove()
            logger.info(f"Trino container {container_name} stopped and removed")
        except docker.errors.NotFound:
            logger.info(f"Container {container_name} not found")
        except Exception as e:
            logger.error(f"Error stopping Trino container {container_name}: {str(e)}")
            raise RuntimeError(f"Failed to stop Trino container: {str(e)}")
