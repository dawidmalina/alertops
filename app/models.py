"""
Pydantic models for Prometheus Alertmanager webhook payload.

Based on Alertmanager webhook specification v4.
https://prometheus.io/docs/alerting/latest/configuration/#webhook_config
"""

from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class Alert(BaseModel):
    """Individual alert in the webhook payload."""
    
    status: str = Field(..., description="Alert status: 'firing' or 'resolved'")
    labels: Dict[str, str] = Field(default_factory=dict, description="Alert labels")
    annotations: Dict[str, str] = Field(default_factory=dict, description="Alert annotations")
    startsAt: datetime = Field(..., description="Alert start time")
    endsAt: Optional[datetime] = Field(None, description="Alert end time (for resolved alerts)")
    generatorURL: str = Field(..., description="URL to the Prometheus expression browser")
    fingerprint: str = Field(..., description="Unique alert fingerprint for deduplication")


class WebhookPayload(BaseModel):
    """Complete Alertmanager webhook payload."""
    
    version: str = Field(..., description="Webhook payload version (currently '4')")
    groupKey: str = Field(..., description="Group key for alert grouping")
    truncatedAlerts: int = Field(default=0, description="Number of truncated alerts")
    status: str = Field(..., description="Group status: 'firing' or 'resolved'")
    receiver: str = Field(..., description="Name of the receiver")
    groupLabels: Dict[str, str] = Field(default_factory=dict, description="Labels common to the group")
    commonLabels: Dict[str, str] = Field(default_factory=dict, description="Labels common to all alerts")
    commonAnnotations: Dict[str, str] = Field(default_factory=dict, description="Annotations common to all alerts")
    externalURL: str = Field(..., description="External URL of the Alertmanager")
    alerts: List[Alert] = Field(..., description="List of alerts in this notification")

    class Config:
        json_schema_extra = {
            "example": {
                "version": "4",
                "groupKey": "{}:{alertname=\"InstanceDown\"}",
                "truncatedAlerts": 0,
                "status": "firing",
                "receiver": "webhook-receiver",
                "groupLabels": {"alertname": "InstanceDown"},
                "commonLabels": {
                    "alertname": "InstanceDown",
                    "instance": "server1:9090",
                    "job": "prometheus",
                    "severity": "critical"
                },
                "commonAnnotations": {
                    "description": "server1:9090 has been down for more than 5 minutes.",
                    "summary": "Instance server1:9090 down"
                },
                "externalURL": "http://alertmanager:9093",
                "alerts": [
                    {
                        "status": "firing",
                        "labels": {
                            "alertname": "InstanceDown",
                            "instance": "server1:9090",
                            "job": "prometheus",
                            "severity": "critical"
                        },
                        "annotations": {
                            "description": "server1:9090 has been down for more than 5 minutes.",
                            "summary": "Instance server1:9090 down"
                        },
                        "startsAt": "2026-01-28T10:00:00.000Z",
                        "endsAt": "0001-01-01T00:00:00Z",
                        "generatorURL": "http://prometheus:9090/graph",
                        "fingerprint": "abc123def456"
                    }
                ]
            }
        }


class PluginResponse(BaseModel):
    """Standard response from plugin endpoints."""
    
    status: str = Field(default="ok", description="Processing status")
    plugin: str = Field(..., description="Plugin name")
    message: Optional[str] = Field(None, description="Optional message")
    alerts_processed: int = Field(..., description="Number of alerts processed")
