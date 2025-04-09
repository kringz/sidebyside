# Trino Version Comparison Tool

A Python web application for comprehensive Trino cluster deployment and version comparison, enabling developers to streamline configuration management and performance analysis.

## Features

- Deploy and manage two Trino clusters with different versions
- Compare query execution and performance between versions
- Configure and manage multiple catalog connectors:
  - Hive
  - Iceberg
  - Delta Lake
  - MySQL/MariaDB
  - PostgreSQL
  - SQL Server
  - DB2
  - ClickHouse
  - Pinot
  - Elasticsearch
- Query history tracking with timing and result comparison
- Dynamic Docker configuration for different environments
- Visual version compatibility checker

## Prerequisites

- Python 3.8+ installed
- Docker installed and running (for full functionality)
- Browser with JavaScript enabled

## Quick Start

### For Mac/Linux Users

Simply run the start script:

```bash
./start_app.sh
```

### For Windows Users

Double-click the batch file or run:

```
start_app.bat
```

### Manual Setup

If the scripts don't work for you, you can set up manually:

1. Create a virtual environment:
   ```
   python -m venv venv
   source venv/bin/activate  # On Mac/Linux
   venv\Scripts\activate     # On Windows
   ```

2. Install dependencies:
   ```
   pip install flask flask-sqlalchemy gunicorn psycopg2-binary pyyaml docker trafilatura trino email-validator
   ```

3. Initialize the database:
   ```
   python init_db.py
   ```

4. Run the application:
   ```
   python run.py
   ```

5. Open your browser at:
   ```
   http://localhost:5000
   ```

## Docker Connection Settings

If using Docker Desktop for Mac, set the "Trino Connect Host" to `host.docker.internal` in the Docker Connection Settings section.

## Development

The application uses:
- Flask web framework
- Docker SDK for Python
- SQLAlchemy ORM
- Bootstrap for UI
- PostgreSQL for persistent storage (with SQLite fallback)

## License

This project is open source.