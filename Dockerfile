# Multi-stage build for portable library manager
# Build targets: slim (default), full

FROM python:3.11-slim AS base

WORKDIR /app

# Install system dependencies for base
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Create runtime directories
RUN mkdir -p /app/var /data/libraries

# Slim target - Python libs only (Pillow, mutagen, libmagic)
FROM base AS slim

EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]

# Full target - adds ffmpeg, exiftool, poppler-utils
FROM base AS full

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libimage-exiftool-perl \
    poppler-utils \
    file \
    && rm -rf /var/lib/apt/lists/*

EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]

