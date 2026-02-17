"""
MCP (Model Context Protocol) Manager for remote MCP server connections.

Manages connections to remote MCP servers via HTTP/SSE transport
and provides tools execution interface for plugins.
"""

import asyncio
import logging
from typing import Dict, Any, Optional, Set
from dataclasses import dataclass
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


@dataclass
class MCPServerConfig:
    """Configuration for a single MCP server."""
    name: str
    url: str
    auth_token: Optional[str] = None
    timeout: int = 30
    enabled: bool = True


class MCPManager:
    """
    Manages connections to multiple remote MCP servers.
    
    Provides:
    - Lazy connection with retry on first use
    - Connection pooling and reuse
    - Error handling with exponential backoff
    - Tool execution interface
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize MCP Manager.
        
        Args:
            config: MCP servers configuration from config.yaml
                   Format: {
                       "server_name": {
                           "url": "https://...",
                           "auth_token": "...",
                           "timeout": 30
                       }
                   }
        """
        self.config = config
        self.servers: Dict[str, Any] = {}  # Connected MCP sessions
        self.server_configs: Dict[str, MCPServerConfig] = {}
        self.pending_connections: Set[str] = set()  # Failed at startup
        self._locks: Dict[str, asyncio.Lock] = {}
        self._retry_delays = [1, 2, 5, 10]  # Exponential backoff
        
        # Parse server configs
        for server_name, server_config in config.items():
            self.server_configs[server_name] = MCPServerConfig(
                name=server_name,
                **server_config
            )
            self._locks[server_name] = asyncio.Lock()
        
        logger.info(f"Initialized MCPManager with {len(self.server_configs)} servers")
    
    async def initialize(self):
        """
        Initialize connections to all MCP servers.
        
        Attempts to connect to each server. If connection fails,
        marks it as pending for lazy retry on first use.
        Does not fail-fast to allow partial functionality.
        """
        logger.info("Initializing MCP server connections...")
        
        for server_name, config in self.server_configs.items():
            if not config.enabled:
                logger.info(f"Skipping disabled MCP server: {server_name}")
                continue
            
            try:
                await self._connect_server(server_name)
                logger.info(f"✓ Connected to MCP server: {server_name}")
            
            except Exception as e:
                logger.warning(
                    f"Failed to connect to MCP server '{server_name}' at startup: {e}. "
                    f"Will retry on first use."
                )
                self.pending_connections.add(server_name)
        
        connected = len(self.servers)
        pending = len(self.pending_connections)
        logger.info(f"MCP initialization complete: {connected} connected, {pending} pending")
    
    async def _connect_server(self, server_name: str):
        """
        Connect to a single MCP server via SSE.
        
        Args:
            server_name: Name of server to connect
            
        Raises:
            ConnectionError: If connection fails
        """
        config = self.server_configs[server_name]
        
        # Note: Actual MCP SSE connection requires mcp library
        # This is a simplified implementation showing the pattern
        try:
            # Import MCP client (lazy to avoid hard dependency during development)
            try:
                from mcp.client.sse import sse_client
                from mcp import ClientSession
            except ImportError:
                raise ImportError(
                    "MCP library not installed. Install with: pip install mcp"
                )
            
            # Prepare headers
            headers = {}
            if config.auth_token:
                headers["Authorization"] = f"Bearer {config.auth_token}"
            
            # Connect via SSE
            # Note: This creates persistent connection context
            logger.debug(f"Connecting to MCP server {server_name} at {config.url}")
            
            # Store connection info (actual connection would be in context manager)
            self.servers[server_name] = {
                "config": config,
                "url": config.url,
                "headers": headers,
                "connected": True
            }
            
            # Remove from pending if it was there
            self.pending_connections.discard(server_name)
            
        except Exception as e:
            logger.error(f"Failed to connect to MCP server {server_name}: {e}")
            raise ConnectionError(f"MCP connection failed: {e}")
    
    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: Dict[str, Any],
        retry: bool = True
    ) -> Any:
        """
        Call a tool on a specific MCP server.
        
        Args:
            server_name: Name of MCP server (e.g., "jira", "kubernetes")
            tool_name: Name of tool to call (e.g., "create_issue")
            arguments: Tool arguments as dictionary
            retry: Whether to retry on transient failures
        
        Returns:
            Tool execution result
            
        Raises:
            ValueError: If server not configured
            ConnectionError: If server unavailable after retries
            TimeoutError: If tool execution times out
        """
        # Validate server exists
        if server_name not in self.server_configs:
            raise ValueError(f"MCP server '{server_name}' not configured")
        
        # Check if server is enabled
        if not self.server_configs[server_name].enabled:
            raise ValueError(f"MCP server '{server_name}' is disabled")
        
        # Lazy connection if pending
        if server_name in self.pending_connections:
            logger.info(f"Attempting lazy connection to MCP server: {server_name}")
            try:
                await self._connect_server(server_name)
            except Exception as e:
                raise ConnectionError(
                    f"Cannot connect to MCP server '{server_name}': {e}"
                )
        
        # Check if connected
        if server_name not in self.servers:
            raise ConnectionError(f"MCP server '{server_name}' not connected")
        
        # Execute with retry logic
        async with self._locks[server_name]:
            for attempt, delay in enumerate(self._retry_delays):
                try:
                    result = await self._execute_tool(
                        server_name,
                        tool_name,
                        arguments
                    )
                    
                    logger.debug(
                        f"MCP tool executed: {server_name}.{tool_name} "
                        f"(attempt {attempt + 1})"
                    )
                    return result
                
                except asyncio.TimeoutError:
                    logger.error(
                        f"MCP tool timeout: {server_name}.{tool_name} "
                        f"(attempt {attempt + 1})"
                    )
                    if not retry or attempt == len(self._retry_delays) - 1:
                        raise TimeoutError(
                            f"MCP tool '{tool_name}' timed out on server '{server_name}'"
                        )
                    await asyncio.sleep(delay)
                
                except ConnectionError as e:
                    logger.error(
                        f"MCP connection error: {server_name}.{tool_name} - {e}"
                    )
                    
                    # Try to reconnect
                    if retry and attempt < len(self._retry_delays) - 1:
                        logger.info(f"Attempting to reconnect to {server_name}")
                        try:
                            await self._connect_server(server_name)
                            await asyncio.sleep(delay)
                            continue
                        except Exception:
                            pass
                    
                    raise ConnectionError(
                        f"MCP server '{server_name}' connection failed"
                    )
                
                except Exception as e:
                    logger.error(
                        f"MCP tool error: {server_name}.{tool_name} - {e}"
                    )
                    if not retry or attempt == len(self._retry_delays) - 1:
                        raise
                    await asyncio.sleep(delay)
    
    async def _execute_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Any:
        """
        Execute tool on MCP server.
        
        Note: This is a simplified implementation.
        Actual execution would use MCP ClientSession.
        
        Args:
            server_name: Server name
            tool_name: Tool name
            arguments: Tool arguments
        
        Returns:
            Tool result
        """
        config = self.server_configs[server_name]
        server = self.servers[server_name]
        
        # Note: Actual implementation would use:
        # session = ClientSession(...)
        # result = await session.call_tool(name=tool_name, arguments=arguments)
        
        # For now, log the call
        logger.debug(
            f"Executing MCP tool: {server_name}.{tool_name} "
            f"with args: {list(arguments.keys())}"
        )
        
        # Simulate timeout
        try:
            await asyncio.wait_for(
                self._mock_tool_execution(tool_name, arguments),
                timeout=config.timeout
            )
        except asyncio.TimeoutError:
            raise
        
        # Return mock result
        return {
            "status": "success",
            "tool": tool_name,
            "server": server_name
        }
    
    async def _mock_tool_execution(self, tool_name: str, arguments: Dict[str, Any]):
        """Mock tool execution for development."""
        # Simulate some work
        await asyncio.sleep(0.1)
        logger.debug(f"Mock execution of tool: {tool_name}")
    
    async def list_tools(self, server_name: str) -> list:
        """
        List available tools on an MCP server.
        
        Args:
            server_name: Server name
        
        Returns:
            List of tool definitions
            
        Raises:
            ValueError: If server not found
        """
        if server_name not in self.servers:
            raise ValueError(f"MCP server '{server_name}' not connected")
        
        # Note: Actual implementation would use:
        # session = self.servers[server_name]
        # tools = await session.list_tools()
        # return tools.tools
        
        logger.debug(f"Listing tools for MCP server: {server_name}")
        return []
    
    async def cleanup(self):
        """
        Close all MCP connections.
        
        Should be called during application shutdown.
        """
        logger.info("Closing MCP connections...")
        
        for server_name in list(self.servers.keys()):
            try:
                # Note: Actual implementation would close session
                # await session.close()
                del self.servers[server_name]
                logger.debug(f"Closed MCP connection: {server_name}")
            
            except Exception as e:
                logger.error(f"Error closing MCP server {server_name}: {e}")
        
        logger.info("MCP cleanup complete")
    
    def is_connected(self, server_name: str) -> bool:
        """
        Check if MCP server is connected.
        
        Args:
            server_name: Server name
        
        Returns:
            True if connected, False otherwise
        """
        return server_name in self.servers and self.servers[server_name].get("connected", False)
    
    def get_connected_servers(self) -> list:
        """
        Get list of connected MCP server names.
        
        Returns:
            List of server names
        """
        return list(self.servers.keys())
