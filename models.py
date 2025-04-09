from datetime import datetime
import json

from flask_sqlalchemy import SQLAlchemy

# Initialize SQLAlchemy instance
db = SQLAlchemy()

class QueryHistory(db.Model):
    """Model for storing query history"""
    id = db.Column(db.Integer, primary_key=True)
    query_text = db.Column(db.Text, nullable=False)
    execution_time = db.Column(db.DateTime, default=datetime.utcnow)
    cluster1_timing = db.Column(db.Float, nullable=True)
    cluster2_timing = db.Column(db.Float, nullable=True)
    cluster1_status = db.Column(db.String(20), nullable=True)
    cluster2_status = db.Column(db.String(20), nullable=True)
    
    # Store the JSON results as text
    cluster1_results = db.Column(db.Text, nullable=True)
    cluster2_results = db.Column(db.Text, nullable=True)
    
    # Store any errors that occurred
    cluster1_error = db.Column(db.Text, nullable=True)
    cluster2_error = db.Column(db.Text, nullable=True)
    
    def save_results(self, results, timing, errors):
        """Save the query execution results"""
        if 'cluster1' in results:
            self.cluster1_results = json.dumps(results['cluster1'])
            self.cluster1_timing = timing.get('cluster1')
        else:
            self.cluster1_status = 'No results'
            
        if 'cluster2' in results:
            self.cluster2_results = json.dumps(results['cluster2'])
            self.cluster2_timing = timing.get('cluster2')
        else:
            self.cluster2_status = 'No results'
            
        if 'cluster1' in errors:
            self.cluster1_error = errors.get('cluster1')
            self.cluster1_status = 'Error'
            
        if 'cluster2' in errors:
            self.cluster2_error = errors.get('cluster2')
            self.cluster2_status = 'Error'
        
        # Set status for successful runs
        if not self.cluster1_status and 'cluster1' in results:
            self.cluster1_status = 'Success'
        if not self.cluster2_status and 'cluster2' in results:
            self.cluster2_status = 'Success'
    
    def get_cluster1_results(self):
        """Get the cluster1 results as a Python object"""
        if self.cluster1_results:
            return json.loads(self.cluster1_results)
        return None
    
    def get_cluster2_results(self):
        """Get the cluster2 results as a Python object"""
        if self.cluster2_results:
            return json.loads(self.cluster2_results)
        return None


class TrinoVersion(db.Model):
    """Model for storing Trino version compatibility information"""
    id = db.Column(db.Integer, primary_key=True)
    version = db.Column(db.String(20), nullable=False, unique=True)
    release_date = db.Column(db.Date, nullable=True)
    is_lts = db.Column(db.Boolean, default=False)
    support_end_date = db.Column(db.Date, nullable=True)
    release_notes_url = db.Column(db.String(255), nullable=True)
    
    # Store compatibility information as JSON
    compatibility_info = db.Column(db.Text, nullable=True)
    
    def get_compatibility_info(self):
        """Get the compatibility info as a Python object"""
        if self.compatibility_info:
            return json.loads(self.compatibility_info)
        return {}
    
    def set_compatibility_info(self, info):
        """Set the compatibility info from a Python object"""
        self.compatibility_info = json.dumps(info)


class CatalogCompatibility(db.Model):
    """Model for storing catalog compatibility with Trino versions"""
    id = db.Column(db.Integer, primary_key=True)
    catalog_name = db.Column(db.String(50), nullable=False)
    min_version = db.Column(db.String(20), nullable=True)
    max_version = db.Column(db.String(20), nullable=True)
    deprecated_in = db.Column(db.String(20), nullable=True)
    removed_in = db.Column(db.String(20), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    
    def __repr__(self):
        return f"<CatalogCompatibility {self.catalog_name}>"