FROM python:3.9-slim

WORKDIR /app

# Copy application files
COPY breaking_changes_app.py /app/
COPY trino_breaking_changes.wsgi /app/
COPY templates/breaking_changes.html /app/templates/

# Install dependencies
RUN pip install --no-cache-dir flask flask-sqlalchemy beautifulsoup4 requests gunicorn

# Expose port 5000
EXPOSE 5000

# Create directory for SQLite database
RUN mkdir -p /app/instance && chmod 777 /app/instance

# Run the application
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--access-logfile", "-", "--error-logfile", "-", "breaking_changes_app:app"]