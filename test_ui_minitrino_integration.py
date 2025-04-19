import unittest
import logging
import os
import time
import random
import subprocess
from flask import Flask
from docker_manager import DockerManager, MinitrinoManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TestUIMinitrinoIntegration(unittest.TestCase):
    def setUp(self):
        """Set up test environment before each test"""
        # Clean up any existing containers first
        self._cleanup_existing_containers()
        
        # Initialize Flask app
        self.app = Flask(__name__)
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        
        # Initialize Docker manager with test socket
        socket_path = os.environ.get('DOCKER_SOCKET', '/var/run/docker.sock')
        if socket_path.startswith('/'):
            socket_path = f"unix://{socket_path}"
        self.docker_manager = DockerManager(socket_path=socket_path)
        
        # Generate unique port for this test session
        self.test_port = random.randint(9000, 9999)
        
        # Add test routes
        self._setup_test_routes()
        
    def _cleanup_existing_containers(self):
        """Clean up any existing containers before starting tests"""
        try:
            # Stop and remove any existing containers
            subprocess.run(['docker', 'ps', '-a', '--filter', 'name=trino', '-q'], 
                         check=True, capture_output=True, text=True)
            subprocess.run(['docker', 'rm', '-f', 'trino'], 
                         check=False)  # Don't fail if no containers exist
            time.sleep(2)  # Give Docker time to clean up
        except subprocess.CalledProcessError as e:
            logger.warning(f"Cleanup failed: {str(e)}")
        
    def _setup_test_routes(self):
        """Set up test routes for UI endpoints"""
        @self.app.route('/api/clusters/status')
        def get_cluster_status():
            try:
                status = self.docker_manager.get_container_status('cluster1')
                if isinstance(status, dict):
                    return {'status': status}
                else:
                    return {'status': {'status': status}}
            except Exception as e:
                logger.error(f"Error getting status: {str(e)}")
                return {'error': str(e)}, 500

        @self.app.route('/api/clusters/start', methods=['POST'])
        def start_cluster():
            try:
                config = {
                    'version': '429',
                    'port': self.test_port,
                    'catalogs': {'tpch': {'enabled': True}}
                }
                success = self.docker_manager.start_trino_cluster('cluster1', 
                                                               config['version'],
                                                               config['port'],
                                                               config['catalogs'])
                if not success:
                    return {'error': 'Failed to start cluster'}, 500
                return {'success': True}
            except Exception as e:
                logger.error(f"Error starting cluster: {str(e)}")
                return {'error': str(e)}, 500

        @self.app.route('/api/clusters/stop', methods=['POST'])
        def stop_cluster():
            try:
                success = self.docker_manager.stop_trino_cluster('cluster1')
                if not success:
                    return {'error': 'Failed to stop cluster'}, 500
                return {'success': True}
            except Exception as e:
                logger.error(f"Error stopping cluster: {str(e)}")
                return {'error': str(e)}, 500

    def tearDown(self):
        """Clean up after each test"""
        try:
            # First try to stop the cluster
            self.docker_manager.stop_trino_cluster('cluster1')
            # Then clean up any stale containers
            self._cleanup_existing_containers()
        except Exception as e:
            logger.warning(f"Cleanup failed: {str(e)}")

    def test_ui_cluster_status_updates(self):
        """Test that UI correctly reflects cluster status changes"""
        # Start cluster
        response = self.client.post('/api/clusters/start')
        self.assertEqual(response.status_code, 200, 
                        f"Expected status 200, got {response.status_code}. Response: {response.json}")
        self.assertTrue(response.json['success'], 
                       f"Failed to start cluster: {response.json.get('error', '')}")
        
        # Wait for cluster to start
        time.sleep(5)
        
        # Check status
        response = self.client.get('/api/clusters/status')
        self.assertEqual(response.status_code, 200)
        status = response.json['status']
        if isinstance(status, str):
            self.assertEqual(status, 'running')
        else:
            self.assertEqual(status['status'], 'running', 
                           f"Cluster not running: {status}")
            self.assertEqual(status['version'], '429')
            self.assertEqual(status['port'], self.test_port)
        
        # Stop cluster
        response = self.client.post('/api/clusters/stop')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json['success'], 
                       f"Failed to stop cluster: {response.json.get('error', '')}")
        
        # Check status again
        response = self.client.get('/api/clusters/status')
        self.assertEqual(response.status_code, 200)
        status = response.json['status']
        if isinstance(status, str):
            self.assertNotEqual(status, 'running')
        else:
            self.assertNotEqual(status['status'], 'running', 
                              "Cluster still running after stop")

    def test_ui_error_handling(self):
        """Test UI error handling when Docker is not available"""
        # Simulate Docker not being available
        self.docker_manager.docker_available = False
        
        # Try to start cluster
        response = self.client.post('/api/clusters/start')
        self.assertEqual(response.status_code, 500,
                        f"Expected status 500, got {response.status_code}. Response: {response.json}")
        self.assertIn('error', response.json)
        
        # Check status
        response = self.client.get('/api/clusters/status')
        self.assertEqual(response.status_code, 200)
        status = response.json['status']
        if isinstance(status, str):
            self.assertEqual(status, 'error')
        else:
            self.assertEqual(status['status'], 'error')

    def test_ui_cluster_configuration(self):
        """Test UI handling of different cluster configurations"""
        # Test with different Trino versions
        versions = ['429', '428']
        for version in versions:
            config = {
                'version': version,
                'port': self.test_port,
                'catalogs': {'tpch': {'enabled': True}}
            }
            
            # Start cluster
            response = self.client.post('/api/clusters/start', json=config)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json['success'], 
                          f"Failed to start cluster with version {version}: {response.json.get('error', '')}")
            
            # Check status
            response = self.client.get('/api/clusters/status')
            self.assertEqual(response.status_code, 200)
            status = response.json['status']
            if isinstance(status, str):
                self.assertEqual(status, 'running')
            else:
                self.assertEqual(status['version'], version)
            
            # Stop cluster
            response = self.client.post('/api/clusters/stop')
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json['success'], 
                          f"Failed to stop cluster: {response.json.get('error', '')}")
            
            # Wait for cleanup
            time.sleep(2)

    def test_ui_catalog_management(self):
        """Test UI handling of catalog configuration"""
        # Test with multiple catalogs
        config = {
            'version': '429',
            'port': self.test_port,
            'catalogs': {
                'tpch': {'enabled': True},
                'postgresql': {
                    'enabled': True,
                    'host': 'localhost',
                    'port': 5432,
                    'database': 'test'
                }
            }
        }
        
        # Start cluster with multiple catalogs
        response = self.client.post('/api/clusters/start', json=config)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json['success'], 
                       f"Failed to start cluster with catalogs: {response.json.get('error', '')}")
        
        # Check status
        response = self.client.get('/api/clusters/status')
        self.assertEqual(response.status_code, 200)
        status = response.json['status']
        if isinstance(status, str):
            self.assertEqual(status, 'running')
        else:
            self.assertEqual(status['status'], 'running')
        
        # Stop cluster
        response = self.client.post('/api/clusters/stop')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json['success'], 
                       f"Failed to stop cluster: {response.json.get('error', '')}")

if __name__ == '__main__':
    unittest.main() 