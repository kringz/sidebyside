import logging
import sys
from docker_manager import MinitrinoManager

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_docker_connection():
    """Test Docker connection and basic functionality"""
    logger.info("Testing Docker connection...")
    
    try:
        # Initialize MinitrinoManager
        manager = MinitrinoManager()
        
        # Check Docker availability
        if not manager.docker_available:
            logger.error("Docker is not available")
            return False
        
        logger.info("Docker is available")
        
        # Test getting cluster status
        status = manager.get_cluster_status("test_cluster")
        logger.info(f"Status of non-existent cluster: {status}")
        
        # The status should be "not_found"
        if status["status"] != "not_found":
            logger.error("Unexpected status for non-existent cluster")
            return False
            
        logger.info("Cluster status check successful")
        return True
        
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return False

if __name__ == "__main__":
    success = test_docker_connection()
    if success:
        logger.info("All tests passed successfully")
        sys.exit(0)
    else:
        logger.error("Tests failed")
        sys.exit(1) 