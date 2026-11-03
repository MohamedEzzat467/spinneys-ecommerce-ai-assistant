# Production Dockerfile for Spinneys E-Commerce Store & AI Assistant Backend
# Optimized for 100% Free-tier container hosting (Render, Hugging Face Spaces, Fly.io, Railway)

FROM python:3.10-slim

# Prevent python from writing pyc files and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    RETRIEVAL_MODE=bm25

WORKDIR /app

# Install minimal OS dependencies for compilation and health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source code and catalog datasets
COPY app/ ./app/
COPY scripts/ ./scripts/
COPY data/retrieval_meta.parquet ./data/retrieval_meta.parquet
COPY data/retrieval_docs.parquet ./data/retrieval_docs.parquet

# Prepare runtime logging directory
RUN mkdir -p logs

# Expose container port
EXPOSE 8000

# Container healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Launch FastAPI ASGI server
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
