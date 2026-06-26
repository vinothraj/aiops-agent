import logging
from typing import Optional
from datetime import datetime, timedelta
import json

from sqlalchemy.orm import Session
from sqlalchemy import select, func

from app.models.models import IncidentDecision, Log, LogAnalysis
from app.schemas.schemas import TriageDecisionResponse

logger = logging.getLogger(__name__)

class TriageEngine:
    """Core AI-powered triage engine.

    It calculates risk/impact/frequency scores, determines priority, chooses a recommended
    action, generates a short rationale (via Gemini), and persists the decision.
    """

    def __init__(self):
        # Placeholder for possible future injection of LLM client.
        pass

    # ---------------------------------------------------------------------
    # Helper calculations
    # ---------------------------------------------------------------------
    def _calculate_frequency_score(self, db: Session, service_name: str) -> float:
        """How often similar errors have occurred in the last 24h.

        Returns a value in [0.0, 1.0] where 1.0 means "very frequent".
        """
        cutoff = datetime.utcnow() - timedelta(hours=24)
        count = db.scalar(
            select(func.count(Log.id)).where(
                Log.service_name == service_name,
                Log.timestamp >= cutoff,
                Log.log_level.in_(["ERROR", "FATAL"])
            )
        ) or 0
        # Cap at 10 occurrences for scaling
        score = min(count / 10.0, 1.0)
        logger.debug(f"Frequency count for {service_name}: {count}, score={score}")
        return score

    def _text_score(self, text: Optional[str]) -> float:
        """Simple heuristic: length of the text normalized to 0‑1.
        Empty or None => 0.0.
        """
        if not text:
            return 0.0
        # Assume 500 characters is a "high impact" length.
        return min(len(text) / 500.0, 1.0)

    def _determine_priority(self, risk_score: float, ai_severity: Optional[str] = None) -> str:
        """Determine priority, respecting AI severity if provided."""
        # AI severity from Gemini is authoritative — map it directly
        if ai_severity:
            severity_map = {"P1": "P1", "P2": "P2", "P3": "P3", "P4": "P4"}
            if ai_severity.upper() in severity_map:
                return severity_map[ai_severity.upper()]
        # Fallback to risk score thresholds
        if risk_score >= 0.8:
            return "P1"
        if risk_score >= 0.6:
            return "P2"
        if risk_score >= 0.4:
            return "P3"
        return "P4"

    def _determine_action(self, priority: str, severity: Optional[str]) -> str:
        # AI severity drives the action when P1
        if priority == "P1":
            return "IMMEDIATE_ESCALATION"
        if priority == "P2":
            return "CREATE_INCIDENT"
        if priority == "P3":
            return "INVESTIGATE"
        return "IGNORE"

    def _generate_rationale(self, log: Log, analysis: Optional[LogAnalysis], scores: dict) -> str:
        """Generate a short human‑readable rationale.
        For now we build a templated string; later this can call Gemini.
        """
        parts = [
            f"Log ID {log.id} from service '{log.service_name}' triggered a {log.log_level}.",
            f"Risk score: {scores['risk_score']:.2f} (priority {scores['priority']}).",
            f"Business impact likelihood: {scores['business_impact_score']:.2f}.",
            f"Technical impact likelihood: {scores['technical_impact_score']:.2f}.",
            f"Frequency in last 24h: {scores['frequency_score']:.2f}.",
        ]
        if analysis and analysis.root_cause:
            parts.append(f"Root cause identified: {analysis.root_cause[:120]}...")
        return " ".join(parts)

    # ---------------------------------------------------------------------
    # Public method
    # ---------------------------------------------------------------------
    def triage(self, db: Session, log_id: int, analysis_id: Optional[int] = None) -> TriageDecisionResponse:
        """Run the full triage pipeline and persist the decision.

        Returns a Pydantic model (TriageDecisionResponse) that can be used directly
        in API responses.
        """
        # 1️⃣ Fetch the log
        log = db.scalar(select(Log).where(Log.id == log_id))
        if not log:
            raise ValueError(f"Log {log_id} not found")

        # 2️⃣ Optional analysis lookup (used when auto‑triggered from RCA)
        analysis = None
        if analysis_id:
            analysis = db.scalar(select(LogAnalysis).where(LogAnalysis.id == analysis_id))

        # 3️⃣ Compute scores
        frequency = self._calculate_frequency_score(db, log.service_name)
        business = self._text_score(analysis.business_impact if analysis else None)
        technical = self._text_score(analysis.technical_impact if analysis else None)
        # Confidence from RCA if available (0‑1)
        confidence = analysis.confidence_score if analysis else 0.5
        # Simple weighted risk formula
        risk = 0.3 * business + 0.3 * technical + 0.2 * frequency + 0.2 * confidence

        priority = self._determine_priority(risk, analysis.severity if analysis else None)
        action = self._determine_action(priority, analysis.severity if analysis else None)

        # 4️⃣ Rationale (templated for now)
        rationale = self._generate_rationale(log, analysis, {
            "risk_score": risk,
            "business_impact_score": business,
            "technical_impact_score": technical,
            "frequency_score": frequency,
            "priority": priority,
        })

        # 5️⃣ Persist decision
        decision = IncidentDecision(
            log_id=log.id,
            analysis_id=analysis.id if analysis else None,
            risk_score=risk,
            business_impact_score=business,
            technical_impact_score=technical,
            frequency_score=frequency,
            priority=priority,
            recommended_action=action,
            rationale=rationale,
            affected_services=json.dumps([s.service_name for s in analysis.services]) if analysis and analysis.services else None,
            similar_incident_count=int(frequency * 10),  # rough estimate
            status="OPEN",
        )
        db.add(decision)
        db.commit()
        db.refresh(decision)

        # 6️⃣ Phase 6: Trigger GitLab Agent if action requires it
        if action in ["CREATE_INCIDENT", "IMMEDIATE_ESCALATION"]:
            try:
                from app.services.gitlab.gitlab_agent import gitlab_agent
                # Run creation in background/non-blocking manner if possible, but here we just call it synchronously
                # Alternatively, we could spawn a thread. For simplicity, call directly.
                gitlab_issue = gitlab_agent.create_issue(db, decision.id)
                if gitlab_issue:
                    logger.info(f"GitLab Issue created for decision {decision.id}: {gitlab_issue.web_url}")
            except Exception as e:
                logger.error(f"Failed to trigger GitLab Agent for decision {decision.id}: {e}")

        # 7️⃣ Phase 7: Trigger Collaboration & Notifications Agent
        try:
            from app.services.notification.notification_agent import notification_agent
            notification_agent.send_notification(db, decision.id)
            logger.info(f"Notification agent dispatched alerts for decision {decision.id}")
        except Exception as e:
            logger.error(f"Failed to trigger Notification Agent for decision {decision.id}: {e}")

        # 8️⃣ Return Pydantic model
        return TriageDecisionResponse.from_orm(decision)

# Singleton for easy import elsewhere
triage_engine = TriageEngine()
