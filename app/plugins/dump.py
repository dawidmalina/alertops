"""
Dump plugin - outputs raw payload to stdout.

This plugin is designed for debugging and development purposes.
It outputs the complete raw JSON payload received from Alertmanager,
which can be used as test input for developing or fine-tuning other plugins.

Usage:
1. Temporarily configure an alert to use this plugin endpoint
2. Trigger the alert to see the raw payload
3. Use the captured payload for plugin development/testing
"""

import json
import logging
import sys
from typing import Dict, Any
from app.plugins.base import BasePlugin
from app.models import WebhookPayload

logger = logging.getLogger(__name__)


class DumpPlugin(BasePlugin):
    """
    Plugin that dumps the complete raw payload to stdout in JSON format.
    
    This is useful for:
    - Debugging incoming alerts
    - Capturing test payloads for plugin development
    - Understanding the structure of Alertmanager webhooks
    
    Configuration options (from config.yaml):
        indent: int (default: 2) - JSON indentation for pretty printing
        ensure_ascii: bool (default: False) - Whether to escape non-ASCII characters
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(name="dump", config=config)
        self.indent = self.config.get("indent", 2)
        self.ensure_ascii = self.config.get("ensure_ascii", False)
    
    async def handle(self, payload: WebhookPayload) -> Dict[str, Any]:
        """
        Dump the complete payload to stdout in JSON format.
        
        Args:
            payload: Alertmanager webhook payload
            
        Returns:
            Processing result
        """
        # Convert the Pydantic model to dict
        payload_dict = payload.model_dump(mode='json')
        
        # Output the complete raw payload to stdout
        json_output = json.dumps(
            payload_dict,
            indent=self.indent,
            ensure_ascii=self.ensure_ascii
        )
        
        # Print to stdout (not using logger to avoid timestamp/level prefixes)
        print("\n" + "=" * 80, file=sys.stdout)
        print("RAW PAYLOAD DUMP", file=sys.stdout)
        print("=" * 80, file=sys.stdout)
        print(json_output, file=sys.stdout)
        print("=" * 80 + "\n", file=sys.stdout)
        sys.stdout.flush()
        
        return {
            "status": "ok",
            "plugin": self.name,
            "message": "Payload dumped to stdout",
            "alerts_processed": len(payload.alerts)
        }
    
    def validate_config(self) -> bool:
        """Validate dump plugin configuration."""
        if not isinstance(self.indent, int) or self.indent < 0:
            logger.error(f"Invalid indent value '{self.indent}'. Must be a non-negative integer")
            return False
        if not isinstance(self.ensure_ascii, bool):
            logger.error(f"Invalid ensure_ascii value '{self.ensure_ascii}'. Must be a boolean")
            return False
        return True
