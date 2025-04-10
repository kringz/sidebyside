import os
import yaml
import logging
import tempfile
import time
import json
import threading
import random

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
            
            # Create Trino config files with different internal HTTP ports based on container
            # Use 8080 for first container and 8081 for second to avoid port conflicts
            internal_http_port = 8080
            if "2" in container_name:
                internal_http_port = 8081
                
            with open(f"{config_dir}/config.properties", "w") as f:
                f.write("coordinator=true\n")
                f.write("node-scheduler.include-coordinator=true\n")
                f.write(f"http-server.http.port={internal_http_port}\n")
                f.write("discovery-server.enabled=true\n")
                f.write(f"discovery.uri=http://localhost:{internal_http_port}\n")
                
            logger.info(f"Configured Trino {container_name} with internal HTTP port {internal_http_port}")
            
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
            
            # Define postgres_container_name upfront
            # Will be updated later if a PostgreSQL container is created
            postgres_container_name = None
            
            # If PostgreSQL catalog is enabled, prepare to create a dedicated container
            use_postgres = False
            postgres_config = None
            if catalogs_config:  # Check if catalogs_config is not None
                for catalog_name, catalog_config in catalogs_config.items():
                    if catalog_name == 'postgres' and catalog_config.get('enabled', False):
                        use_postgres = True
                        postgres_config = catalog_config
                        # Create a unique container name based on the Trino container name
                        postgres_container_name = f"postgres-for-{container_name}"
                        logger.info(f"PostgreSQL catalog enabled - will use container {postgres_container_name}")
                        break
            
            # Create catalog config files
            for catalog_name, catalog_config in catalogs_config.items():
                if catalog_config.get('enabled', False):
                    catalog_file_path = f"{config_dir}/catalog/{catalog_name}.properties"
                    logger.info(f"Creating catalog file for {catalog_name} at {catalog_file_path}")
                    
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
                    
                    elif catalog_name == 'postgres':
                        # Special handling for PostgreSQL with our dedicated container
                        # Default fallback values (for when not using Docker)
                        host = catalog_config.get('host', 'localhost')
                        port = catalog_config.get('port', '5432')
                        user = catalog_config.get('user', 'postgres')
                        password = catalog_config.get('password', 'postgres')
                        database = catalog_config.get('database', 'postgres')
                
                        # If we're using Docker, we need to ensure consistent credentials
                        # across both the PostgreSQL container and the catalog configuration
                        if self.docker_available:
                            # Ensure that we're always using the secure default if not explicitly configured
                            # This ensures consistency with the PostgreSQL container setup
                            password = catalog_config.get('password') if catalog_config.get('password') else 'postgres123'
                            
                            # Log the PostgreSQL catalog settings for debugging
                            logger.info(f"PostgreSQL catalog settings for container {container_name}: host={host}, port={port}, user={user}, database={database}")
                        
                        # If we have a dedicated PostgreSQL container for this Trino cluster,
                        # use its container_name and port
                        if postgres_container_name and "1" in container_name:
                            # For the first Trino cluster (trino1), use the first PostgreSQL container
                            host = postgres_container_name
                            logger.info(f"Updated PostgreSQL connection for {container_name} to use container {host}")
                        elif postgres_container_name and "2" in container_name:
                            # For the second Trino cluster (trino2), use the second PostgreSQL container
                            host = postgres_container_name
                            logger.info(f"Updated PostgreSQL connection for {container_name} to use container {host}")
                        
                        # Create the PostgreSQL catalog config
                        with open(catalog_file_path, "w") as f:
                            f.write("connector.name=postgresql\n")
                            # Note: Inside Docker containers, we need to use the Docker container name as the hostname
                            # and ensure we're using the internal PostgreSQL port (5432) not the host-mapped port
                            f.write(f"connection-url=jdbc:postgresql://{host}:5432/{database}\n")
                            f.write(f"connection-user={user}\n")
                            f.write(f"connection-password={password}\n")
                            
                        logger.info(f"Created PostgreSQL catalog configuration at {catalog_file_path} with host {host}, port {port}, database {database}, and user {user}")
                    
                    elif catalog_name == 'tpch':
                        with open(catalog_file_path, "w") as f:
                            f.write("connector.name=tpch\n")
                            # Optional configuration for column naming
                            if catalog_config.get('column_naming'):
                                f.write(f"tpch.column-naming={catalog_config.get('column_naming')}\n")
                        # Output debug information about the TPC-H catalog creation
                        logger.info(f"Created TPC-H catalog configuration with column naming: {catalog_config.get('column_naming', 'DEFAULT')}")
                    
                    elif catalog_name == 'iceberg':
                        # In Docker, the hostname is the container name
                        if self.docker_available:
                            iceberg_rest_host = f"iceberg-rest-for-{container_name}"
                            s3_endpoint = f"http://s3.us-east-1.minio.com:9000"
                        else:
                            # In non-Docker mode, use localhost
                            iceberg_rest_host = catalog_config.get('rest_host', 'localhost')
                            s3_endpoint = catalog_config.get('s3_endpoint', 'http://localhost:9000')
                        
                        # Determine the Trino version number
                        version_num = 0
                        try:
                            version_num = int(version)
                        except ValueError:
                            # If version can't be converted to int, assume older version
                            pass
                            
                        # For Trino 474+, we need a completely different configuration
                        if version_num >= 474:
                            logger.info(f"Trino version {version} >= 474, using new Iceberg catalog configuration")
                            
                            with open(catalog_file_path, "w") as f:
                                # For Trino 474+, use a simpler configuration focusing only on REST catalog
                                # without any S3 or Hadoop settings directly in the catalog properties
                                f.write("connector.name=iceberg\n")
                                f.write("iceberg.catalog.type=rest\n")
                                f.write(f"iceberg.rest-catalog.uri=http://{iceberg_rest_host}:8181\n")
                                f.write("iceberg.rest-catalog.warehouse=s3://sample-bucket/wh/\n")
                                
                                # Add AWS region and credentials for 474+ based on minitrino configuration
                                f.write("iceberg.aws.region=us-east-1\n")
                                f.write("iceberg.aws.access-key=access-key\n")
                                f.write("iceberg.aws.secret-key=secret-key\n")
                                f.write("iceberg.aws.s3.path-style-access=true\n")
                                
                                # In 474+, S3 credentials need to be provided differently
                                # These are now handled by the REST Iceberg catalog service and specific Iceberg AWS properties
                        
                        # For Trino versions 458-473, use intermediate configuration
                        elif version_num >= 458:
                            logger.info(f"Trino version {version} >= 458 and < 474, using intermediate S3 configuration")
                            
                            with open(catalog_file_path, "w") as f:
                                f.write("connector.name=iceberg\n")
                                f.write("iceberg.catalog.type=rest\n")
                                f.write(f"iceberg.rest-catalog.uri=http://{iceberg_rest_host}:8181\n")
                                f.write("iceberg.rest-catalog.warehouse=s3://sample-bucket/wh/\n")
                                
                                # Native S3 filesystem properties for Trino versions 458-473
                                f.write("s3.endpoint=http://s3.us-east-1.minio.com:9000\n")
                                f.write("s3.aws-access-key=access-key\n")
                                f.write("s3.aws-secret-key=secret-key\n")
                                f.write("s3.path-style-access=true\n")
                                f.write("s3.region=us-east-1\n")
                                # Version 473 specifically doesn't support s3.ssl.enabled
                                try:
                                    # Only include this property for versions below 473
                                    if version_num < 473:
                                        f.write("s3.ssl.enabled=false\n")
                                except:
                                    # In case of an error, omit the property
                                    pass
                                f.write("fs.native-s3.enabled=true\n")
                        
                        # For older Trino versions, use the legacy Hive S3 configuration
                        else:
                            logger.info(f"Trino version {version} < 458, using legacy Hive S3 configuration")
                            
                            with open(catalog_file_path, "w") as f:
                                f.write("connector.name=iceberg\n")
                                f.write("iceberg.catalog.type=rest\n")
                                f.write(f"iceberg.rest-catalog.uri=http://{iceberg_rest_host}:8181\n")
                                f.write("iceberg.rest-catalog.warehouse=s3://sample-bucket/wh/\n")
                                f.write("hive.s3.endpoint=http://s3.us-east-1.minio.com:9000\n")
                                f.write("hive.s3.region=us-east-1\n")
                                f.write("hive.s3.aws-access-key=access-key\n")
                                f.write("hive.s3.aws-secret-key=secret-key\n")
                                f.write("hive.s3.path-style-access=true\n")

                                
                        logger.info(f"Created Iceberg catalog configuration at {catalog_file_path}")
                    
                    # Log that we created the catalog config
                    logger.info(f"Created catalog config for {catalog_name}")
            
            # Start Trino container
            logger.info(f"Starting Trino {version} container {container_name} on port {port}...")
            
            # Check if PostgreSQL catalog is enabled
            use_postgres = False
            postgres_config = None
            if catalogs_config:  # Check if catalogs_config is not None
                for catalog_name, catalog_config in catalogs_config.items():
                    if catalog_name == 'postgres' and catalog_config.get('enabled', False):
                        use_postgres = True
                        postgres_config = catalog_config
                        logger.info("PostgreSQL catalog enabled - will start dedicated PostgreSQL container")
                        break
                        
            # If PostgreSQL is enabled, start a dedicated PostgreSQL container for this Trino cluster
            postgres_container_name = None
            if use_postgres and postgres_config:
                # Create a unique container name based on the Trino container name
                postgres_container_name = f"postgres-for-{container_name}"
                postgres_port = 5432  # Default PostgreSQL port
                
                # Create and start the PostgreSQL container
                try:
                    # First check if container already exists
                    try:
                        existing_container = self.client.containers.get(postgres_container_name)
                        # If it exists but not running, remove it
                        if existing_container.status != 'running':
                            logger.info(f"Found non-running PostgreSQL container {postgres_container_name}, removing it")
                            existing_container.remove(force=True)
                            existing_container = None
                        else:
                            logger.info(f"PostgreSQL container {postgres_container_name} already running")
                    except docker.errors.NotFound:
                        existing_container = None
                    
                    # Start new container if needed
                    if existing_container is None:
                        logger.info(f"Starting PostgreSQL container {postgres_container_name}")
                        
                        # Environment variables for the PostgreSQL container
                        # Ensure the password is definitely not empty
                        pg_password = postgres_config.get('password') if postgres_config and postgres_config.get('password') else 'postgres123'
                        pg_user = postgres_config.get('user', 'postgres') if postgres_config else 'postgres'
                        pg_db = postgres_config.get('database', 'postgres') if postgres_config else 'postgres'
                        
                        # Set environment variables with guaranteed non-empty password
                        pg_env = {
                            "POSTGRES_PASSWORD": pg_password,  # Using a strong default if none provided
                            "POSTGRES_USER": pg_user,
                            "POSTGRES_DB": pg_db,
                            # Add this for easier debugging - allow connections via password auth for all
                            "POSTGRES_HOST_AUTH_METHOD": "md5"
                        }
                        
                        logger.info(f"Initializing PostgreSQL container {postgres_container_name} with user {pg_user} and database {pg_db}")
                        
                        # Determine a suggested port based on container name to avoid conflicts
                        # This helps distinguish between PostgreSQL containers for different Trino instances
                        suggested_pg_port = None
                        if "2" in postgres_container_name:
                            suggested_pg_port = 5433  # Use 5433 for second cluster's PostgreSQL
                        else:
                            suggested_pg_port = 5432  # Use 5432 for first cluster's PostgreSQL
                            
                        # But still allow Docker to reassign if these are also in use
                        pg_ports = {'5432/tcp': suggested_pg_port}
                        
                        # Create a network name for this cluster to ensure container connectivity
                        network_name = f"trino-network-{container_name}"
                        
                        # Create a dedicated network for this cluster if it doesn't exist
                        try:
                            # Check if the network already exists
                            try:
                                existing_network = self.client.networks.get(network_name)
                                logger.info(f"Using existing Docker network: {network_name}")
                            except docker.errors.NotFound:
                                # Create a new network
                                existing_network = self.client.networks.create(
                                    name=network_name,
                                    driver="bridge",
                                    check_duplicate=True
                                )
                                logger.info(f"Created new Docker network: {network_name}")
                        except Exception as e:
                            logger.warning(f"Error setting up Docker network: {str(e)}")
                            network_name = None  # Fall back to default bridge network
                        
                        # Prepare container options
                        container_options = {
                            "name": postgres_container_name,
                            "environment": pg_env,
                            "ports": pg_ports,  # Use our cluster-specific suggested port
                            "detach": True,
                            # Add health check with retries to ensure container stays running
                            "healthcheck": {
                                "test": ["CMD-SHELL", "pg_isready -U postgres"],
                                "interval": 2000000000,  # 2 seconds in nanoseconds
                                "timeout": 1000000000,   # 1 second in nanoseconds
                                "retries": 5,
                                "start_period": 5000000000  # 5 seconds in nanoseconds
                            },
                            # Add host mounts for data persistence
                            "volumes": {
                                f"{postgres_container_name}-data": {"bind": "/var/lib/postgresql/data", "mode": "rw"}
                            },
                            # Ensure the container is restarted if it fails
                            "restart_policy": {"Name": "on-failure", "MaximumRetryCount": 5}
                        }
                        
                        # Only add network specification if we have a valid network
                        if network_name:
                            container_options["network"] = network_name
                        
                        # Start PostgreSQL container with improved stability
                        pg_container = self.client.containers.run(
                            "postgres:13",  # Standard PostgreSQL image
                            **container_options
                        )
                        
                        logger.info(f"Started PostgreSQL container {postgres_container_name}")
                        
                        # Wait a moment to let the container initialize
                        time.sleep(2)
                        
                        # Get the assigned host port - retry a few times if needed
                        retry_count = 0
                        max_retries = 5
                        postgres_port = None
                        
                        while retry_count < max_retries:
                            try:
                                pg_container.reload()
                                host_port_config = pg_container.attrs['NetworkSettings']['Ports']['5432/tcp'][0]
                                postgres_port = int(host_port_config['HostPort'])
                                logger.info(f"PostgreSQL container {postgres_container_name} is running on port {postgres_port}")
                                break
                            except (KeyError, IndexError, TypeError) as e:
                                retry_count += 1
                                logger.warning(f"Error getting port for PostgreSQL container (attempt {retry_count}/{max_retries}): {str(e)}")
                                time.sleep(2)
                        
                        if postgres_port is None:
                            logger.error(f"Failed to get port for PostgreSQL container {postgres_container_name}")
                            raise RuntimeError(f"Failed to get port for PostgreSQL container {postgres_container_name}")
                        
                        # Verify the container is still running
                        pg_container.reload()
                        if pg_container.status != 'running':
                            logger.error(f"PostgreSQL container {postgres_container_name} stopped unexpectedly with status: {pg_container.status}")
                            # Check container logs for the cause
                            logs = pg_container.logs().decode('utf-8')
                            logger.error(f"PostgreSQL container logs: {logs}")
                            raise RuntimeError(f"PostgreSQL container {postgres_container_name} stopped unexpectedly")
                        
                        # Wait for PostgreSQL to be ready (simple exponential backoff)
                        self._wait_for_postgres_ready(pg_container, postgres_container_name, max_attempts=15)
                        
                        # Seed the PostgreSQL container with sample data
                        # Use the same credentials we used for setting up the container
                        self._seed_postgres_container(pg_container, postgres_container_name, 
                                                     pg_user,
                                                     pg_password,
                                                     pg_db)
                        
                except Exception as e:
                    logger.error(f"Error starting PostgreSQL container: {str(e)}")
                    # Continue anyway, as we might be able to connect to an existing PostgreSQL instance
            
            # Check if Iceberg catalog is enabled
            use_iceberg = False
            iceberg_config = None
            minio_container_name = None
            iceberg_rest_container_name = None
            
            if catalogs_config:  # Check if catalogs_config is not None
                for catalog_name, catalog_config in catalogs_config.items():
                    if catalog_name == 'iceberg' and catalog_config.get('enabled', False):
                        use_iceberg = True
                        iceberg_config = catalog_config
                        # Create unique container names based on the Trino container name
                        iceberg_rest_container_name = f"iceberg-rest-for-{container_name}"
                        minio_container_name = f"minio-for-{container_name}"
                        logger.info(f"Iceberg catalog enabled - will use containers {iceberg_rest_container_name} and {minio_container_name}")
                        break
            
            # If Iceberg catalog is enabled, start the necessary containers
            if use_iceberg and iceberg_config and self.docker_available:
                try:
                    # 1. Create a dedicated network for this cluster if it doesn't exist
                    network_name = f"trino-network-{container_name}"
                    try:
                        # Check if the network already exists
                        try:
                            existing_network = self.client.networks.get(network_name)
                            logger.info(f"Using existing Docker network: {network_name}")
                        except docker.errors.NotFound:
                            # Create a new network
                            existing_network = self.client.networks.create(
                                name=network_name,
                                driver="bridge",
                                check_duplicate=True
                            )
                            logger.info(f"Created new Docker network: {network_name}")
                    except Exception as e:
                        logger.warning(f"Error setting up Docker network: {str(e)}")
                        network_name = None  # Fall back to default bridge network
                    
                    # 2. Start the MinIO container
                    # First check if container already exists
                    try:
                        existing_minio = self.client.containers.get(minio_container_name)
                        if existing_minio.status != 'running':
                            logger.info(f"Found non-running MinIO container {minio_container_name}, removing it")
                            existing_minio.remove(force=True)
                            existing_minio = None
                        else:
                            logger.info(f"MinIO container {minio_container_name} already running")
                    except docker.errors.NotFound:
                        existing_minio = None
                    
                    # Start MinIO container if needed
                    if existing_minio is None:
                        logger.info(f"Starting MinIO container {minio_container_name}")
                        
                        minio_env = {
                            "MINIO_ROOT_USER": "access-key",
                            "MINIO_ROOT_PASSWORD": "secret-key",
                            "MINIO_DOMAIN": "s3.us-east-1.minio.com",
                            # Add region settings to match AWS_REGION
                            "MINIO_REGION_NAME": "us-east-1",
                            "MINIO_REGION": "us-east-1",
                            # Allow web browser access for debugging
                            "MINIO_BROWSER": "on"
                        }
                        
                        # Determine suggested port based on the container name
                        suggested_minio_port = 9000 if "1" in container_name else 9001
                        minio_ports = {
                            '9000/tcp': suggested_minio_port,  # S3 API port
                            '9003/tcp': suggested_minio_port + 3  # Console port
                        }
                        
                        # Add network aliases for virtual-style paths
                        network_config = {}
                        if network_name:
                            network_config = {
                                network_name: {
                                    "aliases": [
                                        "s3.us-east-1.minio.com",
                                        "sample-bucket.s3.us-east-1.minio.com"
                                    ]
                                }
                            }
                        
                        minio_options = {
                            "name": minio_container_name,
                            "environment": minio_env,
                            "ports": minio_ports,
                            "detach": True,
                            "command": "server --address :9000 --console-address :9003 /data",
                            "volumes": {
                                f"{minio_container_name}-data": {"bind": "/data", "mode": "rw"}
                            },
                            "restart_policy": {"Name": "on-failure", "MaximumRetryCount": 5}
                        }
                        
                        # Add network configuration if available
                        if network_name:
                            minio_options["networks"] = network_config
                        
                        # Start MinIO container
                        minio_container = self.client.containers.run(
                            "minio/minio:latest",
                            **minio_options
                        )
                        
                        logger.info(f"Started MinIO container {minio_container_name}")
                        time.sleep(2)  # Give it a moment to start up
                    
                    # 3. Start the bucket creation container
                    bucket_creator_name = f"create-buckets-for-{container_name}"
                    try:
                        existing_creator = self.client.containers.get(bucket_creator_name)
                        logger.info(f"Bucket creator container {bucket_creator_name} already exists, removing it")
                        existing_creator.remove(force=True)
                    except docker.errors.NotFound:
                        pass
                    
                    # Start a new bucket creation container
                    bucket_creator_cmd = (
                        "/bin/sh -c '"
                        "mc alias set minio http://%s:9000 access-key secret-key && "
                        "mc mb --region us-east-1 minio/sample-bucket && "
                        "mc mb --region us-east-1 minio/sample-bucket/wh/ && "
                        "mc policy set public minio/sample-bucket && "
                        "echo \"MinIO buckets created successfully with region us-east-1\" && "
                        "tail -f /dev/null'"
                    ) % minio_container_name
                    
                    logger.info(f"Starting bucket creator container with command: {bucket_creator_cmd}")
                    
                    bucket_creator_options = {
                        "name": bucket_creator_name,
                        "detach": True,
                        "remove": True,  # Remove container when it exits
                        "entrypoint": "/bin/sh",
                        "command": ["-c", bucket_creator_cmd.replace("'", "")]
                    }
                    
                    # Add to network if available
                    if network_name:
                        bucket_creator_options["network"] = network_name
                    
                    bucket_creator = self.client.containers.run(
                        "minio/mc:latest",
                        **bucket_creator_options
                    )
                    
                    logger.info(f"Started bucket creator container {bucket_creator_name}")
                    time.sleep(5)  # Give MinIO time to start and the bucket to be created
                    
                    # 4. Start Iceberg REST service container
                    try:
                        existing_iceberg = self.client.containers.get(iceberg_rest_container_name)
                        if existing_iceberg.status != 'running':
                            logger.info(f"Found non-running Iceberg REST container {iceberg_rest_container_name}, removing it")
                            existing_iceberg.remove(force=True)
                            existing_iceberg = None
                        else:
                            logger.info(f"Iceberg REST container {iceberg_rest_container_name} already running")
                    except docker.errors.NotFound:
                        existing_iceberg = None
                    
                    # Start Iceberg REST container if needed
                    if existing_iceberg is None:
                        logger.info(f"Starting Iceberg REST container {iceberg_rest_container_name}")
                        
                        iceberg_env = {
                            "AWS_ACCESS_KEY_ID": "access-key",
                            "AWS_SECRET_ACCESS_KEY": "secret-key",
                            "AWS_REGION": "us-east-1",
                            "AWS_DEFAULT_REGION": "us-east-1",  # Add explicit default region
                            "CATALOG_URI": "jdbc:sqlite:/home/iceberg/iceberg.db",
                            "CATALOG_WAREHOUSE": "s3://sample-bucket/wh/",
                            "CATALOG_IO__IMPL": "org.apache.iceberg.aws.s3.S3FileIO",
                            "CATALOG_S3_ENDPOINT": "http://s3.us-east-1.minio.com:9000",
                            "CATALOG_S3_PATH_STYLE_ACCESS": "true",
                            "CATALOG_S3_SSL_ENABLED": "false"
                        }
                        
                        # Add additional configurations for version 474+ compatibility
                        try:
                            version_num = int(version)
                            if version_num >= 474:
                                logger.info(f"Using enhanced REST catalog configuration for Trino {version}")
                                # These additional settings help with Trino 474+ compatibility
                                iceberg_env.update({
                                    "AWS_S3_PATH_STYLE_ACCESS": "true",
                                    "S3_USE_PATH_STYLE_ACCESS": "true",
                                    "CATALOG_WAREHOUSE_LOCATION": "s3://sample-bucket/wh/",
                                    "REST_CATALOG_CONFIG_OVERRIDE_REST_CATALOG_WAREHOUSE": "s3://sample-bucket/wh/"
                                })
                        except ValueError:
                            pass
                        
                        # Determine a suggested port based on the container name
                        suggested_iceberg_port = 8181 if "1" in container_name else 8182
                        
                        iceberg_options = {
                            "name": iceberg_rest_container_name,
                            "environment": iceberg_env,
                            "ports": {'8181/tcp': suggested_iceberg_port},
                            "detach": True,
                            "volumes": {
                                f"{iceberg_rest_container_name}-metadata": {"bind": "/home/iceberg", "mode": "rw"}
                            },
                            "restart_policy": {"Name": "on-failure", "MaximumRetryCount": 5}
                        }
                        
                        # Add to network if available
                        if network_name:
                            iceberg_options["network"] = network_name
                        
                        # Start Iceberg REST container
                        # For Trino 474+, use a newer image compatible with the REST catalog API changes
                        iceberg_image = "tabulario/iceberg-rest:latest"
                        try:
                            version_num = int(version)
                            if version_num >= 474:
                                # Use a more compatible image for Trino 474+
                                iceberg_image = "tabular/iceberg-rest:0.15.0"
                                logger.info(f"Using updated Iceberg REST image for Trino {version}: {iceberg_image}")
                        except ValueError:
                            pass
                            
                        iceberg_container = self.client.containers.run(
                            iceberg_image,
                            **iceberg_options
                        )
                        
                        logger.info(f"Started Iceberg REST container {iceberg_rest_container_name}")
                        time.sleep(5)  # Give it time to initialize
                    
                    logger.info(f"Iceberg containers set up successfully for Trino cluster {container_name}")
                    
                except Exception as e:
                    logger.error(f"Error setting up Iceberg containers: {str(e)}")
                    # Continue anyway, as we might be able to connect to existing Iceberg services
            
            # Always set different internal HTTP ports for each container to avoid conflicts
            internal_http_port = 8081 if "2" in container_name else 8080
            
            # Always ensure port is an integer for comparisons
            try:
                port = int(port)
            except (ValueError, TypeError):
                # If port can't be converted to int, use a safe default
                logger.warning(f"Invalid port value: {port}, using default port")
                port = 8081 if "2" in container_name else 8080
            
            # Also use different external ports for each Trino cluster to avoid conflicts
            # Ensure Trino never uses ports that might conflict with PostgreSQL (5432/5433)
            # First cluster starts at 8080, second at 8081 by default
            if "2" in container_name and port <= 8080:
                # Second cluster should use a higher port if not specifically set otherwise
                port = 8081
            else:
                # Ensure first cluster uses at least 8080 to avoid conflicts with possible 
                # PostgreSQL ports (5432/5433)
                if port < 8080:
                    port = 8080
            
            # Explicitly avoid common database ports
            if port in [5432, 5433]:
                logger.warning(f"Requested port {port} conflicts with PostgreSQL ports, using port 8080 instead")
                port = 8080 if "1" in container_name else 8081
            
            # For logging
            logger.info(f"Starting Trino container {container_name} with port mapping {internal_http_port} (internal) -> {port} (external)") 
            
            # IMPORTANT: Additional port conflict detection for Trino containers
            # This helps when multiple instances are being started
            if self.docker_available:
                try:
                    # First check ALL running containers for port conflicts using Docker API
                    all_containers = self.client.containers.list()
                    for c in all_containers:
                        container_ports = c.attrs.get('NetworkSettings', {}).get('Ports', {})
                        for container_port, bindings in container_ports.items():
                            if bindings:
                                for binding in bindings:
                                    if binding.get('HostPort') == str(port):
                                        logger.warning(f"Port {port} is already in use by container {c.name}")
                                        # Find a free port starting from our default + 10
                                        port = 8090 if "1" in container_name else 8091
                                        logger.info(f"Using alternative port {port} to avoid conflicts")
                                        break
                    
                    # Additional check for containers by expose filter (backup method)
                    # The port must be converted to string for the filter to work properly
                    existing_containers = self.client.containers.list(all=True, filters={'expose': f'{str(port)}/tcp'})
                    if existing_containers:
                        container_names = [c.name for c in existing_containers if c.name != container_name]
                        if container_names:
                            logger.warning(f"Port {port} is already in use by containers: {', '.join(container_names)}")
                            # Find a free port starting from our default + 10
                            for test_port in range(int(port) + 10, int(port) + 100):
                                # Ensure port is a string for filter
                                existing = self.client.containers.list(all=True, filters={'expose': f'{str(test_port)}/tcp'})
                                if not existing:
                                    port = test_port  # This is an int
                                    logger.info(f"Using alternative port {port} to avoid conflicts")
                                    break
                except Exception as e:
                    logger.warning(f"Error checking for port conflicts: {str(e)}")
            
            # Create a network name for this cluster to ensure container connectivity
            network_name = f"trino-network-{container_name}"
            
            # Create a dedicated network for this cluster if it doesn't exist
            try:
                # Check if the network already exists
                try:
                    existing_network = self.client.networks.get(network_name)
                    logger.info(f"Using existing Docker network: {network_name}")
                except docker.errors.NotFound:
                    # Create a new network
                    existing_network = self.client.networks.create(
                        name=network_name,
                        driver="bridge",
                        check_duplicate=True
                    )
                    logger.info(f"Created new Docker network: {network_name}")
                
                # If there's a PostgreSQL container for this Trino cluster, connect it to this network
                if postgres_container_name:
                    try:
                        pg_container = self.client.containers.get(postgres_container_name)
                        # Connect the PostgreSQL container to our network if it's not already connected
                        try:
                            existing_network.connect(pg_container)
                            logger.info(f"Connected PostgreSQL container {postgres_container_name} to network {network_name}")
                        except docker.errors.APIError as e:
                            # Already connected - that's fine
                            if "already exists" in str(e):
                                logger.info(f"PostgreSQL container {postgres_container_name} already connected to network {network_name}")
                            else:
                                raise
                    except docker.errors.NotFound:
                        logger.warning(f"Could not find PostgreSQL container {postgres_container_name} to connect to network")
            except Exception as e:
                logger.warning(f"Error setting up Docker network: {str(e)}")
                network_name = None  # Fall back to default bridge network
            
            # Always use bridge networking with explicit port mapping for both containers
            # This ensures that Docker shows the port mappings in container list
            container_options = {
                'name': container_name,
                'ports': {f'{internal_http_port}/tcp': port},  # Explicit port mapping with our conflict resolution
                'volumes': {
                    config_dir: {'bind': '/etc/trino', 'mode': 'rw'}
                },
                'detach': True
            }
            
            # Only add network specification if we have a valid network
            if network_name:
                container_options['network'] = network_name
                
            # Start the Trino container with all our options
            container = self.client.containers.run(
                f"trinodb/trino:{version}",
                **container_options
            )
            
            # Log the port mapping for clarity
            if use_postgres:
                logger.info(f"Started Trino container {container_name} with port mapping {internal_http_port} -> {port} (with PostgreSQL host access)")
            else:
                logger.info(f"Started Trino container {container_name} with port mapping {internal_http_port} -> {port}")
            
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
                    # Simulate progress with byte information in demo mode
                    total_bytes = 500 * 1024 * 1024  # ~500MB image
                    for i in range(11):
                        progress = i / 10.0
                        bytes_downloaded = int(progress * total_bytes)
                        
                        # Try to send detailed information if callback supports it
                        try:
                            # Updated for callback accepting byte information
                            import inspect
                            sig = inspect.signature(progress_callback)
                            if len(sig.parameters) >= 3:
                                # Callback accepts (progress, bytes_downloaded, total_bytes)
                                progress_callback(progress, bytes_downloaded, total_bytes)
                            else:
                                # Fall back to simple progress
                                progress_callback(progress)
                        except:
                            # If anything fails, use simple callback
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
    
    def verify_container_running(self, container_name):
        """Check if a container is actually running and return true if it is"""
        if not self.docker_available:
            return False
            
        try:
            container = self.client.containers.get(container_name)
            return container.status == 'running'
        except docker.errors.NotFound:
            logger.info(f"Container {container_name} not found during verification")
            return False
        except Exception as e:
            logger.error(f"Error verifying container status for {container_name}: {str(e)}")
            return False
            
    def cleanup_stale_containers(self, container_names):
        """Check and clean up stale Trino containers with the given names"""
        if not self.docker_available:
            logger.warning("Docker not available, cannot clean up stale containers")
            return
            
        cleaned = []
        for name in container_names:
            try:
                container = self.client.containers.get(name)
                # If the container exists but our app doesn't know about it, it's stale
                logger.info(f"Found stale container {name}, removing it...")
                container.stop()
                container.remove()
                cleaned.append(name)
                logger.info(f"Stale container {name} stopped and removed")
            except docker.errors.NotFound:
                # Container doesn't exist, nothing to do
                pass
            except Exception as e:
                logger.error(f"Error cleaning up stale container {name}: {str(e)}")
        
        return cleaned
    
    def _wait_for_postgres_ready(self, container, container_name, max_attempts=10):
        """Wait for PostgreSQL container to be ready to accept connections
        
        Args:
            container: The Docker container object
            container_name: The name of the PostgreSQL container
            max_attempts: Maximum number of connection attempts
        """
        logger.info(f"Waiting for PostgreSQL container {container_name} to be ready...")
        
        # We'll do a simple retry with exponential backoff
        import time
        
        # Don't wait if Docker is not available (demo mode)
        if not self.docker_available:
            return
            
        # Try to connect using both pg_isready and a direct psql connection check
        # This provides more robust readiness detection
        attempt = 0
        while attempt < max_attempts:
            try:
                # First ensure the container is still running
                container.reload()
                if container.status != 'running':
                    logger.error(f"PostgreSQL container {container_name} is not running (status: {container.status})")
                    logs = container.logs().decode('utf-8')
                    logger.error(f"Container logs: {logs[:1000]}...")  # Show first 1000 chars to avoid log flooding
                    time.sleep(2)
                    attempt += 1
                    continue
                
                # Try pg_isready first - simplest check
                pg_isready_cmd = ["pg_isready"]
                exit_code, output = container.exec_run(pg_isready_cmd)
                
                # Check if PostgreSQL is ready (exit code 0)
                if exit_code == 0:
                    logger.info(f"PostgreSQL container {container_name} is ready for connections (pg_isready check passed)")
                    
                    # Double-check with a basic psql command 
                    psql_check_cmd = ["psql", "-U", "postgres", "-c", "SELECT 1"]
                    exit_code, output = container.exec_run(psql_check_cmd)
                    
                    if exit_code == 0:
                        logger.info(f"PostgreSQL container {container_name} passed connection test with psql")
                        return True
                    else:
                        logger.warning(f"pg_isready passed but psql check failed: {output.decode('utf-8').strip()}")
                
                # More detailed readiness check if pg_isready fails
                else:
                    logger.info(f"PostgreSQL not ready yet (attempt {attempt+1}/{max_attempts}): {output.decode('utf-8').strip()}")
                    
                    # Check container logs for startup progress or errors
                    if attempt % 2 == 0:  # Only check logs every other attempt to avoid log flooding
                        logs = container.logs(tail=20).decode('utf-8')
                        logger.info(f"Recent container logs: {logs}")
                
                # Wait with exponential backoff (capped at 10 seconds max wait)
                wait_time = min(2 ** attempt, 10)
                time.sleep(wait_time)
                attempt += 1
                
            except Exception as e:
                logger.error(f"Error checking PostgreSQL readiness: {str(e)}")
                time.sleep(min(2 ** attempt, 10))
                attempt += 1
                
        logger.warning(f"Timed out waiting for PostgreSQL container {container_name} to be ready after {max_attempts} attempts")
        
        # Last resort: show the container logs to help diagnose the issue
        try:
            logs = container.logs().decode('utf-8')
            logger.error(f"PostgreSQL container logs after timeout: {logs}")
        except Exception as e:
            logger.error(f"Error getting logs from failed container: {str(e)}")
            
        return False
    
    def _seed_postgres_container(self, container, container_name, user, password, database):
        """Seed a PostgreSQL container with sample data
        
        Args:
            container: The Docker container object
            container_name: The name of the PostgreSQL container
            user: PostgreSQL username
            password: PostgreSQL password
            database: PostgreSQL database name
        """
        logger.info(f"Seeding PostgreSQL container {container_name} with sample data...")
        
        # Don't seed if Docker is not available (demo mode)
        if not self.docker_available:
            return
            
        try:
            # Create a script with sample data
            seed_sql = """
            -- Create a sample schema
            CREATE SCHEMA IF NOT EXISTS sample;
            
            -- Create a users table
            CREATE TABLE IF NOT EXISTS sample.users (
                user_id SERIAL PRIMARY KEY,
                username VARCHAR(50) NOT NULL,
                email VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            -- Create a products table
            CREATE TABLE IF NOT EXISTS sample.products (
                product_id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                price DECIMAL(10, 2) NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            -- Create an orders table
            CREATE TABLE IF NOT EXISTS sample.orders (
                order_id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES sample.users(user_id),
                total_amount DECIMAL(10, 2) NOT NULL,
                status VARCHAR(20) DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            -- Create an order_items table
            CREATE TABLE IF NOT EXISTS sample.order_items (
                item_id SERIAL PRIMARY KEY,
                order_id INTEGER REFERENCES sample.orders(order_id),
                product_id INTEGER REFERENCES sample.products(product_id),
                quantity INTEGER NOT NULL,
                price DECIMAL(10, 2) NOT NULL
            );
            
            -- Insert sample users
            INSERT INTO sample.users (username, email) VALUES
                ('johndoe', 'john.doe@example.com'),
                ('janedoe', 'jane.doe@example.com'),
                ('bobsmith', 'bob.smith@example.com'),
                ('alicejones', 'alice.jones@example.com'),
                ('michaelbrown', 'michael.brown@example.com')
            ON CONFLICT (user_id) DO NOTHING;
            
            -- Insert sample products
            INSERT INTO sample.products (name, price, description) VALUES
                ('Laptop', 1299.99, 'High-performance laptop with 16GB RAM'),
                ('Smartphone', 799.99, 'Latest model with 128GB storage'),
                ('Headphones', 199.99, 'Noise-cancelling wireless headphones'),
                ('Tablet', 499.99, '10-inch tablet with 64GB storage'),
                ('Monitor', 349.99, '27-inch 4K monitor')
            ON CONFLICT (product_id) DO NOTHING;
            
            -- Insert sample orders
            INSERT INTO sample.orders (user_id, total_amount, status) VALUES
                (1, 1299.99, 'completed'),
                (2, 999.98, 'completed'),
                (3, 199.99, 'processing'),
                (4, 849.98, 'shipped'),
                (1, 349.99, 'pending')
            ON CONFLICT (order_id) DO NOTHING;
            
            -- Insert sample order items
            INSERT INTO sample.order_items (order_id, product_id, quantity, price) VALUES
                (1, 1, 1, 1299.99),
                (2, 2, 1, 799.99),
                (2, 3, 1, 199.99),
                (3, 3, 1, 199.99),
                (4, 2, 1, 799.99),
                (4, 4, 1, 49.99),
                (5, 5, 1, 349.99)
            ON CONFLICT (item_id) DO NOTHING;
            
            -- Create another schema for a different dataset
            CREATE SCHEMA IF NOT EXISTS analytics;
            
            -- Create a sales table in the analytics schema
            CREATE TABLE IF NOT EXISTS analytics.sales (
                sale_id SERIAL PRIMARY KEY,
                product_name VARCHAR(100) NOT NULL,
                category VARCHAR(50) NOT NULL,
                amount DECIMAL(10, 2) NOT NULL,
                sale_date DATE NOT NULL
            );
            
            -- Insert sample sales data
            INSERT INTO analytics.sales (product_name, category, amount, sale_date) VALUES
                ('Laptop Pro', 'Electronics', 1499.99, '2025-01-15'),
                ('Smartphone X', 'Electronics', 899.99, '2025-01-16'),
                ('Desk Chair', 'Furniture', 199.99, '2025-01-17'),
                ('Coffee Table', 'Furniture', 299.99, '2025-01-18'),
                ('Bluetooth Speaker', 'Electronics', 79.99, '2025-01-19'),
                ('Tablet Air', 'Electronics', 599.99, '2025-01-20'),
                ('Sofa', 'Furniture', 899.99, '2025-01-21'),
                ('Headphones Pro', 'Electronics', 249.99, '2025-01-22'),
                ('Dining Table', 'Furniture', 499.99, '2025-01-23'),
                ('Smart Watch', 'Electronics', 349.99, '2025-01-24'),
                ('Bookshelf', 'Furniture', 149.99, '2025-01-25'),
                ('Laptop Pro', 'Electronics', 1499.99, '2025-02-15'),
                ('Smartphone X', 'Electronics', 899.99, '2025-02-16'),
                ('Desk Chair', 'Furniture', 199.99, '2025-02-17'),
                ('Coffee Table', 'Furniture', 299.99, '2025-02-18'),
                ('Bluetooth Speaker', 'Electronics', 79.99, '2025-02-19'),
                ('Tablet Air', 'Electronics', 599.99, '2025-02-20'),
                ('Sofa', 'Furniture', 899.99, '2025-02-21'),
                ('Headphones Pro', 'Electronics', 249.99, '2025-02-22'),
                ('Dining Table', 'Furniture', 499.99, '2025-02-23')
            ON CONFLICT (sale_id) DO NOTHING;
            
            -- Create a view to show total sales by category
            CREATE OR REPLACE VIEW analytics.sales_by_category AS
            SELECT 
                category,
                SUM(amount) as total_sales,
                COUNT(*) as num_sales
            FROM analytics.sales
            GROUP BY category;
            
            -- Create a view to show monthly sales
            CREATE OR REPLACE VIEW analytics.monthly_sales AS
            SELECT 
                EXTRACT(YEAR FROM sale_date) as year,
                EXTRACT(MONTH FROM sale_date) as month,
                SUM(amount) as total_sales,
                COUNT(*) as num_sales
            FROM analytics.sales
            GROUP BY year, month
            ORDER BY year, month;
            """
            
            # Write the SQL script to a file inside the container
            # We'll use a temporary file approach
            script_path = "/tmp/seed_data.sql"
            cmd = f'bash -c "echo \'{seed_sql}\' > {script_path}"'
            exit_code, output = container.exec_run(cmd, privileged=True)
            
            if exit_code != 0:
                logger.error(f"Failed to create seed script: {output.decode('utf-8')}")
                return
                
            # Execute the script
            psql_cmd = f'bash -c "PGPASSWORD={password} psql -U {user} -d {database} -f {script_path}"'
            exit_code, output = container.exec_run(psql_cmd)
            
            if exit_code != 0:
                logger.error(f"Failed to seed database: {output.decode('utf-8')}")
                return
                
            logger.info(f"Successfully seeded PostgreSQL container {container_name} with sample data")
            
            # Verify the data was loaded by counting tables
            verify_cmd = f'bash -c "PGPASSWORD={password} psql -U {user} -d {database} -c \'SELECT COUNT(*) FROM sample.users;\'"'
            exit_code, output = container.exec_run(verify_cmd)
            
            if exit_code == 0:
                logger.info(f"Verification successful: {output.decode('utf-8').strip()}")
            else:
                logger.warning(f"Verification failed: {output.decode('utf-8')}")
                
        except Exception as e:
            logger.error(f"Error seeding PostgreSQL container {container_name}: {str(e)}")
    
    def stop_trino_cluster(self, container_name):
        """Stop and remove a Trino cluster and its associated containers (PostgreSQL, Iceberg, etc.)"""
        if not self.docker_available:
            logger.warning(f"Docker not available, cannot stop Trino cluster {container_name}")
            return
            
        # First try to stop and remove the associated PostgreSQL container if it exists
        postgres_container_name = f"postgres-for-{container_name}"
        try:
            postgres_container = self.client.containers.get(postgres_container_name)
            logger.info(f"Stopping PostgreSQL container {postgres_container_name}...")
            postgres_container.stop()
            postgres_container.remove()
            logger.info(f"PostgreSQL container {postgres_container_name} stopped and removed")
        except docker.errors.NotFound:
            # No PostgreSQL container found, which is okay
            logger.debug(f"No PostgreSQL container found for {container_name}")
        except Exception as e:
            # Log but continue - we still want to try stopping the Trino container
            logger.error(f"Error stopping PostgreSQL container {postgres_container_name}: {str(e)}")
        
        # Stop and remove Iceberg REST container if it exists
        iceberg_rest_container_name = f"iceberg-rest-for-{container_name}"
        try:
            iceberg_container = self.client.containers.get(iceberg_rest_container_name)
            logger.info(f"Stopping Iceberg REST container {iceberg_rest_container_name}...")
            iceberg_container.stop()
            iceberg_container.remove()
            logger.info(f"Iceberg REST container {iceberg_rest_container_name} stopped and removed")
        except docker.errors.NotFound:
            # No Iceberg REST container found, which is okay
            logger.debug(f"No Iceberg REST container found for {container_name}")
        except Exception as e:
            # Log but continue
            logger.error(f"Error stopping Iceberg REST container {iceberg_rest_container_name}: {str(e)}")
            
        # Stop and remove MinIO container if it exists
        minio_container_name = f"minio-for-{container_name}"
        try:
            minio_container = self.client.containers.get(minio_container_name)
            logger.info(f"Stopping MinIO container {minio_container_name}...")
            minio_container.stop()
            minio_container.remove()
            logger.info(f"MinIO container {minio_container_name} stopped and removed")
        except docker.errors.NotFound:
            # No MinIO container found, which is okay
            logger.debug(f"No MinIO container found for {container_name}")
        except Exception as e:
            # Log but continue
            logger.error(f"Error stopping MinIO container {minio_container_name}: {str(e)}")
            
        # Try to remove bucket creator container if it exists (though it should auto-remove)
        bucket_creator_name = f"create-buckets-for-{container_name}"
        try:
            bucket_creator = self.client.containers.get(bucket_creator_name)
            logger.info(f"Removing bucket creator container {bucket_creator_name}...")
            bucket_creator.remove(force=True)
            logger.info(f"Bucket creator container {bucket_creator_name} removed")
        except docker.errors.NotFound:
            # No bucket creator container found, which is okay
            pass
        except Exception as e:
            # Log but continue
            logger.error(f"Error removing bucket creator container {bucket_creator_name}: {str(e)}")
            
        # Now stop and remove the Trino container
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
