# Multi-arch Python base (supports linux/arm/v7, arm64, amd64)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# System deps (none required for pure-Python stack). Keep image small.
WORKDIR /app

# Install Python deps first for better caching
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the app
COPY . /app

# Default env suitable for container
ENV APP_HOST=0.0.0.0 \
    APP_PORT=5051

EXPOSE 5051

# Persist DB/uploads by mounting volumes to /app or bind-mount specific files/dirs
# VOLUME ["/app"]

# Start the Flask app (uses env APP_HOST/APP_PORT)
CMD ["python", "app.py"]
