# Harbor Stock Analysis System
# Multi-arch build (supports linux/arm64 for Apple Silicon)
FROM python:3.11-slim

# System dependencies for scipy, matplotlib, lxml, and C extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    gfortran \
    libopenblas-dev \
    libfreetype6-dev \
    libpng-dev \
    libxml2-dev \
    libxslt1-dev \
    pkg-config \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer caching optimization)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Default: run market regime analysis
# Override at runtime with: docker compose run --rm harbor-engine python <script>
CMD ["python", "market_health/market_regime.py"]
