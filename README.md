# AlertOps - Modular Alert Receiver

[![Build and Push Docker Image](https://github.com/malina/alertops/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/malina/alertops/actions/workflows/docker-publish.yml)

A flexible, plugin-based alert receiver for Prometheus Alertmanager with support for custom alert processing actions.

## Features

- 🔌 **Plugin Architecture**: Easy to add new alert handlers
- 🚀 **FastAPI**: Modern async Python web framework
- ✅ **Alertmanager Compatible**: Follows Prometheus Alertmanager webhook specification
- ⚡ **Fast Response**: Returns 200 OK immediately, processes asynchronously
- 📝 **Configurable**: YAML-based configuration
- 🐳 **Distroless Docker**: Minimal, secure container images

## Quick Start

### Running Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Run the server
python -m app.main

# Or with uvicorn directly
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

### Running with Docker

#### Using pre-built image from GitHub Container Registry

```bash
# Pull the latest image
docker pull ghcr.io/malina/alertops:latest

# Run the container
docker run -d \
  -p 8080:8080 \
  -v $(pwd)/config.yaml:/app/config.yaml \
  --name alertops \
  ghcr.io/malina/alertops:latest

# View logs
docker logs -f alertops

# Test the endpoint
curl http://localhost:8080/health
```

#### Building locally

```bash
# Build the image
docker build -t alertops:latest .

# Run the container
docker run -d \
  -p 8080:8080 \
  -v $(pwd)/config.yaml:/app/config.yaml \
  --name alertops \
  alertops:latest
```

### Docker Compose (optional)

```yaml
version: '3.8'
services:
  alertops:
    image: ghcr.io/malina/alertops:latest
    # Or build locally:
    # build: .
    ports:
      - "8080:8080"
    volumes:
      - ./config.yaml:/app/config.yaml:ro
    restart: unless-stopped
```

## Architecture

Each plugin registers its own endpoint at `/alert/{plugin_name}`:

- `/alert/logger` - Logs alerts to stdout
- `/alert/jira` - Creates Jira tickets (coming soon)
- `/alert/webhook` - Forwards to other webhooks (coming soon)

## Configuration

Edit `config.yaml`:

```yaml
plugins:
  enabled:
    - logger
  
  logger:
    format: "json"
```

## Alertmanager Configuration

```yaml
receivers:
  - name: 'alertops-logger'
    webhook_configs:
      - url: 'http://localhost:8080/alert/logger'
        send_resolved: true
```

## Adding New Plugins

1. Create a new file in `app/plugins/your_plugin.py`
2. Inherit from `BasePlugin`
3. Implement `async def handle(self, payload: WebhookPayload)`
4. Register the router in your plugin
5. Add plugin name to `config.yaml`

See `app/plugins/logger.py` for an example.

## Docker Image Details

This project uses [Google Distroless](https://github.com/GoogleContainerTools/distroless) base images for:

- **Minimal attack surface**: No shell, package managers, or unnecessary binaries
- **Small image size**: Only Python runtime and application dependencies (~88 MB)
- **Security**: Runs as non-root user by default
- **Reproducibility**: Immutable, minimal base layer

### Image Layers
1. **Builder stage**: `python:3.11-slim` - Installs dependencies
2. **Runtime stage**: `gcr.io/distroless/python3-debian12:nonroot` - Final minimal image

### Security Features
- Non-root user (UID 65532)
- No shell access
- Minimal dependencies
- Distroless Python 3 runtime only

### Available Image Tags

Images are automatically built and published to GitHub Container Registry:

- `ghcr.io/dawidmalina/alertops:latest` - Latest build from main branch
- `ghcr.io/dawidmalina/alertops:main` - Latest main branch
- `ghcr.io/dawidmalina/alertops:v1.0.0` - Specific version tags
- `ghcr.io/dawidmalina/alertops:sha-abc123` - Specific commit SHA

### CI/CD Pipeline

Every push to `main` triggers:
1. Docker build with caching
2. Automatic tagging (latest, branch, SHA)
3. Push to GitHub Container Registry
