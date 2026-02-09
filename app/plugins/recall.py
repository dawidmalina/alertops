"""
Recall plugin - stores and retrieves alert history.

This plugin stores incoming alerts and provides query endpoints
to retrieve past alerts by fingerprint, status, labels, or time range.
"""

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from fastapi import Query
from app.plugins.base import BasePlugin
from app.models import WebhookPayload, Alert

logger = logging.getLogger(__name__)


class RecallPlugin(BasePlugin):
    """
    Plugin that stores alerts and provides endpoints to query alert history.
    
    Features:
    - POST /alert/recall - Receives and stores alerts
    - GET /alert/recall - Query all stored alerts
    - GET /alert/recall/{fingerprint} - Get specific alert by fingerprint
    
    Storage is in-memory by default. Alerts are stored with their full payload.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(name="recall", config=config)
        # In-memory storage: Dict[fingerprint, List[Alert]]
        # We store a list for each fingerprint to track alert history
        self.alerts_store: Dict[str, List[Dict[str, Any]]] = {}
        # Track total number of alerts received
        self.total_alerts_received = 0
        self._setup_query_routes()
    
    def _setup_query_routes(self):
        """Set up additional GET routes for querying alerts."""
        
        # Note: More specific routes must come before parameterized routes
        @self.router.get(f"/{self.name}/stats")
        async def get_stats():
            """
            Get statistics about stored alerts.
            """
            return self._get_stats()
        
        @self.router.get(f"/{self.name}")
        async def query_alerts(
            status: Optional[str] = Query(None, description="Filter by status: firing or resolved"),
            alertname: Optional[str] = Query(None, description="Filter by alertname label"),
            limit: int = Query(100, description="Maximum number of alerts to return", ge=1, le=1000)
        ):
            """
            Query stored alerts with optional filters.
            
            Returns a list of alerts matching the filter criteria.
            """
            return self._query_alerts(status=status, alertname=alertname, limit=limit)
        
        @self.router.get(f"/{self.name}/{{fingerprint}}")
        async def get_alert_by_fingerprint(fingerprint: str):
            """
            Get alert history for a specific fingerprint.
            
            Returns all stored instances of alerts with the given fingerprint.
            """
            return self._get_by_fingerprint(fingerprint)
    
    async def handle(self, payload: WebhookPayload) -> Dict[str, Any]:
        """
        Store the incoming alerts.
        
        Args:
            payload: Alertmanager webhook payload
            
        Returns:
            Processing result
        """
        alerts_stored = 0
        
        for alert in payload.alerts:
            self._store_alert(alert, payload)
            alerts_stored += 1
        
        self.total_alerts_received += alerts_stored
        
        logger.info(f"Stored {alerts_stored} alert(s). Total alerts in store: {self.total_alerts_received}")
        
        return {
            "status": "ok",
            "plugin": self.name,
            "message": f"Stored {alerts_stored} alert(s)",
            "alerts_processed": alerts_stored
        }
    
    def _store_alert(self, alert: Alert, payload: WebhookPayload):
        """
        Store an alert with metadata.
        
        Args:
            alert: Individual alert to store
            payload: Parent webhook payload for additional context
        """
        # Create storage entry with alert data and metadata
        alert_entry = {
            "alert": alert.model_dump(mode='json'),
            "received_at": datetime.utcnow().isoformat() + "Z",
            "receiver": payload.receiver,
            "external_url": payload.externalURL,
            "group_key": payload.groupKey
        }
        
        # Store by fingerprint
        fingerprint = alert.fingerprint
        if fingerprint not in self.alerts_store:
            self.alerts_store[fingerprint] = []
        
        self.alerts_store[fingerprint].append(alert_entry)
    
    def _query_alerts(
        self, 
        status: Optional[str] = None,
        alertname: Optional[str] = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        Query stored alerts with filters.
        
        Args:
            status: Filter by alert status
            alertname: Filter by alertname label
            limit: Maximum number of results
            
        Returns:
            Dict with query results
        """
        results = []
        
        # Iterate through all fingerprints and their alert history
        for fingerprint, alert_history in self.alerts_store.items():
            for entry in alert_history:
                alert_data = entry["alert"]
                
                # Apply filters
                if status and alert_data.get("status") != status:
                    continue
                
                if alertname and alert_data.get("labels", {}).get("alertname") != alertname:
                    continue
                
                # Add to results
                results.append({
                    "fingerprint": fingerprint,
                    "alert": alert_data,
                    "received_at": entry["received_at"],
                    "receiver": entry["receiver"]
                })
                
                # Check limit
                if len(results) >= limit:
                    break
            
            if len(results) >= limit:
                break
        
        # Sort by received_at (most recent first)
        results.sort(key=lambda x: x["received_at"], reverse=True)
        
        return {
            "status": "ok",
            "plugin": self.name,
            "count": len(results),
            "alerts": results[:limit]
        }
    
    def _get_by_fingerprint(self, fingerprint: str) -> Dict[str, Any]:
        """
        Get all alerts for a specific fingerprint.
        
        Args:
            fingerprint: Alert fingerprint
            
        Returns:
            Dict with alert history for the fingerprint
        """
        if fingerprint not in self.alerts_store:
            return {
                "status": "not_found",
                "plugin": self.name,
                "message": f"No alerts found for fingerprint: {fingerprint}",
                "fingerprint": fingerprint,
                "count": 0,
                "history": []
            }
        
        history = self.alerts_store[fingerprint]
        
        return {
            "status": "ok",
            "plugin": self.name,
            "fingerprint": fingerprint,
            "count": len(history),
            "history": history
        }
    
    def _get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about stored alerts.
        
        Returns:
            Dict with statistics
        """
        unique_fingerprints = len(self.alerts_store)
        total_stored = sum(len(history) for history in self.alerts_store.values())
        
        # Count by status
        firing_count = 0
        resolved_count = 0
        
        for alert_history in self.alerts_store.values():
            for entry in alert_history:
                status = entry["alert"].get("status")
                if status == "firing":
                    firing_count += 1
                elif status == "resolved":
                    resolved_count += 1
        
        return {
            "status": "ok",
            "plugin": self.name,
            "statistics": {
                "unique_fingerprints": unique_fingerprints,
                "total_alerts_stored": total_stored,
                "firing_alerts": firing_count,
                "resolved_alerts": resolved_count
            }
        }
    
    def validate_config(self) -> bool:
        """Validate recall plugin configuration."""
        # No specific configuration required for basic functionality
        return True
