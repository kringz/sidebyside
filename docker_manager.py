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
    
    def __init__(self):
        """Initialize the Docker client"""
        self.docker_available = False
        self.client = None
        
        if not docker_imported:
            logger.warning("Docker package not available. Running in demo mode.")
            return
            
        try:
            self.client = docker.from_env()
            self.docker_available = True
            logger.info("Docker client initialized successfully")
        except Exception as e:
            logger.error(f"Docker not available: {str(e)}")
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
    
    def pull_trino_image(self, version):
        """Pull a Trino Docker image in advance"""
        if not self.docker_available:
            logger.warning(f"Docker not available, cannot pull Trino image {version}")
            return False
            
        try:
            logger.info(f"Pulling Trino image version {version}...")
            image = self.client.images.pull(f"trinodb/trino:{version}")
            logger.info(f"Successfully pulled Trino image version {version}")
            return True
        except Exception as e:
            logger.error(f"Error pulling Trino image version {version}: {str(e)}")
            return False
            
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
