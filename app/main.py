"""
AlertOps - Modular Alert Receiver

Main FastAPI application that loads and registers plugins.
"""

import sys
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, Any, List
import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from app.models import WebhookPayload
from app.plugins.base import BasePlugin
from app.ai_provider import create_ai_provider, AIProvider
from app.mcp_manager import MCPManager


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)


def load_config(config_path: str = "config.yaml") -> Dict[str, Any]:
    """
    Load configuration from YAML file with environment variable substitution.
    
    Args:
        config_path: Path to config file
        
    Returns:
        Configuration dictionary with env vars substituted
    """
    try:
        with open(config_path, "r") as f:
            config_text = f.read()
        
        # Simple environment variable substitution ${VAR_NAME}
        import re
        def replace_env_var(match):
            var_name = match.group(1)
            return os.environ.get(var_name, match.group(0))
        
        config_text = re.sub(r'\$\{(\w+)\}', replace_env_var, config_text)
        config = yaml.safe_load(config_text)
        
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


def load_plugins(
    config: Dict[str, Any],
    ai_provider: AIProvider = None,
    mcp_manager: MCPManager = None
) -> List[BasePlugin]:
    """
    Dynamically load enabled plugins with AI and MCP support.
    
    Args:
        config: Application configuration
        ai_provider: Optional AI provider instance
        mcp_manager: Optional MCP manager instance
        
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
            
            # Initialize plugin with AI and MCP support
            plugin = plugin_class(
                config=plugin_config,
                ai_provider=ai_provider,
                mcp_manager=mcp_manager
            )
            
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
    Create and configure FastAPI application with lifespan management.
    
    Returns:
        Configured FastAPI app instance
    """
    
    # Global services
    ai_provider: AIProvider = None
    mcp_manager: MCPManager = None
    
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """
        Lifespan context manager for startup and shutdown.
        """
        nonlocal ai_provider, mcp_manager
        
        # Load configuration
        config = load_config()
        
        # Set log level from config
        log_level = config.get("server", {}).get("log_level", "info").upper()
        logging.getLogger().setLevel(getattr(logging, log_level))
        
        logger.info("=" * 60)
        logger.info("🚀 AlertOps Starting...")
        logger.info("=" * 60)
        
        # Initialize AI Provider (if configured)
        if "ai" in config:
            try:
                ai_provider = create_ai_provider(config["ai"])
                logger.info(f"✓ AI Provider initialized: {config['ai'].get('provider', 'unknown')}")
            except Exception as e:
                logger.warning(f"⚠ AI Provider initialization failed: {e}")
                ai_provider = None
        else:
            logger.info("ℹ No AI configuration found, AI features disabled")
        
        # Initialize MCP Manager (if configured)
        if "mcp_servers" in config:
            try:
                mcp_manager = MCPManager(config["mcp_servers"])
                await mcp_manager.initialize()
                logger.info(f"✓ MCP Manager initialized with {len(config['mcp_servers'])} server(s)")
            except Exception as e:
                logger.warning(f"⚠ MCP Manager initialization failed: {e}")
                mcp_manager = None
        else:
            logger.info("ℹ No MCP servers configured, MCP features disabled")
        
        # Load and register plugins
        plugins = load_plugins(config, ai_provider, mcp_manager)
        
        for plugin in plugins:
            app.include_router(plugin.router)
            logger.info(f"✓ Registered endpoint: /alert/{plugin.name}")
        
        # Store in app state
        app.state.config = config
        app.state.plugins = plugins
        app.state.ai_provider = ai_provider
        app.state.mcp_manager = mcp_manager
        
        logger.info("=" * 60)
        logger.info(f"Loaded {len(plugins)} plugin(s): {[p.name for p in plugins]}")
        logger.info(f"Available endpoints:")
        for plugin in plugins:
            logger.info(f"  POST /alert/{plugin.name}")
        logger.info("=" * 60)
        
        yield
        
        # Cleanup on shutdown
        logger.info("Shutting down AlertOps...")
        
        if ai_provider:
            try:
                await ai_provider.close()
                logger.info("✓ AI Provider closed")
            except Exception as e:
                logger.error(f"Error closing AI provider: {e}")
        
        if mcp_manager:
            try:
                await mcp_manager.cleanup()
                logger.info("✓ MCP Manager closed")
            except Exception as e:
                logger.error(f"Error closing MCP manager: {e}")
        
        logger.info("Shutdown complete")
    
    app = FastAPI(
        title="AlertOps - Alert Receiver",
        description="Modular alert receiver for Prometheus Alertmanager with plugin support",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan
    )
    
    @app.get("/")
    async def root():
        """Root endpoint with service info."""
        plugins = getattr(app.state, 'plugins', [])
        return {
            "service": "AlertOps",
            "version": "1.0.0",
            "status": "running",
            "plugins": [p.name for p in plugins],
            "endpoints": [f"/alert/{p.name}" for p in plugins],
            "ai_enabled": app.state.ai_provider is not None,
            "mcp_enabled": app.state.mcp_manager is not None
        }
    
    @app.get("/health")
    async def health():
        """Health check endpoint."""
        plugins = getattr(app.state, 'plugins', [])
        return {
            "status": "healthy",
            "plugins_loaded": len(plugins),
            "ai_provider": "enabled" if app.state.ai_provider else "disabled",
            "mcp_manager": "enabled" if app.state.mcp_manager else "disabled"
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
