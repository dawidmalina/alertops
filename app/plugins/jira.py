"""
Jira plugin - creates Jira issues from Prometheus alerts.

Uses AI (GitHub Models) for intelligent summarization and
MCP (Model Context Protocol) for Jira operations.
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime

from app.plugins.base import BasePlugin
from app.models import WebhookPayload, Alert

logger = logging.getLogger(__name__)


class JiraPlugin(BasePlugin):
    """
    Plugin that creates Jira issues from Prometheus alerts.
    
    Features:
    - AI-powered alert summarization using GitHub Models
    - Jira operations through MCP server
    - Deduplication by alert fingerprint
    - Severity to priority mapping
    
    Configuration (config.yaml):
        jira:
          project_key: "OPS"
          issue_type: "Incident"
          deduplicate: true
          deduplicate_window_hours: 24
          severity_priority_map:
            critical: "Highest"
            warning: "High"
            info: "Medium"
          ai:
            system_prompt: "Custom system prompt..."
            temperature: 0.2
            max_tokens: 200
    """
    
    # Default system prompt for AI summarization
    DEFAULT_SYSTEM_PROMPT = """You are an expert SRE assistant creating Jira tickets from Prometheus alerts.

Your task is to create a clear, concise summary suitable for a Jira ticket.

Focus on:
- Alert severity and impact
- Affected service/instance
- Root cause if identifiable
- Recommended immediate actions

Format:
- First line: Brief summary (max 100 characters) for ticket title
- Following lines: Detailed description with context

Use plain text, no markdown formatting."""
    
    def __init__(
        self,
        config: Dict[str, Any],
        ai_provider: Optional[Any] = None,
        mcp_manager: Optional[Any] = None
    ):
        super().__init__(name="jira", config=config, ai_provider=ai_provider, mcp_manager=mcp_manager)
        
        # Jira configuration
        self.project_key = config.get("project_key", "OPS")
        self.issue_type = config.get("issue_type", "Incident")
        
        # Deduplication settings
        self.deduplicate = config.get("deduplicate", True)
        self.dedup_window = config.get("deduplicate_window_hours", 24)
        
        # Severity to priority mapping
        self.severity_map = config.get("severity_priority_map", {
            "critical": "Highest",
            "high": "High",
            "warning": "High",
            "info": "Medium",
            "low": "Low"
        })
        
        # AI configuration (plugin-specific overrides)
        self.ai_config = config.get("ai", {})
        self.system_prompt = self.ai_config.get(
            "system_prompt",
            self.DEFAULT_SYSTEM_PROMPT
        )
        
        logger.info(
            f"Initialized Jira plugin: project={self.project_key}, "
            f"type={self.issue_type}, dedup={self.deduplicate}"
        )
    
    def validate_config(self) -> bool:
        """Validate Jira plugin configuration."""
        if not self.project_key:
            logger.error("Jira plugin: project_key is required")
            return False
        
        if not self.mcp:
            logger.error("Jira plugin: MCP manager is required")
            return False
        
        return True
    
    async def handle(self, payload: WebhookPayload) -> Dict[str, Any]:
        """
        Process alerts and create Jira issues.
        
        Args:
            payload: Alertmanager webhook payload
        
        Returns:
            Processing results with created issue keys
        """
        created_issues = []
        skipped_duplicates = 0
        errors = 0
        
        for alert in payload.alerts:
            try:
                # Check for duplicates
                if self.deduplicate and await self._is_duplicate(alert):
                    logger.info(f"Skipping duplicate alert: {alert.fingerprint}")
                    skipped_duplicates += 1
                    continue
                
                # Generate AI summary
                summary, description = await self._generate_summary(alert)
                
                # Create Jira issue via MCP
                issue = await self._create_jira_issue(alert, summary, description)
                
                if issue:
                    issue_key = issue.get("key", "unknown")
                    created_issues.append(issue_key)
                    logger.info(f"Created Jira issue: {issue_key} for alert {alert.fingerprint}")
                else:
                    logger.warning(f"Failed to create Jira issue for alert {alert.fingerprint}")
                    errors += 1
            
            except Exception as e:
                logger.error(f"Error processing alert {alert.fingerprint}: {e}", exc_info=True)
                errors += 1
        
        return {
            "status": "ok" if errors == 0 else "partial",
            "plugin": self.name,
            "message": f"Created {len(created_issues)} issues, skipped {skipped_duplicates} duplicates, {errors} errors",
            "alerts_processed": len(created_issues),
            "issues_created": created_issues,
            "skipped": skipped_duplicates,
            "errors": errors
        }
    
    async def _is_duplicate(self, alert: Alert) -> bool:
        """
        Check if alert already has an open Jira issue.
        
        Uses MCP to search Jira with JQL query filtering by fingerprint label.
        
        Args:
            alert: Alert to check
        
        Returns:
            True if duplicate found, False otherwise
        """
        jql = (
            f'project = {self.project_key} '
            f'AND labels = "fingerprint-{alert.fingerprint}" '
            f'AND status NOT IN (Done, Resolved, Closed) '
            f'AND created >= -{self.dedup_window}h'
        )
        
        try:
            result = await self.call_mcp_tool(
                server_name="jira",
                tool_name="search_issues",
                arguments={
                    "jql": jql,
                    "max_results": 1
                }
            )
            
            if result and isinstance(result, dict):
                total = result.get("total", 0)
                return total > 0
            
            return False
        
        except Exception as e:
            logger.warning(f"Deduplication check failed: {e}")
            # On error, assume not duplicate to avoid missing alerts
            return False
    
    async def _generate_summary(self, alert: Alert) -> tuple[str, str]:
        """
        Generate AI-powered summary and description.
        
        Falls back to template-based generation if AI fails.
        
        Args:
            alert: Alert to summarize
        
        Returns:
            Tuple of (summary, description)
        """
        # Try AI generation if available
        if self.ai:
            try:
                ai_result = await self._generate_ai_summary(alert)
                if ai_result:
                    return ai_result
            except Exception as e:
                logger.warning(f"AI summarization failed, using fallback: {e}")
        
        # Fallback to template-based
        return self._generate_template_summary(alert)
    
    async def _generate_ai_summary(self, alert: Alert) -> Optional[tuple[str, str]]:
        """
        Generate AI summary using GitHub Models.
        
        Args:
            alert: Alert to summarize
        
        Returns:
            Tuple of (summary, description) or None if fails
        """
        # Build prompt from alert data
        prompt = self._build_ai_prompt(alert)
        
        # Get AI config overrides
        ai_kwargs = {
            "temperature": self.ai_config.get("temperature", 0.2),
            "max_tokens": self.ai_config.get("max_tokens", 200)
        }
        
        # Generate text
        ai_text = await self.generate_ai_text(
            prompt=prompt,
            system_prompt=self.system_prompt,
            **ai_kwargs
        )
        
        if not ai_text:
            return None
        
        # Parse AI response (first line = summary, rest = description)
        lines = ai_text.strip().split("\n", 1)
        summary = lines[0].strip()
        description = lines[1].strip() if len(lines) > 1 else ai_text
        
        # Ensure summary is not too long for Jira
        if len(summary) > 255:
            summary = summary[:252] + "..."
        
        return summary, description
    
    def _build_ai_prompt(self, alert: Alert) -> str:
        """Build AI prompt from alert data."""
        return f"""Create a Jira ticket from this Prometheus alert:

Alert Name: {alert.labels.get('alertname', 'Unknown')}
Status: {alert.status}
Severity: {alert.labels.get('severity', 'unknown')}
Instance: {alert.labels.get('instance', 'unknown')}
Job: {alert.labels.get('job', 'unknown')}

Description: {alert.annotations.get('description', 'No description')}
Summary: {alert.annotations.get('summary', 'No summary')}

Started: {alert.startsAt}
Fingerprint: {alert.fingerprint}

Provide a clear Jira ticket with:
1. First line: Concise summary (max 100 chars) for ticket title
2. Following lines: Detailed description with impact and recommended actions"""
    
    def _generate_template_summary(self, alert: Alert) -> tuple[str, str]:
        """
        Generate basic summary using template.
        
        Fallback when AI is unavailable or fails.
        
        Args:
            alert: Alert to summarize
        
        Returns:
            Tuple of (summary, description)
        """
        alertname = alert.labels.get('alertname', 'Unknown Alert')
        instance = alert.labels.get('instance', 'unknown')
        severity = alert.labels.get('severity', 'unknown')
        
        # Create summary
        summary = f"[{severity.upper()}] {alertname} on {instance}"
        
        # Create description in Jira Wiki markup
        description = f"""h2. Alert Details

*Status:* {alert.status}
*Severity:* {severity}
*Instance:* {instance}
*Job:* {alert.labels.get('job', 'unknown')}
*Started:* {alert.startsAt}

h3. Description
{alert.annotations.get('description', 'No description available')}

h3. Summary
{alert.annotations.get('summary', 'No summary available')}

h3. Technical Details
*Generator URL:* {alert.generatorURL}
*Fingerprint:* {{{{monospace}}}}{alert.fingerprint}{{{{monospace}}}}
*Labels:*
"""
        
        # Add all labels
        for key, value in alert.labels.items():
            description += f"* *{key}:* {value}\n"
        
        return summary, description
    
    async def _create_jira_issue(
        self,
        alert: Alert,
        summary: str,
        description: str
    ) -> Optional[Dict[str, Any]]:
        """
        Create Jira issue via MCP.
        
        Args:
            alert: Alert data
            summary: Issue summary
            description: Issue description
        
        Returns:
            Created issue data or None if fails
        """
        # Map severity to priority
        severity = alert.labels.get('severity', 'info')
        priority = self.severity_map.get(severity.lower(), "Medium")
        
        # Build labels
        labels = [
            "alertops",
            "prometheus",
            f"fingerprint-{alert.fingerprint}",
            f"severity-{severity}",
            alert.labels.get('alertname', '').replace(' ', '-').lower()
        ]
        # Filter empty labels
        labels = [l for l in labels if l]
        
        # Create issue via MCP
        try:
            result = await self.call_mcp_tool(
                server_name="jira",
                tool_name="create_issue",
                arguments={
                    "project": self.project_key,
                    "issuetype": self.issue_type,
                    "summary": summary,
                    "description": description,
                    "priority": priority,
                    "labels": labels
                }
            )
            
            return result
        
        except Exception as e:
            logger.error(f"Failed to create Jira issue: {e}")
            raise
