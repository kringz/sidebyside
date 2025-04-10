from datetime import datetime
import json
import time

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
    
    # Store explain plans
    cluster1_explain = db.Column(db.Text, nullable=True)
    cluster2_explain = db.Column(db.Text, nullable=True)
    cluster1_explain_timing = db.Column(db.Float, nullable=True)
    cluster2_explain_timing = db.Column(db.Float, nullable=True)
    
    def save_results(self, results, timing, errors, explain_results=None, explain_timing=None):
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
        
        # Save explain plans if provided
        if explain_results and explain_timing:
            if 'cluster1' in explain_results:
                self.cluster1_explain = json.dumps(explain_results['cluster1'])
                self.cluster1_explain_timing = explain_timing.get('cluster1')
            
            if 'cluster2' in explain_results:
                self.cluster2_explain = json.dumps(explain_results['cluster2'])
                self.cluster2_explain_timing = explain_timing.get('cluster2')
        
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
        
    def get_cluster1_explain(self):
        """Get the cluster1 explain plan as a Python object"""
        if self.cluster1_explain:
            return json.loads(self.cluster1_explain)
        return None
        
    def get_cluster2_explain(self):
        """Get the cluster2 explain plan as a Python object"""
        if self.cluster2_explain:
            return json.loads(self.cluster2_explain)
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


class BreakingChange(db.Model):
    """Model for storing breaking changes between Trino versions"""
    id = db.Column(db.Integer, primary_key=True)
    version = db.Column(db.String(20), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False)
    workaround = db.Column(db.Text, nullable=True)
    component = db.Column(db.String(50), nullable=True)
    impacts_performance = db.Column(db.Boolean, default=False)
    impacts_compatibility = db.Column(db.Boolean, default=True)
    
    def __repr__(self):
        return f"<BreakingChange {self.title} in {self.version}>"


class VersionComparison(db.Model):
    """Model for storing cached version comparison results"""
    id = db.Column(db.Integer, primary_key=True)
    from_version = db.Column(db.String(20), nullable=False)
    to_version = db.Column(db.String(20), nullable=False)
    
    # Store the comparison results as JSON
    comparison_results = db.Column(db.Text, nullable=False)
    
    # When this comparison was cached
    cached_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Cache expiry/validity in days (0 means no expiry)
    cache_valid_days = db.Column(db.Integer, default=30)
    
    def get_comparison_results(self):
        """Get the comparison results as a Python object"""
        if self.comparison_results:
            return json.loads(self.comparison_results)
        return {}
    
    def set_comparison_results(self, results):
        """Set the comparison results from a Python object"""
        self.comparison_results = json.dumps(results)
    
    def is_cache_valid(self):
        """Check if the cached results are still valid"""
        if self.cache_valid_days == 0:
            return True  # No expiry
        
        cache_age = datetime.utcnow() - self.cached_at
        return cache_age.days < self.cache_valid_days
    
    def __repr__(self):
        return f"<VersionComparison {self.from_version} to {self.to_version}>"


class FeatureChange(db.Model):
    """Model for storing feature changes (new, removed, or modified) between Trino versions"""
    id = db.Column(db.Integer, primary_key=True)
    version = db.Column(db.String(20), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False)
    change_type = db.Column(db.String(20), nullable=False)  # 'new', 'removed', 'deprecated', 'modified'
    component = db.Column(db.String(50), nullable=True)
    example = db.Column(db.Text, nullable=True)
    alternative = db.Column(db.String(255), nullable=True)  # For removed/deprecated features
    
    def __repr__(self):
        return f"<FeatureChange {self.title} ({self.change_type}) in {self.version}>"


class BenchmarkQuery(db.Model):
    """Model for storing predefined benchmark queries"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    query_text = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50), nullable=True)  # e.g., 'Joins', 'Aggregations', 'Window Functions'
    complexity = db.Column(db.String(20), nullable=True)  # e.g., 'Simple', 'Medium', 'Complex'
    expected_runtime = db.Column(db.Float, nullable=True)  # Expected runtime in seconds for calibration
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    
    # Relationship with results
    results = db.relationship('BenchmarkResult', backref='query', lazy=True)
    
    def __repr__(self):
        return f"<BenchmarkQuery {self.name}>"


class BenchmarkResult(db.Model):
    """Model for storing benchmark query results"""
    id = db.Column(db.Integer, primary_key=True)
    benchmark_query_id = db.Column(db.Integer, db.ForeignKey('benchmark_query.id'), nullable=False)
    execution_time = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Cluster versions and configurations
    cluster1_version = db.Column(db.String(20), nullable=True)
    cluster2_version = db.Column(db.String(20), nullable=True)
    cluster1_config = db.Column(db.Text, nullable=True)  # Stored as JSON
    cluster2_config = db.Column(db.Text, nullable=True)  # Stored as JSON
    
    # Performance metrics
    cluster1_timing = db.Column(db.Float, nullable=True)  # Total query time in seconds
    cluster2_timing = db.Column(db.Float, nullable=True)  # Total query time in seconds
    cluster1_cpu_time = db.Column(db.Float, nullable=True)  # CPU time in milliseconds
    cluster2_cpu_time = db.Column(db.Float, nullable=True)  # CPU time in milliseconds
    cluster1_memory_usage = db.Column(db.Float, nullable=True)  # Peak memory usage in MB
    cluster2_memory_usage = db.Column(db.Float, nullable=True)  # Peak memory usage in MB
    
    # Detailed timing metrics (stored as JSON)
    cluster1_timing_details = db.Column(db.Text, nullable=True)  # JSON with planning time, execution time, etc.
    cluster2_timing_details = db.Column(db.Text, nullable=True)  # JSON with planning time, execution time, etc.
    
    # Result metadata
    cluster1_row_count = db.Column(db.Integer, nullable=True)
    cluster2_row_count = db.Column(db.Integer, nullable=True)
    cluster1_status = db.Column(db.String(20), nullable=True)  # 'Success', 'Error', 'Timeout'
    cluster2_status = db.Column(db.String(20), nullable=True)  # 'Success', 'Error', 'Timeout'
    
    # Error information
    cluster1_error = db.Column(db.Text, nullable=True)
    cluster2_error = db.Column(db.Text, nullable=True)
    
    def get_cluster1_config(self):
        """Get the cluster1 config as a Python object"""
        if self.cluster1_config:
            return json.loads(self.cluster1_config)
        return {}
    
    def get_cluster2_config(self):
        """Get the cluster2 config as a Python object"""
        if self.cluster2_config:
            return json.loads(self.cluster2_config)
        return {}
    
    def get_cluster1_timing_details(self):
        """Get the cluster1 timing details as a Python object"""
        if self.cluster1_timing_details:
            return json.loads(self.cluster1_timing_details)
        return {}
    
    def get_cluster2_timing_details(self):
        """Get the cluster2 timing details as a Python object"""
        if self.cluster2_timing_details:
            return json.loads(self.cluster2_timing_details)
        return {}
    
    def __repr__(self):
        return f"<BenchmarkResult for query {self.benchmark_query_id} at {self.execution_time}>"