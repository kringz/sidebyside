#!/bin/bash
# Trino Breaking Changes App Installation Script for Ubuntu with Apache

# Exit on error
set -e

echo "========================================================"
echo "Trino Breaking Changes App - Ubuntu & Apache Setup"
echo "========================================================"

# Update and install required packages
echo "Updating package lists and installing required packages..."
sudo apt-get update
sudo apt-get install -y python3 python3-pip apache2 libapache2-mod-wsgi-py3 python3-venv

# Create a directory for the app
echo "Creating application directory..."
sudo mkdir -p /var/www/trino-breaking-changes
sudo chown $(whoami):$(whoami) /var/www/trino-breaking-changes

# Copy application files to the directory
echo "Please copy these files to your server into /var/www/trino-breaking-changes:"
echo "- breaking_changes_app.py"
echo "- trino_breaking_changes.wsgi"
echo "- templates/breaking_changes.html"

# Create a virtual environment and install dependencies
echo "Setting up virtual environment and installing dependencies..."
python3 -m venv /var/www/trino-breaking-changes/venv
source /var/www/trino-breaking-changes/venv/bin/activate
pip install flask flask-sqlalchemy requests beautifulsoup4 gunicorn

# Set appropriate permissions
echo "Setting appropriate permissions..."
sudo chown -R www-data:www-data /var/www/trino-breaking-changes
sudo chmod -R 755 /var/www/trino-breaking-changes

# Create Apache virtual host configuration
echo "Creating Apache virtual host configuration..."
sudo tee /etc/apache2/sites-available/trino-breaking-changes.conf > /dev/null << EOF
<VirtualHost *:80>
    ServerName your-domain.com
    ServerAdmin webmaster@your-domain.com
    
    DocumentRoot /var/www/trino-breaking-changes
    
    WSGIDaemonProcess trino-breaking-changes python-home=/var/www/trino-breaking-changes/venv python-path=/var/www/trino-breaking-changes
    WSGIProcessGroup trino-breaking-changes
    WSGIScriptAlias / /var/www/trino-breaking-changes/trino_breaking_changes.wsgi
    
    <Directory /var/www/trino-breaking-changes>
        WSGIScriptReloading On
        Require all granted
        Options FollowSymLinks
        AllowOverride None
    </Directory>
    
    ErrorLog \${APACHE_LOG_DIR}/trino-breaking-changes_error.log
    CustomLog \${APACHE_LOG_DIR}/trino-breaking-changes_access.log combined
</VirtualHost>
EOF

# Enable the site and restart Apache
echo "Enabling the site and restarting Apache..."
sudo a2ensite trino-breaking-changes.conf
sudo a2enmod wsgi
sudo systemctl restart apache2

# Create a test database
echo "Creating a test SQLite database..."
sudo -u www-data mkdir -p /var/www/trino-breaking-changes/instance
sudo -u www-data python3 -c "
import sqlite3
conn = sqlite3.connect('/var/www/trino-breaking-changes/instance/breaking_changes.db')
cursor = conn.cursor()
cursor.execute('CREATE TABLE IF NOT EXISTS trino_version (id INTEGER PRIMARY KEY, version TEXT UNIQUE NOT NULL, create_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
cursor.execute('CREATE TABLE IF NOT EXISTS version_comparison (id INTEGER PRIMARY KEY, from_version TEXT NOT NULL, to_version TEXT NOT NULL, comparison_data TEXT, create_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, expire_date TIMESTAMP, UNIQUE(from_version, to_version))')
versions = ['401', '406', '414', '424', '438', '442', '446', '451', '458', '465', '473', '474']
for v in versions:
    try:
        cursor.execute('INSERT INTO trino_version (version) VALUES (?)', (v,))
    except sqlite3.IntegrityError:
        pass
conn.commit()
conn.close()
"

echo "========================================================"
echo "Installation complete!"
echo "========================================================"
echo "Your Trino Breaking Changes application should now be accessible at: http://your-domain.com"
echo ""
echo "Important notes:"
echo "1. Replace 'your-domain.com' in the Apache configuration with your actual domain name"
echo "2. If you want to use HTTPS, you should set up SSL certificates using Let's Encrypt"
echo "3. For production use, consider setting up a more robust database like PostgreSQL"
echo "4. Ensure your server's firewall allows HTTP (port 80) and HTTPS (port 443) traffic"
echo "========================================================"