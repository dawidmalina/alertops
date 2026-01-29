"""
Dump plugin - outputs raw payload to stdout.

Simple plugin that dumps the complete raw JSON payload to stdout.
Useful for debugging and capturing test data for plugin development.
"""

import json
import sys
from typing import Dict, Any
from app.plugins.base import BasePlugin
from app.models import WebhookPayload


class DumpPlugin(BasePlugin):
    """
    Plugin that dumps the complete raw payload to stdout in JSON format.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(name="dump", config=config)
    
    async def handle(self, payload: WebhookPayload) -> Dict[str, Any]:
        """
        Dump the complete payload to stdout in JSON format.
        
        Args:
            payload: Alertmanager webhook payload
            
        Returns:
            Processing result
        """
        # Convert the Pydantic model to dict and output as JSON
        payload_dict = payload.model_dump(mode='json')
        json_output = json.dumps(payload_dict, indent=2, ensure_ascii=False)
        
        # Print to stdout
        print(json_output, file=sys.stdout)
        sys.stdout.flush()
        
        return {
            "status": "ok",
            "plugin": self.name,
            "message": "Payload dumped to stdout",
            "alerts_processed": len(payload.alerts)
        }

