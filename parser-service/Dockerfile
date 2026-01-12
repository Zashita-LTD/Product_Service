# Parser Service Dockerfile - Multi-stage build
# Build stage
FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org

# Production stage
FROM python:3.11-slim as production

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app

# Install runtime dependencies for Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Playwright dependencies
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libatspi2.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libwayland-client0 \
    # Other
    ca-certificates \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=builder /root/.local /root/.local

# Set PATH
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV NODE_TLS_REJECT_UNAUTHORIZED=0

# Copy application code
COPY internal/ ./internal/
COPY config/ ./config/
COPY pkg/ ./pkg/
COPY cmd/ ./cmd/

# Create proxies file placeholder
RUN touch proxies.txt

# Create entrypoint script that installs Playwright browsers on first run
RUN echo '#!/bin/bash\n\
set -e\n\
if [ ! -f /root/.cache/ms-playwright/.installed ]; then\n\
  echo "Installing Playwright browsers..."\n\
  playwright install chromium || true\n\
  touch /root/.cache/ms-playwright/.installed\n\
fi\n\
exec "$@"\n\
' > /entrypoint.sh && chmod +x /entrypoint.sh

# Note: Running as root to avoid Playwright permission issues
# In production, consider proper user permissions

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "cmd/main.py"]
