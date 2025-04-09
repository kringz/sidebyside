import os
import subprocess
import sys
import time

def setup_and_run():
    # Use SQLite by default for simplicity and local development
    if not os.environ.get("DATABASE_URL"):
        print("Setting up SQLite database for local development")
        os.environ["DATABASE_URL"] = "sqlite:///trino_comparison.db"
    else:
        db_url = os.environ.get("DATABASE_URL")
        if db_url:
            print(f"Using database from environment: {db_url[:10]}...")
        else:
            print("DATABASE_URL environment variable is set but empty")
    
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