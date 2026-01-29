# AlertOps - Modular Alert Receiver

[![Build and Push Docker Image](https://github.com/dawidmalina/alertops/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/dawidmalina/alertops/actions/workflows/docker-publish.yml)

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
docker pull ghcr.io/dawidmalina/alertops:latest

# Run the container
docker run -d \
  -p 8080:8080 \
  -v $(pwd)/config.yaml:/app/config.yaml \
  --name alertops \
  ghcr.io/dawidmalina/alertops:latest

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
    image: ghcr.io/dawidmalina/alertops:latest
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
- `/alert/dump` - Outputs complete raw payload in JSON format (useful for debugging/development)
- `/alert/jira` - Creates Jira tickets (coming soon)
- `/alert/webhook` - Forwards to other webhooks (coming soon)

## Configuration

Edit `config.yaml`:

```yaml
plugins:
  enabled:
    - logger
  
  logger:
    format: "json"  # Options: "json" or "text"
    include_labels: true
    include_annotations: true
```

### Logger Plugin Formats

The logger plugin supports two output formats:

#### JSON Format (default)
Structured JSON output with all fields, perfect for log aggregation and parsing:

```json
{
  "timestamp": "2026-01-29T10:37:34.371848",
  "version": "4",
  "groupKey": "{}:{alertname=\"TestAlert\"}",
  "status": "firing",
  "receiver": "webhook-test",
  "alerts_count": 1,
  "alerts": [
    {
      "status": "firing",
      "labels": {
        "alertname": "TestAlert",
        "severity": "warning"
      },
      "annotations": {
        "description": "This is a test alert",
        "summary": "Test Alert Summary"
      }
    }
  ]
}
```

#### Text Format
Clean, markdown-style output similar to Grafana's Alertmanager notifications, perfect for human readability:

```
*Alert:* Test Alert Summary - `warning`

*Description:* This is a test alert from Alertmanager

*Details:*
  • *alertname:* `TestAlert`
  • *instance:* `localhost:9090`
  • *job:* `test-job`
  • *severity:* `warning`
```

To use text format, set `format: "text"` in your logger configuration.

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

## Dump Plugin - For Development & Debugging

The `dump` plugin outputs the complete raw JSON payload to stdout, making it perfect for:

- **Debugging**: See exactly what data Alertmanager is sending
- **Plugin Development**: Capture real payloads to use as test data
- **Testing**: Understand the structure of incoming webhooks

### Usage

The dump plugin is **enabled by default**. To use it:

1. Configure Alertmanager to send alerts to the dump endpoint:

```yaml
receivers:
  - name: 'alertops-dump'
    webhook_configs:
      - url: 'http://localhost:8080/alert/dump'
        send_resolved: true
```

2. Trigger an alert and check the application logs/stdout for the JSON payload

3. Copy the dumped payload for use in plugin development or testing

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
