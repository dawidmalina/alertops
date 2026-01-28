# Multi-stage build for AlertOps using Google Distroless
# https://github.com/GoogleContainerTools/distroless

# Stage 1: Builder - Install dependencies
FROM python:3.11-slim as builder

# Set working directory
WORKDIR /app

# Install build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements first for better layer caching
COPY requirements.txt .

# Install Python dependencies to /install directory
RUN pip install --no-cache-dir --prefix=/install --no-warn-script-location \
    -r requirements.txt

# Stage 2: Runtime - Distroless Python image
FROM gcr.io/distroless/python3-debian12:nonroot

# Set working directory
WORKDIR /app

# Copy Python dependencies from builder
COPY --from=builder /install/lib/python3.11/site-packages /app/site-packages

# Copy application code
COPY app/ /app/app/
COPY config.yaml /app/config.yaml

# Set Python path to include our site-packages
ENV PYTHONPATH=/app/site-packages:/app
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 8080

# Run as non-root user (distroless nonroot user)
USER nonroot:nonroot

# Run the application using the distroless Python interpreter
# The distroless image has python3 as the entrypoint
ENTRYPOINT ["/usr/bin/python3"]
CMD ["-m", "app.main"]
