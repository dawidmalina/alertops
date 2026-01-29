"""
Logger plugin - logs alerts to stdout.

This is a simple reference implementation that demonstrates
how to create a plugin for the alert receiver.

The text format provides a clean, markdown-style output similar to
Grafana's Alertmanager notification format, showing alert title,
description, and details with all labels.
"""

import json
import logging
from typing import Dict, Any
from datetime import datetime
from app.plugins.base import BasePlugin
from app.models import WebhookPayload

logger = logging.getLogger(__name__)


class LoggerPlugin(BasePlugin):
    """
    Plugin that logs incoming alerts to stdout.
    
    Configuration options (from config.yaml):
        format: "json" or "text" (default: "json")
            - json: Structured JSON output with all fields
            - text: Clean markdown-style format showing alert title, description, 
                    and details (labels) - similar to Grafana's format
        include_labels: bool (default: true)
            - Includes labels in the output (text format shows them in Details section)
        include_annotations: bool (default: true)
            - Includes annotations in the output (used in text format)
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(name="logger", config=config)
        self.format = self.config.get("format", "json")
        self.include_labels = self.config.get("include_labels", True)
        self.include_annotations = self.config.get("include_annotations", True)
    
    async def handle(self, payload: WebhookPayload) -> Dict[str, Any]:
        """
        Process and log the alert payload.
        
        Args:
            payload: Alertmanager webhook payload
            
        Returns:
            Processing result
        """
        if self.format == "json":
            self._log_json(payload)
        else:
            self._log_text(payload)
        
        return {
            "status": "ok",
            "plugin": self.name,
            "message": "Alerts logged successfully",
            "alerts_processed": len(payload.alerts)
        }
    
    def _log_json(self, payload: WebhookPayload):
        """Log payload in JSON format."""
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "version": payload.version,
            "groupKey": payload.groupKey,
            "status": payload.status,
            "receiver": payload.receiver,
            "externalURL": payload.externalURL,
            "alerts_count": len(payload.alerts),
            "alerts": []
        }
        
        for alert in payload.alerts:
            alert_data = {
                "status": alert.status,
                "fingerprint": alert.fingerprint,
                "startsAt": alert.startsAt.isoformat(),
                "generatorURL": alert.generatorURL
            }
            
            if alert.endsAt:
                alert_data["endsAt"] = alert.endsAt.isoformat()
            
            if self.include_labels:
                alert_data["labels"] = alert.labels
            
            if self.include_annotations:
                alert_data["annotations"] = alert.annotations
            
            log_data["alerts"].append(alert_data)
        
        logger.info(json.dumps(log_data, indent=2))
    
    def _log_text(self, payload: WebhookPayload):
        """Log payload in human-readable text format."""
        output_lines = []
        
        for alert in payload.alerts:
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
            output_lines.append("*Details:*")
            
            if self.include_labels and alert.labels:
                # Sort labels for consistent output
                sorted_labels = sorted(alert.labels.items())
                for key, value in sorted_labels:
                    output_lines.append(f"  • *{key}:* `{value}`")
            
            output_lines.append("")
        
        # Log the formatted output
        logger.info("\n" + "\n".join(output_lines))
    
    def validate_config(self) -> bool:
        """Validate logger plugin configuration."""
        if self.format not in ["json", "text"]:
            logger.error(f"Invalid format '{self.format}'. Must be 'json' or 'text'")
            return False
        return True
