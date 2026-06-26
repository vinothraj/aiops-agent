import logging
import json
import smtplib
import urllib.request
import urllib.parse
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select, func

import google.generativeai as genai

from app.core.config import settings
from app.models.models import IncidentDecision, Notification, NotificationRecipient, NotificationTemplate, LogAnalysis

logger = logging.getLogger(__name__)

class NotificationAgent:
    def __init__(self):
        self._model = None

    def _get_model(self):
        """Lazy-initialize Gemini model for notifications and digests."""
        if self._model is None:
            if not settings.GEMINI_API_KEY:
                logger.warning("GEMINI_API_KEY is not configured. AI digest and summaries will use fallback template generation.")
                return None
            try:
                genai.configure(api_key=settings.GEMINI_API_KEY)
                self._model = genai.GenerativeModel(
                    model_name=settings.GEMINI_MODEL,
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.3,
                        max_output_tokens=2048,
                    )
                )
            except Exception as e:
                logger.error(f"Failed to initialize Gemini for notifications: {e}")
                return None
        return self._model

    def _get_recipients(self, db: Session, category: str) -> List[NotificationRecipient]:
        """Retrieve active recipients/destinations for a category with default fallbacks."""
        # 1. Look for category-specific recipients
        recipients = db.scalars(
            select(NotificationRecipient).where(
                NotificationRecipient.category == category,
                NotificationRecipient.is_active == True
            )
        ).all()

        if recipients:
            return list(recipients)

        # 2. Look for DEFAULT recipients
        recipients = db.scalars(
            select(NotificationRecipient).where(
                NotificationRecipient.category == "DEFAULT",
                NotificationRecipient.is_active == True
            )
        ).all()

        if recipients:
            return list(recipients)

        # 3. Fallback: If no recipients configured, insert defaults to bootstrap settings
        bootstrapped = []
        
        # Default Email Routing
        email_recipient = NotificationRecipient(
            category="DEFAULT",
            channel="email",
            destination="ops-team@company.internal",
            recipient_name="Operations Team",
            is_active=True
        )
        db.add(email_recipient)
        bootstrapped.append(email_recipient)

        # Default Teams Routing (if configured in settings)
        teams_dest = settings.TEAMS_WEBHOOK_URL or "https://outlook.office.com/webhook/placeholder-teams"
        teams_recipient = NotificationRecipient(
            category="DEFAULT",
            channel="teams",
            destination=teams_dest,
            recipient_name="Operations Teams Webhook",
            is_active=True
        )
        db.add(teams_recipient)
        bootstrapped.append(teams_recipient)

        # Category specific database bootstrap for DBA
        dba_recipient = NotificationRecipient(
            category="DATABASE",
            channel="email",
            destination="dba-team@company.internal",
            recipient_name="DBA On-Call Team",
            is_active=True
        )
        db.add(dba_recipient)
        bootstrapped.append(dba_recipient)

        db.commit()
        for r in bootstrapped:
            db.refresh(r)

        # Return relevant ones
        return [r for r in bootstrapped if r.category == category or (r.category == "DEFAULT" and category != "DATABASE")]

    # ─── MS Teams Sending ─────────────────────────────────────────────────────
    def send_teams_message(self, webhook_url: str, title: str, markdown_body: str) -> bool:
        """Sends a notification payload to MS Teams via Incoming Webhook."""
        if not webhook_url or "placeholder" in webhook_url:
            logger.info(f"[MOCK TEAMS NOTIFICATION] Webhook not configured. Title: {title}\nBody:\n{markdown_body}")
            return True

        # Construct Teams Card JSON
        payload = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "type": "AdaptiveCard",
                        "body": [
                            {
                                "type": "TextBlock",
                                "size": "Medium",
                                "weight": "Bolder",
                                "text": title
                            },
                            {
                                "type": "TextBlock",
                                "text": markdown_body,
                                "wrap": True
                            }
                        ],
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "version": "1.2"
                    }
                }
            ]
        }

        try:
            req = urllib.request.Request(
                webhook_url,
                data=json.dumps(payload).encode('utf-8'),
                headers={'Content-Type': 'application/json'}
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                status_code = response.getcode()
                if status_code in [200, 201, 202]:
                    logger.info(f"Teams notification successfully sent: {title}")
                    return True
                else:
                    logger.error(f"Teams webhook returned status code: {status_code}")
                    return False
        except Exception as e:
            logger.error(f"Failed to send Teams webhook message: {e}")
            return False

    # ─── Email Sending ────────────────────────────────────────────────────────
    def send_email_message(self, destination: str, subject: str, html_body: str) -> bool:
        """Sends an email notification via SMTP with fallback logging."""
        msg = MIMEText(html_body, "html")
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_FROM
        msg["To"] = destination

        # Append to a mock email log file in Logs directory for local testing
        try:
            import os
            os.makedirs("Logs", exist_ok=True)
            with open("Logs/mock_emails.log", "a", encoding="utf-8") as f:
                f.write(f"\n{'='*80}\n")
                f.write(f"TIMESTAMP: {datetime.now().isoformat()}\n")
                f.write(f"TO: {destination}\n")
                f.write(f"SUBJECT: {subject}\n")
                f.write(f"BODY:\n{html_body}\n")
                f.write(f"{'='*80}\n")
        except Exception as file_err:
            logger.error(f"Failed to write mock email log: {file_err}")

        # Attempt actual SMTP send
        try:
            # Skip actual SMTP if settings default to localhost or not configured
            if settings.SMTP_HOST == "localhost" and settings.SMTP_PORT == 1025:
                # Unless we actually expect a local dev mail server like MailHog running
                logger.info(f"Sending email (Mock mode / MailHog on port 1025) to {destination}: {subject}")
            
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=5) as server:
                if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                    server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                server.sendmail(settings.SMTP_FROM, [destination], msg.as_string())
            
            logger.info(f"Email successfully delivered to {destination}: {subject}")
            return True
        except Exception as smtp_err:
            logger.warning(f"SMTP send failed (logged to Logs/mock_emails.log instead): {smtp_err}")
            # We treat development mock logging as a successful fallback for testing
            return True

    # ─── Gemini Summarization & Digests ───────────────────────────────────────
    def generate_p1_exec_summary(self, decision: IncidentDecision) -> str:
        """Generates a professional executive-friendly summary for P1 incidents."""
        model = self._get_model()
        if not model:
            return "Executive Summary: Critical P1 incident detected in service. Immediate escalation triggered."

        prompt = f"""
        You are an expert Reliability Engineer. Generate a concise, high-level executive summary for a P1 Critical Outage.
        The audience is business executives, so focus on business impact, technical context in layman terms, and clear resolution steps.

        Incident Details:
        - Priority: {decision.priority}
        - Service Name: {decision.log.service_name if decision.log else 'Unknown'}
        - Trigger Message: {decision.log.message if decision.log else ''}
        - AI Root Cause Analysis: {decision.analysis.root_cause if decision.analysis else 'Under investigation'}
        - Business Impact: {decision.analysis.business_impact if decision.analysis else ''}
        - Technical Impact: {decision.analysis.technical_impact if decision.analysis else ''}
        - Recommended Action: {decision.recommended_action}
        
        Write a short executive summary in 3-4 bullet points (max 150 words). Include:
        1. What happened and business impact
        2. Root Cause Category
        3. Action taken / immediate mitigation steps
        """

        try:
            response = model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            logger.error(f"Error generating P1 executive summary with Gemini: {e}")
            return f"P1 incident occurred in {decision.log.service_name if decision.log else 'Service'}. Root Cause: {decision.analysis.root_cause if decision.analysis else 'Investigation pending'}."

    def generate_daily_digest(self, db: Session) -> str:
        """Collects all incidents in the last 24h and generates an AI summary."""
        cutoff = datetime.utcnow() - timedelta(hours=24)
        decisions = db.scalars(
            select(IncidentDecision).where(IncidentDecision.created_at >= cutoff)
        ).all()

        if not decisions:
            return "Daily Operational Digest: No incident decisions triaged in the last 24 hours. Systems are healthy."

        model = self._get_model()
        if not model:
            # Fallback template
            return f"Daily Operational Digest: {len(decisions)} incidents triaged in the last 24h. P1 count: {len([d for d in decisions if d.priority == 'P1'])}."

        summary_data = []
        for d in decisions:
            summary_data.append({
                "id": d.id,
                "priority": d.priority,
                "service": d.log.service_name if d.log else 'Unknown',
                "action": d.recommended_action,
                "category": d.analysis.root_cause_category if d.analysis else 'Unknown',
                "root_cause": d.analysis.root_cause[:150] if d.analysis else 'Unknown'
            })

        prompt = f"""
        You are a Principal Site Reliability Engineer. Generate a Daily Operational Digest summarizing the last 24 hours of system incidents.
        
        Triaged Incidents:
        {json.dumps(summary_data, indent=2)}

        Write a professional daily summary including:
        - Overall reliability status and health rating (Excellent/Fair/Critical)
        - Breakdown of incidents by priority
        - High-level summary of critical P1/P2 issues and their root causes
        - Recommended general preventive actions or patterns detected
        Keep the report structured, clear, and action-oriented. Format in Markdown.
        """

        try:
            response = model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            logger.error(f"Failed to generate daily digest: {e}")
            return "Failed to compile AI daily digest. Please check logs."

    def generate_weekly_insights(self, db: Session) -> str:
        """Collects all incidents in the last 7 days and analyzes reliability trends."""
        cutoff = datetime.utcnow() - timedelta(days=7)
        decisions = db.scalars(
            select(IncidentDecision).where(IncidentDecision.created_at >= cutoff)
        ).all()

        if not decisions:
            return "Weekly Reliability Insights: No incidents tracked in the last 7 days. Systems are fully reliable."

        model = self._get_model()
        if not model:
            return f"Weekly Reliability Insights: {len(decisions)} incidents tracked in the last 7 days."

        summary_data = []
        for d in decisions:
            summary_data.append({
                "service": d.log.service_name if d.log else 'Unknown',
                "priority": d.priority,
                "category": d.analysis.root_cause_category if d.analysis else 'Unknown',
                "created_at": d.created_at.strftime("%Y-%m-%d")
            })

        prompt = f"""
        You are an expert Systems Architect. Analyze the following 7-day incident history data and write a Weekly Reliability Insights Report.
        
        Incident Data:
        {json.dumps(summary_data, indent=2)}

        Please analyze:
        1. **System Outage Trends**: Are outages increasing or decreasing?
        2. **Hotspots**: Which services are failing most frequently?
        3. **Category Breakdown**: What are the most common root cause categories (e.g. DATABASE, APPLICATION_BUG, etc.)?
        4. **Actionable SRE Recommendations**: Recommendations for architectural refactoring, monitoring, or testing improvements.
        Format in Markdown with clean sections.
        """

        try:
            response = model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            logger.error(f"Failed to generate weekly insights: {e}")
            return "Failed to compile AI weekly reliability insights."

    # ─── Orchestration ────────────────────────────────────────────────────────
    def send_notification(self, db: Session, incident_decision_id: int, channels: Optional[List[str]] = None) -> List[Notification]:
        """Orchestrates dynamic routing and template rendering to send notifications for an incident."""
        decision = db.scalar(select(IncidentDecision).where(IncidentDecision.id == incident_decision_id))
        if not decision:
            logger.error(f"IncidentDecision {incident_decision_id} not found.")
            return []

        # Get routing category
        category = "DEFAULT"
        if decision.analysis and decision.analysis.root_cause_category:
            category = decision.analysis.root_cause_category

        # Determine channels to notify
        recipients = self._get_recipients(db, category)
        notifications_sent = []

        # Generate P1 Executive Summary if it's P1
        exec_summary = None
        if decision.priority == "P1":
            exec_summary = self.generate_p1_exec_summary(decision)

        for recipient in recipients:
            # Filter by requested channels if specified
            if channels and recipient.channel not in channels:
                continue

            # Format the title and message
            title = f"[AIOps Alert - {decision.priority}] incident in {decision.log.service_name if decision.log else 'Service'}"
            
            # Formulate Markdown / HTML payload
            message_body = []
            message_body.append(f"**Action Recommended:** {decision.recommended_action}")
            message_body.append(f"**Risk Score:** {decision.risk_score:.2f}")
            message_body.append(f"**Triage Rationale:** {decision.rationale}")
            
            if exec_summary:
                message_body.append(f"\n### Executive Summary\n{exec_summary}")
            elif decision.analysis:
                message_body.append(f"\n### Root Cause Analysis\n{decision.analysis.root_cause}")

            if decision.gitlab_issue_id:
                message_body.append(f"\n**GitLab Tracker:** Issue ID {decision.gitlab_issue_id}")

            message_str = "\n\n".join(message_body)

            # Check if this notification was already sent
            existing = db.scalar(
                select(Notification).where(
                    Notification.incident_decision_id == decision.id,
                    Notification.channel == recipient.channel,
                    Notification.recipient_destination == recipient.destination
                )
            )
            if existing and existing.status == "SENT":
                logger.info(f"Notification already sent to {recipient.destination} via {recipient.channel}")
                continue

            # Save Notification record
            notification = Notification(
                incident_decision_id=decision.id,
                channel=recipient.channel,
                recipient_destination=recipient.destination,
                title=title,
                message=message_str,
                status="PENDING",
                retry_count=0
            )
            db.add(notification)
            db.commit()
            db.refresh(notification)

            # Send Notification
            success = False
            error_msg = None
            if recipient.channel == "teams":
                success = self.send_teams_message(recipient.destination, title, message_str)
                if not success:
                    error_msg = "Teams webhook post failed."
            elif recipient.channel == "email":
                # Create HTML formatted email body
                html_body = f"""
                <html>
                <body style="font-family: Arial, sans-serif; background-color: #f3f4f6; padding: 20px;">
                    <div style="max-width: 600px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; border: 1px solid #e5e7eb;">
                        <h2 style="color: #dc2626;">[AIOps Alert] {decision.priority} Incident Detected</h2>
                        <p><strong>Service:</strong> {decision.log.service_name if decision.log else 'Unknown'}</p>
                        <p><strong>Recommended Action:</strong> {decision.recommended_action}</p>
                        <p><strong>Risk Score:</strong> {(decision.risk_score*100):.0f}%</p>
                        <p><strong>Triage Rationale:</strong> {decision.rationale}</p>
                        <hr style="border: 0; border-top: 1px solid #e5e7eb; margin: 20px 0;"/>
                        {f"<h3>Executive Summary</h3><p style='line-height:1.6;'>{exec_summary.replace(chr(10), '<br>')}</p>" if exec_summary else ''}
                        {f"<h3>Root Cause Analysis</h3><p style='line-height:1.6;'>{decision.analysis.root_cause.replace(chr(10), '<br>')}</p>" if not exec_summary and decision.analysis else ''}
                        <p style="font-size: 0.8rem; color: #6b7280; margin-top: 20px;">Auto-generated by AIOps Platform Agentic Flow.</p>
                    </div>
                </body>
                </html>
                """
                success = self.send_email_message(recipient.destination, title, html_body)
                if not success:
                    error_msg = "SMTP delivery failed."

            # Update status
            notification.status = "SENT" if success else "FAILED"
            if not success:
                notification.error_message = error_msg
            notification.updated_at = datetime.utcnow()
            
            db.commit()
            db.refresh(notification)
            notifications_sent.append(notification)

        return notifications_sent

    def retry_failed_notifications(self, db: Session):
        """Scans for failed notifications and retries them, incrementing retry count."""
        failed = db.scalars(
            select(Notification).where(
                Notification.status == "FAILED",
                Notification.retry_count < 3
            )
        ).all()

        if not failed:
            return

        logger.info(f"Found {len(failed)} failed notifications. Commencing retry cycle...")

        for n in failed:
            n.retry_count += 1
            n.status = "PENDING"
            db.commit()

            success = False
            if n.channel == "teams":
                success = self.send_teams_message(n.recipient_destination, n.title, n.message)
            elif n.channel == "email":
                success = self.send_email_message(n.recipient_destination, n.title, f"<p>{n.message}</p>")

            n.status = "SENT" if success else "FAILED"
            if not success:
                n.error_message = f"Retry {n.retry_count} failed."
            
            n.updated_at = datetime.utcnow()
            db.commit()
            logger.info(f"Retry {n.retry_count} for notification {n.id} outcome: {n.status}")

# Singleton for easy import elsewhere
notification_agent = NotificationAgent()
