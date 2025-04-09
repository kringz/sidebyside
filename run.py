import os
import subprocess
import sys
import time

def setup_postgres():
    """Set up PostgreSQL database with Replit"""
    try:
        # Check if PostgreSQL environment variables are already set
        postgres_vars = ["PGHOST", "PGUSER", "PGPASSWORD", "PGDATABASE", "PGPORT", "DATABASE_URL"]
        if all(os.environ.get(var) for var in postgres_vars):
            print("PostgreSQL database environment variables already set")
            return True
        
        # Try to check database status, which will fail if no PostgreSQL is available
        subprocess.run([sys.executable, "-c", "import os, psycopg2; conn = psycopg2.connect(os.environ.get('DATABASE_URL')); conn.close()"], check=True)
        print("PostgreSQL database connection successful")
        return True
    except Exception as e:
        print(f"PostgreSQL setup failed: {e}")
        return False

def setup_and_run():
    # Check if PostgreSQL environment variables are already set (Replit)
    postgres_ready = setup_postgres()
    
    if not postgres_ready:
        # Use SQLite as fallback for local development
        print("PostgreSQL not detected, using SQLite as fallback database")
        os.environ["DATABASE_URL"] = "sqlite:///trino_comparison.db"
    else:
        print("PostgreSQL database detected and ready to use")
    
    # Initialize the database
    print("Initializing database...")
    subprocess.run([sys.executable, "init_db.py"])
    
    # Run the application
    print("Starting application...")
    
    # Determine if we should use Flask development server or Gunicorn
    if os.environ.get("FLASK_ENV") == "development":
        # Development with Flask
        from main import app
        app.run(host="0.0.0.0", port=5000, debug=True)
    else:
        # Production with Gunicorn
        print("Starting with Gunicorn on port 5000...")
        subprocess.run(["gunicorn", "--bind", "0.0.0.0:5000", "main:app"])

if __name__ == "__main__":
    setup_and_run()