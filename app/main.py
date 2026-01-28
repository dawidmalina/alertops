"""
AlertOps - Modular Alert Receiver

Main FastAPI application that loads and registers plugins.
"""

import sys
import logging
from pathlib import Path
from typing import Dict, Any, List
import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from app.models import WebhookPayload
from app.plugins.base import BasePlugin


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)


def load_config(config_path: str = "config.yaml") -> Dict[str, Any]:
    """
    Load configuration from YAML file.
    
    Args:
        config_path: Path to config file
        
    Returns:
        Configuration dictionary
    """
    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
        logger.info(f"Configuration loaded from {config_path}")
        return config
    except FileNotFoundError:
        logger.warning(f"Config file {config_path} not found, using defaults")
        return {
            "server": {"host": "0.0.0.0", "port": 8080, "log_level": "info"},
            "plugins": {"enabled": ["logger"]}
        }
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        raise


def load_plugins(config: Dict[str, Any]) -> List[BasePlugin]:
    """
    Dynamically load enabled plugins.
    
    Args:
        config: Application configuration
        
    Returns:
        List of initialized plugin instances
    """
    plugins = []
    enabled_plugins = config.get("plugins", {}).get("enabled", [])
    
    logger.info(f"Loading plugins: {enabled_plugins}")
    
    for plugin_name in enabled_plugins:
        try:
            # Dynamic import of plugin module
            module = __import__(
                f"app.plugins.{plugin_name}",
                fromlist=[f"{plugin_name.capitalize()}Plugin"]
            )
            
            # Get plugin class (convention: PluginNamePlugin)
            plugin_class_name = f"{plugin_name.capitalize()}Plugin"
            plugin_class = getattr(module, plugin_class_name)
            
            # Get plugin-specific config
            plugin_config = config.get("plugins", {}).get(plugin_name, {})
            
            # Initialize plugin
            plugin = plugin_class(config=plugin_config)
            
            # Validate configuration
            if not plugin.validate_config():
                logger.error(f"Invalid configuration for plugin '{plugin_name}'")
                continue
            
            plugins.append(plugin)
            logger.info(f"✓ Loaded plugin: {plugin_name}")
            
        except ImportError as e:
            logger.error(f"Failed to import plugin '{plugin_name}': {e}")
        except AttributeError as e:
            logger.error(f"Plugin class '{plugin_class_name}' not found in {plugin_name}: {e}")
        except Exception as e:
            logger.error(f"Error loading plugin '{plugin_name}': {e}")
    
    if not plugins:
        logger.warning("No plugins loaded! Server will start but won't process alerts.")
    
    return plugins


def create_app() -> FastAPI:
    """
    Create and configure FastAPI application.
    
    Returns:
        Configured FastAPI app instance
    """
    app = FastAPI(
        title="AlertOps - Alert Receiver",
        description="Modular alert receiver for Prometheus Alertmanager with plugin support",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc"
    )
    
    # Load configuration
    config = load_config()
    
    # Set log level from config
    log_level = config.get("server", {}).get("log_level", "info").upper()
    logging.getLogger().setLevel(getattr(logging, log_level))
    
    # Load and register plugins
    plugins = load_plugins(config)
    
    for plugin in plugins:
        app.include_router(plugin.router)
        logger.info(f"✓ Registered endpoint: /alert/{plugin.name}")
    
    # Store config and plugins in app state for access in routes
    app.state.config = config
    app.state.plugins = plugins
    
    @app.get("/")
    async def root():
        """Root endpoint with service info."""
        return {
            "service": "AlertOps",
            "version": "1.0.0",
            "status": "running",
            "plugins": [p.name for p in plugins],
            "endpoints": [f"/alert/{p.name}" for p in plugins]
        }
    
    @app.get("/health")
    async def health():
        """Health check endpoint."""
        return {
            "status": "healthy",
            "plugins_loaded": len(plugins)
        }
    
    @app.exception_handler(Exception)
    async def global_exception_handler(request, exc):
        """Global exception handler to prevent 500 errors from breaking Alertmanager."""
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=200,  # Return 200 to prevent Alertmanager retries
            content={
                "status": "error",
                "message": "Internal error occurred",
                "detail": str(exc)
            }
        )
    
    logger.info("=" * 60)
    logger.info("🚀 AlertOps Alert Receiver Started")
    logger.info("=" * 60)
    logger.info(f"Loaded {len(plugins)} plugin(s): {[p.name for p in plugins]}")
    logger.info(f"Available endpoints:")
    for plugin in plugins:
        logger.info(f"  POST /alert/{plugin.name}")
    logger.info("=" * 60)
    
    return app


# Create app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn
    
    # Load config for server settings
    config = load_config()
    server_config = config.get("server", {})
    
    host = server_config.get("host", "0.0.0.0")
    port = server_config.get("port", 8080)
    
    logger.info(f"Starting server on {host}:{port}")
    
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=False,
        log_level="info"
    )
