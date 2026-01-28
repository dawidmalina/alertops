"""
Logger plugin - logs alerts to stdout.

This is a simple reference implementation that demonstrates
how to create a plugin for the alert receiver.
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
        include_labels: bool (default: true)
        include_annotations: bool (default: true)
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
        separator = "=" * 80
        logger.info(f"\n{separator}")
        logger.info(f"🚨 ALERTMANAGER WEBHOOK - {payload.status.upper()}")
        logger.info(f"{separator}")
        logger.info(f"Timestamp: {datetime.utcnow().isoformat()}")
        logger.info(f"Receiver: {payload.receiver}")
        logger.info(f"Group Key: {payload.groupKey}")
        logger.info(f"Alerts Count: {len(payload.alerts)}")
        logger.info(f"External URL: {payload.externalURL}")
        
        if payload.commonLabels:
            logger.info(f"\nCommon Labels:")
            for key, value in payload.commonLabels.items():
                logger.info(f"  {key}: {value}")
        
        if payload.commonAnnotations:
            logger.info(f"\nCommon Annotations:")
            for key, value in payload.commonAnnotations.items():
                logger.info(f"  {key}: {value}")
        
        logger.info(f"\n{separator}")
        logger.info(f"ALERTS ({len(payload.alerts)}):")
        logger.info(f"{separator}")
        
        for i, alert in enumerate(payload.alerts, 1):
            logger.info(f"\nAlert #{i}")
            logger.info(f"  Status: {alert.status}")
            logger.info(f"  Fingerprint: {alert.fingerprint}")
            logger.info(f"  Starts At: {alert.startsAt.isoformat()}")
            
            if alert.endsAt:
                logger.info(f"  Ends At: {alert.endsAt.isoformat()}")
            
            logger.info(f"  Generator: {alert.generatorURL}")
            
            if self.include_labels and alert.labels:
                logger.info(f"  Labels:")
                for key, value in alert.labels.items():
                    logger.info(f"    {key}: {value}")
            
            if self.include_annotations and alert.annotations:
                logger.info(f"  Annotations:")
                for key, value in alert.annotations.items():
                    logger.info(f"    {key}: {value}")
        
        logger.info(f"{separator}\n")
    
    def validate_config(self) -> bool:
        """Validate logger plugin configuration."""
        if self.format not in ["json", "text"]:
            logger.error(f"Invalid format '{self.format}'. Must be 'json' or 'text'")
            return False
        return True
