import unittest
import logging
import os
from docker_manager import DockerManager, MinitrinoManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TestMinitrinoIntegration(unittest.TestCase):
    def setUp(self):
        """Set up test environment before each test"""
        socket_path = os.environ.get('DOCKER_SOCKET', '/var/run/docker.sock')
        # Ensure socket path has unix:// prefix
        if socket_path.startswith('/'):
            socket_path = f"unix://{socket_path}"
        self.docker_socket = socket_path
        self.manager = DockerManager(socket_path=self.docker_socket)
        
    def tearDown(self):
        """Clean up after each test"""
        try:
            self.manager.cleanup_stale_containers(['cluster1', 'cluster2'])
        except Exception as e:
            logger.warning(f"Cleanup failed: {str(e)}")

    def test_minitrino_initialization(self):
        """Test that Minitrino manager initializes correctly"""
        self.assertTrue(self.manager.docker_available)
        self.assertIsNotNone(self.manager.minitrino_manager)
        self.assertTrue(isinstance(self.manager.minitrino_manager, MinitrinoManager))

    def test_single_cluster_lifecycle(self):
        """Test starting and stopping a single Trino cluster"""
        # Define test configuration
        config = {
            'version': '429',  # Use a recent Trino version
            'port': 8080,
            'catalogs': {
                'tpch': {'enabled': True}
            }
        }
        
        # Start cluster
        success = self.manager.start_trino_cluster('cluster1', 
                                                 config['version'], 
                                                 config['port'], 
                                                 config['catalogs'])
        self.assertTrue(success, "Failed to start cluster")
        
        # Verify cluster is running
        status = self.manager.get_container_status('cluster1')
        self.assertEqual(status['status'], 'running')
        self.assertEqual(status['version'], '429')
        self.assertEqual(status['port'], 8080)
        
        # Stop cluster
        success = self.manager.stop_trino_cluster('cluster1')
        self.assertTrue(success, "Failed to stop cluster")
        
        # Verify cluster is stopped
        status = self.manager.get_container_status('cluster1')
        self.assertNotEqual(status['status'], 'running')

    def test_dual_cluster_lifecycle(self):
        """Test starting and stopping two Trino clusters"""
        # Define test configurations
        cluster1_config = {
            'version': '429',
            'port': 8080,
            'catalogs': {
                'tpch': {'enabled': True}
            }
        }
        
        cluster2_config = {
            'version': '428',
            'port': 8081,
            'catalogs': {
                'tpch': {'enabled': True}
            }
        }
        
        # Start both clusters
        success = self.manager.start_trino_clusters(cluster1_config, cluster2_config)
        self.assertTrue(success, "Failed to start clusters")
        
        # Verify both clusters are running
        status1 = self.manager.get_container_status('cluster1')
        status2 = self.manager.get_container_status('cluster2')
        
        self.assertEqual(status1['status'], 'running')
        self.assertEqual(status2['status'], 'running')
        
        # Verify versions and ports
        self.assertEqual(status1['version'], '429')
        self.assertEqual(status2['version'], '428')
        self.assertEqual(status1['port'], 8080)
        self.assertEqual(status2['port'], 8081)
        
        # Stop both clusters
        self.manager.cleanup_stale_containers(['cluster1', 'cluster2'])
        
        # Verify both clusters are stopped
        status1 = self.manager.get_container_status('cluster1')
        status2 = self.manager.get_container_status('cluster2')
        
        self.assertNotEqual(status1['status'], 'running')
        self.assertNotEqual(status2['status'], 'running')

    def test_catalog_configuration(self):
        """Test configuring different catalogs"""
        config = {
            'version': '429',
            'port': 8080,
            'catalogs': {
                'tpch': {'enabled': True},
                'postgresql': {
                    'enabled': True,
                    'host': 'localhost',
                    'port': 5432,
                    'database': 'test'
                },
                'mysql': {
                    'enabled': True,
                    'host': 'localhost',
                    'port': 3306,
                    'database': 'test'
                }
            }
        }
        
        # Start cluster with multiple catalogs
        success = self.manager.start_trino_cluster('cluster1', 
                                                 config['version'], 
                                                 config['port'], 
                                                 config['catalogs'])
        self.assertTrue(success, "Failed to start cluster with catalogs")
        
        # Verify cluster is running
        status = self.manager.get_container_status('cluster1')
        self.assertEqual(status['status'], 'running')
        
        # Stop cluster
        success = self.manager.stop_trino_cluster('cluster1')
        self.assertTrue(success, "Failed to stop cluster")

    def test_image_management(self):
        """Test Trino image pulling and listing"""
        # List available images
        images = self.manager.get_available_trino_images()
        self.assertIsInstance(images, list)
        
        # Pull a specific version
        success = self.manager.pull_trino_image('429')
        self.assertTrue(success, "Failed to pull Trino image")
        
        # Verify image is now in list
        images = self.manager.get_available_trino_images()
        self.assertIn('429', images)

if __name__ == '__main__':
    unittest.main() 