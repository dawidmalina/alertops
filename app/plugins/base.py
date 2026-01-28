"""
Base plugin interface for alert handlers.

All plugins must inherit from BasePlugin and implement the handle() method.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from fastapi import APIRouter
from app.models import WebhookPayload


class BasePlugin(ABC):
    """
    Abstract base class for alert handler plugins.
    
    Each plugin:
    - Has a unique name
    - Creates its own FastAPI router with endpoint /alert/{plugin_name}
    - Implements async handle() method for processing alerts
    - Can have custom configuration from config.yaml
    """
    
    def __init__(self, name: str, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the plugin.
        
        Args:
            name: Unique plugin name (used in endpoint path)
            config: Plugin-specific configuration from config.yaml
        """
        self.name = name
        self.config = config or {}
        self.router = APIRouter(
            prefix=f"/alert",
            tags=[f"plugin:{name}"]
        )
        self._setup_routes()
    
    def _setup_routes(self):
        """Set up FastAPI routes for this plugin."""
        @self.router.post(f"/{self.name}")
        async def handle_alert(payload: WebhookPayload):
            """
            Endpoint for receiving Alertmanager webhooks.
            
            Returns 200 OK immediately (as required by Alertmanager).
            Processing happens asynchronously.
            """
            try:
                # Call the plugin's handle method
                result = await self.handle(payload)
                return result
            except Exception as e:
                # Log error but still return 200 OK to prevent Alertmanager retries
                # for permanent errors
                import logging
                logging.error(f"Plugin {self.name} error: {str(e)}", exc_info=True)
                return {
                    "status": "error",
                    "plugin": self.name,
                    "message": str(e),
                    "alerts_processed": 0
                }
    
    @abstractmethod
    async def handle(self, payload: WebhookPayload) -> Dict[str, Any]:
        """
        Process the alert payload.
        
        This method must be implemented by each plugin.
        Should return a dict with processing results.
        
        Args:
            payload: Alertmanager webhook payload
            
        Returns:
            Dict with keys: status, plugin, message, alerts_processed
        """
        pass
    
    def validate_config(self) -> bool:
        """
        Validate plugin configuration.
        
        Override this method to add custom validation logic.
        
        Returns:
            True if config is valid, False otherwise
        """
        return True
