import logging
import time
from trino.dbapi import connect
from trino.exceptions import TrinoQueryError

logger = logging.getLogger(__name__)

class TrinoClient:
    """Client for interacting with Trino clusters"""
    
    def __init__(self, host, port, user='trino', cluster_name=None):
        """Initialize the Trino client
        
        Args:
            host (str): Hostname or IP address of the Trino coordinator
            port (int): HTTP port of the Trino coordinator
            user (str): Username to use for queries
            cluster_name (str): Name of the cluster for identification
        """
        self.host = host
        self.port = port
        self.user = user
        self.cluster_name = cluster_name or f"Trino {host}:{port}"
        self.connection = None
        
        logger.info(f"Initialized Trino client for {self.cluster_name} at {host}:{port}")
    
    def get_connection(self):
        """Get a connection to the Trino cluster"""
        if not self.connection:
            logger.debug(f"Creating new connection to {self.cluster_name}")
            try:
                # When using host networking mode, we need to connect to the correct port directly
                # instead of the mapped port. Trino internally runs on 8080 in the container
                connect_port = self.port
                
                # If the port is different from the standard Trino port (8080),
                # it's probably a mapped port from Docker, so use that
                logger.debug(f"Connecting to Trino at {self.host}:{connect_port}")
                
                self.connection = connect(
                    host=self.host,
                    port=connect_port,
                    user=self.user,
                    catalog='system',
                    schema='runtime'
                )
                logger.info(f"Connected to {self.cluster_name}")
            except Exception as e:
                logger.error(f"Failed to connect to {self.cluster_name}: {str(e)}")
                # Try a fallback connection if the first one fails
                if str(e).find("Connection refused") >= 0:
                    try:
                        fallback_port = 8080 if self.port != 8080 else self.port
                        logger.warning(f"Connection failed, trying fallback to port {fallback_port}")
                        self.connection = connect(
                            host=self.host,
                            port=fallback_port,
                            user=self.user,
                            catalog='system',
                            schema='runtime'
                        )
                        logger.info(f"Connected to {self.cluster_name} using fallback port")
                        return self.connection
                    except Exception as fallback_e:
                        logger.error(f"Fallback connection also failed: {str(fallback_e)}")
                
                raise ConnectionError(f"Failed to connect to Trino cluster at {self.host}:{self.port}: {str(e)}")
        
        return self.connection
    
    def execute_query(self, query):
        """Execute a query on the Trino cluster
        
        Args:
            query (str): SQL query to execute
            
        Returns:
            dict: Query results with columns and rows
        """
        try:
            connection = self.get_connection()
            cursor = connection.cursor()
            
            logger.debug(f"Executing query on {self.cluster_name}: {query}")
            start_time = time.time()
            cursor.execute(query)
            
            # Get column names
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            
            # Fetch all rows
            rows = cursor.fetchall()
            
            end_time = time.time()
            execution_time = end_time - start_time
            
            logger.info(f"Query executed on {self.cluster_name} in {execution_time:.2f} seconds")
            logger.debug(f"Query result: {len(rows)} rows, {len(columns)} columns")
            
            return {
                'columns': columns,
                'rows': rows,
                'row_count': len(rows),
                'execution_time': execution_time
            }
        
        except TrinoQueryError as e:
            logger.error(f"Query error on {self.cluster_name}: {str(e)}")
            raise Exception(f"Trino query error: {str(e)}")
        except Exception as e:
            logger.error(f"Error executing query on {self.cluster_name}: {str(e)}")
            raise Exception(f"Failed to execute query: {str(e)}")
    
    def get_catalogs(self):
        """Get a list of available catalogs"""
        try:
            result = self.execute_query("SHOW CATALOGS")
            return [row[0] for row in result['rows']]
        except Exception as e:
            logger.error(f"Error getting catalogs from {self.cluster_name}: {str(e)}")
            return []
    
    def get_schemas(self, catalog):
        """Get a list of schemas in a catalog"""
        try:
            result = self.execute_query(f"SHOW SCHEMAS FROM {catalog}")
            return [row[0] for row in result['rows']]
        except Exception as e:
            logger.error(f"Error getting schemas from {catalog} in {self.cluster_name}: {str(e)}")
            return []
    
    def get_tables(self, catalog, schema):
        """Get a list of tables in a schema"""
        try:
            result = self.execute_query(f"SHOW TABLES FROM {catalog}.{schema}")
            return [row[0] for row in result['rows']]
        except Exception as e:
            logger.error(f"Error getting tables from {catalog}.{schema} in {self.cluster_name}: {str(e)}")
            return []
    
    def get_cluster_info(self):
        """Get information about the Trino cluster"""
        try:
            version_info = self.execute_query("SELECT node_version FROM nodes")
            if version_info['rows']:
                return version_info['rows'][0][0]
            return "Unknown version"
        except Exception as e:
            logger.error(f"Error getting cluster info from {self.cluster_name}: {str(e)}")
            return "Unknown"
