"""
Logger plugin - logs alerts to stdout in text format.

This is a simple reference implementation that demonstrates
how to create a plugin for the alert receiver.

The output provides a clean, markdown-style format similar to
Grafana's Alertmanager notification format, showing alert title,
description, and details with all labels.

For JSON output, use the dump plugin instead.
"""

import logging
from typing import Dict, Any
from app.plugins.base import BasePlugin
from app.models import WebhookPayload

logger = logging.getLogger(__name__)


class LoggerPlugin(BasePlugin):
    """
    Plugin that logs incoming alerts to stdout in a human-readable text format.
    
    Outputs alerts in a clean markdown-style format showing:
    - Alert title with severity badge
    - Description
    - Details section with all labels
    
    For JSON output, use the dump plugin instead.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(name="logger", config=config)
    
    async def handle(self, payload: WebhookPayload) -> Dict[str, Any]:
        """
        Process and log the alert payload in text format.
        
        Args:
            payload: Alertmanager webhook payload
            
        Returns:
            Processing result
        """
        self._log_text(payload)
        
        return {
            "status": "ok",
            "plugin": self.name,
            "message": "Alerts logged successfully",
            "alerts_processed": len(payload.alerts)
        }
    
    def _log_text(self, payload: WebhookPayload):
        """Log payload in human-readable text format."""
        output_lines = []
        
        for i, alert in enumerate(payload.alerts):
            # Add separator between alerts (not before the first one)
            if i > 0:
                output_lines.append("---")
                output_lines.append("")
            
            # Alert header with title and severity
            title = alert.annotations.get("title") or alert.annotations.get("summary") or alert.labels.get("alertname", "Alert")
            severity = alert.labels.get("severity", "")
            
            if severity:
                output_lines.append(f"*Alert:* {title} - `{severity}`")
            else:
                output_lines.append(f"*Alert:* {title}")
            
            output_lines.append("")
            
            # Description
            description = alert.annotations.get("description", "No description provided")
            output_lines.append(f"*Description:* {description}")
            output_lines.append("")
            
            # Details section with all labels
            if alert.labels:
                output_lines.append("*Details:*")
                # Sort labels for consistent output
                sorted_labels = sorted(alert.labels.items())
                for key, value in sorted_labels:
                    output_lines.append(f"  • *{key}:* `{value}`")
                output_lines.append("")
        
        # Log the formatted output
        logger.info("\n" + "\n".join(output_lines))
    
    def validate_config(self) -> bool:
        """Validate logger plugin configuration."""
        return True
