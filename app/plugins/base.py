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
    - Can access AI provider and MCP manager for advanced capabilities
    """
    
    def __init__(
        self,
        name: str,
        config: Optional[Dict[str, Any]] = None,
        ai_provider: Optional[Any] = None,
        mcp_manager: Optional[Any] = None
    ):
        """
        Initialize the plugin.
        
        Args:
            name: Unique plugin name (used in endpoint path)
            config: Plugin-specific configuration from config.yaml
            ai_provider: Optional AIProvider instance for text generation
            mcp_manager: Optional MCPManager instance for MCP operations
        """
        self.name = name
        self.config = config or {}
        self.ai = ai_provider
        self.mcp = mcp_manager
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
    
    async def generate_ai_text(
        self,
        prompt: str,
        system_prompt: str,
        **kwargs
    ) -> Optional[str]:
        """
        Helper method to generate AI text.
        
        Uses the AIProvider if available, otherwise returns None.
        Plugins can use this for AI-powered features like summarization.
        
        Args:
            prompt: User prompt
            system_prompt: System prompt defining AI behavior
            **kwargs: Additional parameters (temperature, max_tokens, etc.)
        
        Returns:
            Generated text or None if AI not available
        """
        if not self.ai:
            import logging
            logging.warning(f"Plugin {self.name}: AI provider not available")
            return None
        
        try:
            return await self.ai.generate(prompt, system_prompt, **kwargs)
        except Exception as e:
            import logging
            logging.error(f"Plugin {self.name}: AI generation failed - {e}")
            return None
    
    async def call_mcp_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Optional[Any]:
        """
        Helper method to call MCP tool.
        
        Uses the MCPManager if available, otherwise returns None.
        Plugins can use this for MCP-based integrations (Jira, K8s, etc.)
        
        Args:
            server_name: MCP server name (e.g., "jira", "kubernetes")
            tool_name: Tool to call (e.g., "create_issue")
            arguments: Tool arguments
        
        Returns:
            Tool result or None if MCP not available
            
        Raises:
            Exception: On MCP errors (connection, timeout, etc.)
        """
        if not self.mcp:
            import logging
            logging.warning(f"Plugin {self.name}: MCP manager not available")
            return None
        
        try:
            return await self.mcp.call_tool(server_name, tool_name, arguments)
        except Exception as e:
            import logging
            logging.error(
                f"Plugin {self.name}: MCP call failed "
                f"({server_name}.{tool_name}) - {e}"
            )
            raise
