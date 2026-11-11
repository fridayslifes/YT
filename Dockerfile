# Multi-stage production container for FrameForge (v4.0 SOTA Engine)
FROM python:3.11-slim-bookworm AS base

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

# Install system media packages, audio tools, and fonts
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libx264-164 \
    fontconfig \
    fonts-dejavu-core \
    fonts-liberation \
    curl \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Create strictly single .venv at root
RUN python3 -m venv /app/.venv

# Copy dependencies first for Docker layer caching
COPY requirements.txt requirements-optional.txt ./

# Install core and production dependencies into strictly single .venv
RUN /app/.venv/bin/pip install --no-cache-dir --upgrade pip && \
    /app/.venv/bin/pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Ensure scripts are executable
RUN chmod +x check.sh

# Run self-check at build time
RUN /app/.venv/bin/python -m ruff check tools/ tests/ && \
    /app/.venv/bin/python -m compileall tools/ tests/

ENTRYPOINT ["/app/.venv/bin/python", "tools/master.py"]
CMD ["--help"]
