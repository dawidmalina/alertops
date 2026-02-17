"""
AI Provider abstraction for generating text summaries.

Supports multiple AI providers with a common interface.
Currently implements GitHub Models API with future support for MCP-based AI.
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import httpx

logger = logging.getLogger(__name__)


class AIProvider(ABC):
    """
    Abstract base class for AI providers.
    
    Allows plugins to generate AI text with custom prompts
    while abstracting the underlying AI service.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize AI provider with configuration.
        
        Args:
            config: Global AI configuration from config.yaml
        """
        self.config = config
    
    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: str,
        **kwargs
    ) -> str:
        """
        Generate text using AI model.
        
        Args:
            prompt: User prompt with content to process
            system_prompt: System prompt defining AI behavior/role
            **kwargs: Additional provider-specific parameters
                     (temperature, max_tokens, model, etc.)
        
        Returns:
            Generated text response
        """
        pass


class GitHubModelsProvider(AIProvider):
    """
    AI Provider using GitHub Models API.
    
    Supports GPT-4o, GPT-4o-mini, Claude, and other models
    available through GitHub Models.
    """
    
    API_URL = "https://models.inference.ai.azure.com/chat/completions"
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize GitHub Models provider.
        
        Config should contain:
            - github_pat: GitHub Personal Access Token
            - model: Model name (default: gpt-4o-mini)
            - temperature: Sampling temperature (default: 0.3)
            - max_tokens: Maximum tokens (default: 300)
        """
        super().__init__(config)
        
        self.github_pat = config.get("github_pat")
        if not self.github_pat:
            raise ValueError("github_pat is required for GitHubModelsProvider")
        
        # Default parameters
        self.default_model = config.get("model", "gpt-4o-mini")
        self.default_temperature = config.get("temperature", 0.3)
        self.default_max_tokens = config.get("max_tokens", 300)
        
        # HTTP client with connection pooling
        self.client = httpx.AsyncClient(timeout=30.0)
        
        logger.info(f"Initialized GitHubModelsProvider with model: {self.default_model}")
    
    async def generate(
        self,
        prompt: str,
        system_prompt: str,
        **kwargs
    ) -> str:
        """
        Generate text using GitHub Models API.
        
        Args:
            prompt: User prompt
            system_prompt: System prompt
            **kwargs: Overrides for model, temperature, max_tokens
        
        Returns:
            Generated text
            
        Raises:
            httpx.HTTPError: On API errors
            ValueError: On invalid response
        """
        # Merge kwargs with defaults
        model = kwargs.get("model", self.default_model)
        temperature = kwargs.get("temperature", self.default_temperature)
        max_tokens = kwargs.get("max_tokens", self.default_max_tokens)
        
        payload = {
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        headers = {
            "Authorization": f"Bearer {self.github_pat}",
            "Content-Type": "application/json"
        }
        
        try:
            response = await self.client.post(
                self.API_URL,
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            
            result = response.json()
            generated_text = result["choices"][0]["message"]["content"]
            
            logger.debug(f"Generated text ({len(generated_text)} chars) with model {model}")
            return generated_text
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.error("GitHub Models API rate limit exceeded")
                raise ValueError("AI rate limit exceeded, please try again later")
            elif e.response.status_code == 401:
                logger.error("GitHub Models API authentication failed")
                raise ValueError("AI authentication failed, check github_pat")
            else:
                logger.error(f"GitHub Models API error: {e.response.status_code}")
                raise
        
        except Exception as e:
            logger.error(f"AI generation failed: {e}")
            raise
    
    async def close(self):
        """Close HTTP client connection."""
        await self.client.aclose()
        logger.debug("Closed GitHubModelsProvider HTTP client")


class MCPAIProvider(AIProvider):
    """
    AI Provider using MCP (Model Context Protocol) server.
    
    Future implementation for using remote MCP servers
    that provide AI capabilities.
    
    Example MCP servers:
    - Claude Desktop MCP bridge
    - OpenAI MCP wrapper
    - Custom AI gateway with MCP interface
    """
    
    def __init__(self, config: Dict[str, Any], mcp_manager):
        """
        Initialize MCP AI provider.
        
        Args:
            config: AI configuration
            mcp_manager: MCPManager instance for calling MCP tools
        """
        super().__init__(config)
        self.mcp_manager = mcp_manager
        self.mcp_server_name = config.get("mcp_server", "ai")
        self.mcp_tool_name = config.get("mcp_tool", "generate_text")
        
        logger.info(f"Initialized MCPAIProvider using server: {self.mcp_server_name}")
    
    async def generate(
        self,
        prompt: str,
        system_prompt: str,
        **kwargs
    ) -> str:
        """
        Generate text using MCP AI server.
        
        Args:
            prompt: User prompt
            system_prompt: System prompt
            **kwargs: Additional parameters for MCP tool
        
        Returns:
            Generated text
        """
        # Call MCP tool for text generation
        result = await self.mcp_manager.call_tool(
            server_name=self.mcp_server_name,
            tool_name=self.mcp_tool_name,
            arguments={
                "prompt": prompt,
                "system_prompt": system_prompt,
                **kwargs
            }
        )
        
        # Extract text from MCP response
        # Format depends on MCP server implementation
        if isinstance(result, dict):
            return result.get("content", result.get("text", str(result)))
        elif isinstance(result, str):
            return result
        else:
            return str(result)


def create_ai_provider(
    config: Dict[str, Any],
    mcp_manager=None
) -> AIProvider:
    """
    Factory function to create AI provider based on configuration.
    
    Args:
        config: AI configuration from config.yaml
        mcp_manager: Optional MCPManager for MCP-based AI
    
    Returns:
        Configured AIProvider instance
    
    Raises:
        ValueError: If provider type is unsupported
    """
    provider_type = config.get("provider", "github_models")
    
    if provider_type == "github_models":
        return GitHubModelsProvider(config)
    elif provider_type == "mcp":
        if not mcp_manager:
            raise ValueError("mcp_manager required for MCP AI provider")
        return MCPAIProvider(config, mcp_manager)
    else:
        raise ValueError(f"Unsupported AI provider: {provider_type}")
