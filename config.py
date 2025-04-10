import os
import yaml
import logging

logger = logging.getLogger(__name__)

# Paths
CONFIG_DIR = 'config'
CONFIG_FILE = os.path.join(CONFIG_DIR, 'config.yaml')
DEFAULT_CONFIG_FILE = os.path.join(CONFIG_DIR, 'default_config.yaml')

def get_default_config():
    """Get the default configuration"""
    try:
        if os.path.exists(DEFAULT_CONFIG_FILE):
            with open(DEFAULT_CONFIG_FILE, 'r') as f:
                return yaml.safe_load(f)
        else:
            # Return hardcoded default config
            return {
                'docker': {
                    'trino_connect_host': 'localhost',  # Use 'host.docker.internal' for Mac Docker Desktop
                    'socket_path': '',  # Will be auto-detected if empty
                    'timeout': 30,  # Timeout in seconds for Docker operations
                    'auto_pull_images': True  # Whether to auto-pull images when versions change
                },
                'cluster1': {
                    'version': '401',
                    'port': 8001,
                    'container_name': 'trino1'
                },
                'cluster2': {
                    'version': '407',
                    'port': 8002,
                    'container_name': 'trino2'
                },
                'catalogs': {
                    'tpch': {
                        'enabled': True,
                        'column_naming': 'SIMPLIFIED'  # Can be 'SIMPLIFIED' or 'STANDARD'
                    },
                    'hive': {
                        'enabled': False,
                        'metastore_host': 'localhost',
                        'metastore_port': '9083'
                    },
                    'iceberg': {
                        'enabled': False,
                        'rest_host': 'localhost',
                        'rest_port': '8181',
                        's3_endpoint': 'http://localhost:9000',
                        's3_region': 'us-east-1',
                        's3_access_key': 'access-key',
                        's3_secret_key': 'secret-key'
                    },
                    'delta-lake': {
                        'enabled': False,
                        'metastore_host': 'localhost',
                        'metastore_port': '9083'
                    },
                    'mysql': {
                        'enabled': False,
                        'host': 'localhost',
                        'port': '3306',
                        'user': 'root',
                        'password': ''
                    },
                    'mariadb': {
                        'enabled': False,
                        'host': 'localhost',
                        'port': '3306',
                        'user': 'root',
                        'password': ''
                    },
                    'postgres': {
                        'enabled': True,
                        'host': 'localhost',
                        'port': '5432',
                        'database': 'postgres',
                        'user': 'postgres',
                        'password': 'postgres'
                    },
                    'sqlserver': {
                        'enabled': False,
                        'host': 'localhost',
                        'port': '1433',
                        'database': 'master',
                        'user': 'sa',
                        'password': ''
                    },
                    'db2': {
                        'enabled': False,
                        'host': 'localhost',
                        'port': '50000',
                        'database': 'sample',
                        'user': 'db2inst1',
                        'password': ''
                    },
                    'clickhouse': {
                        'enabled': False,
                        'host': 'localhost',
                        'port': '8123',
                        'user': 'default',
                        'password': ''
                    },
                    'pinot': {
                        'enabled': False,
                        'host': 'localhost',
                        'port': '9000'
                    },
                    'elasticsearch': {
                        'enabled': False,
                        'host': 'localhost',
                        'port': '9200'
                    }
                }
            }
    except Exception as e:
        logger.error(f"Error getting default configuration: {str(e)}")
        raise

def load_config():
    """Load configuration from file or create default if it doesn't exist"""
    try:
        # Create config directory if it doesn't exist
        if not os.path.exists(CONFIG_DIR):
            os.makedirs(CONFIG_DIR)
        
        # Load existing config or create default
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                config = yaml.safe_load(f)
                logger.debug("Loaded configuration from file")
                
                # Get default config to check for missing catalogs
                default_config = get_default_config()
                
                # Add any missing catalogs from the default config
                for catalog_name, catalog_config in default_config['catalogs'].items():
                    if catalog_name not in config['catalogs']:
                        logger.info(f"Adding missing catalog '{catalog_name}' from default config")
                        config['catalogs'][catalog_name] = catalog_config
                
                return config
        else:
            config = get_default_config()
            save_config(config)
            logger.info("Created default configuration")
            return config
    except Exception as e:
        logger.error(f"Error loading configuration: {str(e)}")
        raise

def save_config(config):
    """Save configuration to file"""
    try:
        # Create config directory if it doesn't exist
        if not os.path.exists(CONFIG_DIR):
            os.makedirs(CONFIG_DIR)
        
        with open(CONFIG_FILE, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
        logger.debug("Saved configuration to file")
    except Exception as e:
        logger.error(f"Error saving configuration: {str(e)}")
        raise
