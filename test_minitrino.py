import os
import time
from docker_manager import DockerManager
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_minitrino_integration(version):
    """Test the Minitrino integration with two clusters
    
    Args:
        version (str): The Starburst version to use for both clusters
    """
    
    # Initialize the Docker manager
    docker_manager = DockerManager()
    
    # Define configurations for two clusters using Minitrino format
    cluster1_config = {
        'version': version,
        'port': 8090,
        'catalogs': {
            'postgres': {
                'enabled': True,
                'type': 'postgresql',
                'properties': {
                    'connection-url': 'jdbc:postgresql://localhost:5432/postgres',
                    'connection-user': 'postgres',
                    'connection-password': 'postgres123'
                }
            }
        }
    }
    
    cluster2_config = {
        'version': version,
        'port': 8091,
        'catalogs': {
            'elasticsearch': {
                'enabled': True,
                'type': 'elasticsearch',
                'properties': {
                    'elasticsearch.host': 'localhost',
                    'elasticsearch.port': '9200'
                }
            }
        }
    }
    
    try:
        # Start both clusters
        logger.info("Starting clusters...")
        success = docker_manager.start_trino_clusters(cluster1_config, cluster2_config)
        if not success:
            logger.error("Failed to start clusters")
            return False
            
        # Wait for clusters to initialize
        logger.info("Waiting for clusters to initialize...")
        time.sleep(30)
        
        # Check cluster statuses
        logger.info("Checking cluster statuses...")
        status1 = docker_manager.get_container_status('cluster1')
        status2 = docker_manager.get_container_status('cluster2')
        
        logger.info(f"Cluster 1 status: {status1}")
        logger.info(f"Cluster 2 status: {status2}")
        
        # Verify both clusters are running
        if status1.get('status') != 'running' or status2.get('status') != 'running':
            logger.error("One or both clusters failed to start")
            return False
            
        logger.info("Both clusters started successfully!")
        return True
        
    except Exception as e:
        logger.error(f"Test failed: {str(e)}")
        return False
    finally:
        # Clean up
        logger.info("Cleaning up...")
        docker_manager.stop_trino_clusters()

if __name__ == "__main__":
    # For testing purposes, use a default version if none provided
    version = os.environ.get('STARBURST_VERSION', '443-e')
    success = test_minitrino_integration(version)
    if success:
        logger.info("Test completed successfully!")
    else:
        logger.error("Test failed!") 