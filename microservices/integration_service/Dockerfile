# Integration Service Dockerfile
# UK Management Bot - Integration Service

FROM python:3.11-slim

LABEL maintainer="UK Management Bot Team"
LABEL service="integration-service"
LABEL version="1.0.0"

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8009/health || exit 1

# Expose port
EXPOSE 8009

# Run application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8009", "--workers", "4"]
