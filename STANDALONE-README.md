# Trino Breaking Changes Comparison - Standalone App

This standalone application extracts just the Breaking Changes Comparison feature from the X:SideBySide Trino application, allowing you to deploy it independently.

## Overview

The Trino Breaking Changes Comparison tool allows you to:
- Compare breaking changes between any two Trino versions
- View new features introduced between versions
- Cache comparison results for faster access
- Easily identify compatibility issues when upgrading

## Files Included

- **breaking_changes_app.py**: The main Flask application
- **templates/breaking_changes.html**: The HTML template for the user interface
- **trino_breaking_changes.wsgi**: WSGI file for Apache deployment
- **setup_ubuntu_apache.sh**: Script for setting up the app on Ubuntu with Apache
- **Dockerfile**: For building a Docker image
- **docker-compose.yml**: For easy Docker deployment

## Deployment Options

### Option 1: Docker Deployment (Easiest)

This method uses Docker Compose for a simple deployment:

1. Make sure Docker and Docker Compose are installed on your server
2. Copy all files to your server
3. Run the following commands:

```bash
# Build and start the container
docker-compose up -d

# View logs
docker-compose logs -f
```

The application will be available at http://your-server-ip:8080/

### Option 2: Ubuntu with Apache

To deploy on Ubuntu with Apache:

1. Copy the following files to your server:
   - breaking_changes_app.py
   - trino_breaking_changes.wsgi
   - templates/breaking_changes.html
   - setup_ubuntu_apache.sh

2. Make the setup script executable:
   ```bash
   chmod +x setup_ubuntu_apache.sh
   ```

3. Run the setup script:
   ```bash
   ./setup_ubuntu_apache.sh
   ```

4. Modify the Apache configuration in /etc/apache2/sites-available/trino-breaking-changes.conf to use your domain name

5. If you want to use HTTPS, set up SSL with Let's Encrypt:
   ```bash
   sudo apt install certbot python3-certbot-apache
   sudo certbot --apache -d your-domain.com
   ```

### Option 3: Manual Installation

1. Install required packages:
   ```bash
   pip install flask flask-sqlalchemy beautifulsoup4 requests gunicorn
   ```

2. Create necessary directories:
   ```bash
   mkdir -p templates instance
   ```

3. Copy files to appropriate locations:
   - breaking_changes_app.py to the root directory
   - breaking_changes.html to the templates directory

4. Run the application:
   ```bash
   python breaking_changes_app.py
   ```

   Or for production with Gunicorn:
   ```bash
   gunicorn --bind 0.0.0.0:5000 breaking_changes_app:app
   ```

## Configuration

The application uses SQLite by default, storing the database in the instance folder. If you want to use a different database:

1. Modify the `SQLALCHEMY_DATABASE_URI` in breaking_changes_app.py
2. Install any additional database drivers needed (e.g., psycopg2 for PostgreSQL)

## Troubleshooting

1. **Versions not appearing in dropdowns**:
   - Check if the database was created properly in the instance folder
   - Verify that the app has write permissions to the instance directory

2. **Apache errors**:
   - Check Apache error logs: `sudo tail -f /var/log/apache2/error.log`
   - Ensure the WSGI module is enabled: `sudo a2enmod wsgi`
   - Verify permissions on the application directory

3. **Docker issues**:
   - Check container logs: `docker-compose logs`
   - Ensure ports are not already in use
   - Verify that Docker has enough resources allocated

## Security Considerations

For production deployments:
- Set `app.secret_key` to a secure random string
- Consider using a more robust database like PostgreSQL instead of SQLite
- Set up SSL/TLS encryption with a valid certificate
- Configure the application behind a proper reverse proxy