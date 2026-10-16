# Anchorstone Capital Ltd — Flask API
# Production-ready with Gunicorn WSGI server

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies (gunicorn is pinned in requirements.txt)
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create logs directory
RUN mkdir -p /var/log/anchorstone && chmod 755 /var/log/anchorstone

# Create non-root user for security
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app && \
    chown -R appuser:appuser /var/log/anchorstone

USER appuser

# Health check (web: /api/v1/health; worker: its heartbeat file)
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD ["sh", "scripts/start.sh", "health"]

# Expose port
EXPOSE 5000

# One image, two processes. Run both, each in its own container:
#   docker run <image>          the API (gunicorn; WEB_CONCURRENCY workers, default 1)
#   docker run <image> worker   background jobs (emails, scheduled reports, backups)
# Scheduled work runs once however many web or worker containers are running.
ENTRYPOINT ["sh", "scripts/start.sh"]
CMD ["web"]
