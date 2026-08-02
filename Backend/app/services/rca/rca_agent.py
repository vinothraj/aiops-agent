"""
Enterprise AI Root Cause Analysis Agent
(Forcing reload to pick up RAG service)

This module implements an AI SRE (Site Reliability Engineer) agent that analyzes
production failures, identifies probable root causes, assesses business and technical
impact, detects patterns, and suggests remediation actions.

The agent calls whichever AI provider is currently configured (Claude, Gemini, or a
local Ollama model -- see app.services.rca.ai_providers) to perform intelligent
analysis of log context windows (surrounding logs before/after a failure) and
produces structured JSON output.
"""

import json
import re
import logging
from datetime import datetime
from typing import Optional, Dict, Any, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.config import settings
from app.models.models import Log, LogAnalysis, AnalysisPattern, AnalysisDependency, AnalysisService, IncidentGroup
from app.schemas.schemas import RCAStructuredResponse, RCARequest
from app.services.rag.rag_service import rag_service
from app.services.triage.triage_engine import triage_engine
from app.services.rca import incident_matcher
from app.services.rca.ai_providers import get_ai_suggestion, AiProviderError

logger = logging.getLogger(__name__)


class LogNotFoundError(Exception):
    """Raised when analyze() is given a log_id that doesn't exist -- kept
    distinct from ValueError so it can't be confused with an unrelated
    ValueError bubbling up from deep inside a provider SDK."""
    pass


# ─── Root Cause Categories ────────────────────────────────────────────────────

ROOT_CAUSE_CATEGORIES = [
    "DATABASE", "API_FAILURE", "AUTHENTICATION", "AUTHORIZATION",
    "NETWORK", "TIMEOUT", "MEMORY", "CPU", "DISK", "CACHE",
    "MESSAGE_QUEUE", "CONFIGURATION", "DEPENDENCY_FAILURE",
    "THIRD_PARTY_FAILURE", "APPLICATION_BUG", "DATA_INTEGRITY", "UNKNOWN"
]

SEVERITY_LEVELS = {
    "P1": "Production Down",
    "P2": "Major Functionality Impacted",
    "P3": "Partial Service Impact",
    "P4": "Informational"
}

INCIDENT_RECOMMENDATIONS = [
    "CREATE_INCIDENT", "MONITOR", "IGNORE", "REQUIRES_HUMAN_REVIEW"
]

PATTERN_TYPES = [
    "Repeated Error", "Error Burst", "Memory Leak Pattern",
    "Connection Leak Pattern", "Retry Storm", "Thread Exhaustion",
    "Database Pool Exhaustion", "Deadlock Pattern",
    "Deployment Correlation", "Infrastructure Failure Pattern"
]

# ─── System Prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an Enterprise AI SRE (Site Reliability Engineer) Agent.
Your role is to analyze production log failures and provide structured root cause analysis.

For every ERROR or FATAL log you receive, you must perform:
1. Log Analysis - Understand what happened
2. Root Cause Analysis - Identify the probable root cause
3. Severity Classification - Assign P1/P2/P3/P4
4. Business Impact Assessment - Explain impact in business language
5. Service Impact Assessment - Identify affected services
6. Dependency Impact Detection - Identify affected dependencies
7. Similar Error Detection / Pattern Detection
8. Resolution Recommendation - Immediate, short-term, and long-term fixes
9. Incident Recommendation - CREATE_INCIDENT, MONITOR, IGNORE, or REQUIRES_HUMAN_REVIEW
10. Confidence Scoring - Provide confidence for root cause, severity, and recommendation

Root Cause Categories (pick one):
DATABASE, API_FAILURE, AUTHENTICATION, AUTHORIZATION, NETWORK, TIMEOUT, MEMORY, CPU, DISK, CACHE, MESSAGE_QUEUE, CONFIGURATION, DEPENDENCY_FAILURE, THIRD_PARTY_FAILURE, APPLICATION_BUG, DATA_INTEGRITY, UNKNOWN

Severity Levels:
- P1: Production Down
- P2: Major Functionality Impacted
- P3: Partial Service Impact
- P4: Informational

Pattern Types to look for:
Repeated Error, Error Burst, Memory Leak Pattern, Connection Leak Pattern, Retry Storm, Thread Exhaustion, Database Pool Exhaustion, Deadlock Pattern, Deployment Correlation, Infrastructure Failure Pattern

Incident Recommendations:
CREATE_INCIDENT, MONITOR, IGNORE, REQUIRES_HUMAN_REVIEW

You MUST respond with valid JSON only, matching this exact schema:
{
    "incident_type": "<type of incident>",
    "root_cause_category": "<one of the root cause categories>",
    "root_cause": "<detailed root cause explanation>",
    "severity": "<P1|P2|P3|P4>",
    "business_impact": "<impact in business language>",
    "technical_impact": "<technical impact details>",
    "affected_services": ["<service1>", "<service2>"],
    "affected_dependencies": ["<dep1>", "<dep2>"],
    "pattern_detected": ["<pattern1>"],
    "deployment_related": false,
    "recommended_action": "<primary recommended action>",
    "immediate_fix": "<what to do right now>",
    "short_term_fix": "<what to do this week>",
    "long_term_fix": "<permanent fix>",
    "incident_recommendation": "<CREATE_INCIDENT|MONITOR|IGNORE|REQUIRES_HUMAN_REVIEW>",
    "confidence_score": 0.0,
    "severity_confidence": 0.0,
    "recommendation_confidence": 0.0,
    "summary": "<one paragraph summary of the entire analysis>"
}

Be thorough. Analyze the surrounding context logs to understand the sequence of events leading to and following the failure. 
If historical incidents or runbooks are provided, you MUST explicitly consider their documented fixes before suggesting generic ones. If a historical incident matches the current error perfectly, prioritize its resolution.
"""


class RootCauseAnalysisAgent:
    """
    Enterprise-grade Root Cause Analysis Agent, powered by whichever AI
    provider is currently configured (Claude / Gemini / local Ollama).

    Responsibilities:
    - Gather context around a failing log (previous + subsequent logs)
    - Build a rich prompt with service metadata
    - Call the configured AI provider for structured analysis
    - Persist results to the database for future RAG and trend analysis
    """

    # ─── Context Gathering ─────────────────────────────────────────────────

    def _get_surrounding_logs(
        self, db: Session, target_log: Log, before: int = 50, after: int = 20
    ) -> Dict[str, Any]:
        """
        Fetch the log context window around a failure.
        Captures logs chronologically across all services to detect cascading failures.
        """
        # Previous logs (before the failure)
        prev_query = (
            select(Log)
            .where(Log.timestamp <= target_log.timestamp)
            .where(Log.id != target_log.id)
            .order_by(Log.timestamp.desc())
            .limit(before)
        )
        previous_logs = list(db.scalars(prev_query).all())
        previous_logs.reverse()  # chronological order

        # Subsequent logs (after the failure)
        next_query = (
            select(Log)
            .where(Log.timestamp >= target_log.timestamp)
            .where(Log.id != target_log.id)
            .order_by(Log.timestamp.asc())
            .limit(after)
        )
        subsequent_logs = list(db.scalars(next_query).all())

        return {
            "previous_logs": previous_logs,
            "subsequent_logs": subsequent_logs,
        }

    def _format_log_entry(self, log: Log) -> str:
        """Format a single log entry for the prompt."""
        entry = f"[{log.timestamp}] [{log.service_name}] [{log.log_level}] {log.message}"
        if log.stacktrace:
            entry += f"\n  STACKTRACE: {log.stacktrace[:500]}"
        return entry

    # ─── Prompt Construction ───────────────────────────────────────────────

    def _build_prompt(
        self,
        target_log: Log,
        context: Dict[str, Any],
        metadata: Optional[RCARequest] = None,
    ) -> str:
        """
        Build the analysis prompt with full context for Gemini.
        """
        sections = []

        # Section 1: Current Error Log
        sections.append("## CURRENT ERROR LOG (THE FAILURE)")
        sections.append(self._format_log_entry(target_log))
        if target_log.stacktrace:
            sections.append(f"\nFull Stacktrace:\n{target_log.stacktrace}")

        # Section 2: Previous Logs (context before failure)
        sections.append(f"\n## PREVIOUS LOGS (Last {len(context['previous_logs'])} entries before failure)")
        if context["previous_logs"]:
            for log in context["previous_logs"]:
                sections.append(self._format_log_entry(log))
        else:
            sections.append("No previous logs available.")

        # Section 3: Subsequent Logs (context after failure)
        sections.append(f"\n## SUBSEQUENT LOGS (Next {len(context['subsequent_logs'])} entries after failure)")
        if context["subsequent_logs"]:
            for log in context["subsequent_logs"]:
                sections.append(self._format_log_entry(log))
        else:
            sections.append("No subsequent logs available.")

        # Section 4: Historical Incidents (RAG)
        historical_docs = rag_service.search_similar_incidents(query=target_log.message)
        if historical_docs:
            sections.append("\n## HISTORICAL INCIDENTS & RUNBOOKS (RAG KNOWLEDGE BASE)")
            sections.append("The following historical incidents or runbooks may be relevant to the current error:")
            for i, doc in enumerate(historical_docs, 1):
                sections.append(f"\n### Record {i} [{doc['doc_type']}] (Relevance Score: {doc['score']:.2f})")
                sections.append(f"Title: {doc['title']}")
                sections.append(f"Content:\n{doc['content']}")
        else:
            sections.append("\n## HISTORICAL INCIDENTS & RUNBOOKS")
            sections.append("No similar historical incidents or runbooks found in the knowledge base.")

        # Section 5: Service Metadata
        sections.append("\n## SERVICE METADATA")
        sections.append(f"- Service Name: {metadata.service_name or target_log.service_name}")
        sections.append(f"- Environment: {metadata.environment if metadata else 'production'}")
        sections.append(f"- Version: {metadata.version if metadata and metadata.version else 'Unknown'}")
        if metadata and metadata.deployment_timestamp:
            sections.append(f"- Last Deployment: {metadata.deployment_timestamp}")
            sections.append(f"- Error Time: {target_log.timestamp}")
            sections.append("- NOTE: Check if this error correlates with the deployment.")

        # Section 6: Instructions
        sections.append("\n## INSTRUCTIONS")
        sections.append("Analyze the above logs and provide a structured JSON root cause analysis.")
        sections.append("Respond with ONLY valid JSON, no markdown formatting, no code fences.")

        return "\n".join(sections)

    # ─── AI Provider Call ───────────────────────────────────────────────────

    _JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)

    def _call_ai(self, db: Session, prompt: str) -> Tuple[RCAStructuredResponse, str, str]:
        """
        Send the prompt to whichever AI provider is configured and parse the
        structured response. AiProviderError propagates as-is (not wrapped as
        ValueError, which the endpoint layer maps to 404 "log not found" --
        a provider failure is a distinct, differently-coded error case).
        """
        logger.info("Sending RCA analysis request to the configured AI provider...")
        provider, model, raw_text = get_ai_suggestion(db, prompt, system_prompt=SYSTEM_PROMPT)

        logger.info(f"Response received from {provider}/{model}, parsing JSON...")
        return self._parse_rca_response(raw_text), provider, model

    def _parse_rca_response(self, raw_text: str) -> RCAStructuredResponse:
        """
        Parses the AI's JSON response into a structured result, tolerating the
        extra prose/commentary that less-compliant (esp. smaller local) models
        sometimes wrap around the JSON despite instructions not to.
        """
        raw_text = raw_text.strip()

        # Clean up potential markdown fences
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        if raw_text.startswith("```"):
            raw_text = raw_text[3:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
        raw_text = raw_text.strip()

        try:
            parsed = json.loads(raw_text)
            return RCAStructuredResponse(**parsed)
        except (json.JSONDecodeError, Exception):
            pass

        # Fallback: extract the first {...} block in case the model added
        # surrounding commentary despite being told to respond with JSON only.
        match = self._JSON_OBJECT_RE.search(raw_text)
        if match:
            try:
                parsed = json.loads(match.group(0))
                return RCAStructuredResponse(**parsed)
            except (json.JSONDecodeError, Exception) as e:
                logger.error(f"Failed to parse extracted JSON block: {e}")

        logger.error(f"Failed to parse AI response as JSON. Raw response: {raw_text[:500]}")
        return RCAStructuredResponse(
            incident_type="PARSE_ERROR",
            root_cause_category="UNKNOWN",
            root_cause="Failed to parse the AI response as valid JSON.",
            severity="P4",
            summary=f"The AI agent returned a non-parseable response. Raw excerpt: {raw_text[:300]}",
            confidence_score=0.0,
            severity_confidence=0.0,
            recommendation_confidence=0.0,
            incident_recommendation="REQUIRES_HUMAN_REVIEW",
        )

    # ─── Database Persistence ──────────────────────────────────────────────

    def _persist_analysis(
        self, db: Session, log_id: int, target_log: Log, rca: RCAStructuredResponse,
        ai_provider: Optional[str] = None, ai_model: Optional[str] = None
    ) -> LogAnalysis:
        """Save the analysis results and related entities to the database."""

        # Build recommendation text combining all fix levels
        recommendation_text = (
            f"Immediate: {rca.immediate_fix}\n"
            f"Short-term: {rca.short_term_fix}\n"
            f"Long-term: {rca.long_term_fix}\n"
            f"Action: {rca.recommended_action}\n"
            f"Incident: {rca.incident_recommendation}"
        )

        # Create the main analysis record
        analysis = LogAnalysis(
            log_id=log_id,
            root_cause=rca.root_cause,
            root_cause_category=rca.root_cause_category,
            severity=rca.severity,
            business_impact=rca.business_impact,
            technical_impact=rca.technical_impact,
            confidence_score=rca.confidence_score,
            recommendation=recommendation_text,
            summary=rca.summary,
            ai_provider=ai_provider,
            ai_model=ai_model,
        )
        db.add(analysis)
        db.flush()  # Get the ID before adding related records

        # Save detected patterns
        for pattern in rca.pattern_detected:
            db.add(AnalysisPattern(analysis_id=analysis.id, pattern=pattern))

        # Save affected dependencies
        for dep in rca.affected_dependencies:
            db.add(AnalysisDependency(analysis_id=analysis.id, dependency=dep))

        # Save affected services
        for svc in rca.affected_services:
            db.add(AnalysisService(analysis_id=analysis.id, service_name=svc))

        db.commit()
        db.refresh(analysis)

        logger.info(
            f"RCA analysis persisted: id={analysis.id}, "
            f"category={rca.root_cause_category}, severity={rca.severity}, "
            f"confidence={rca.confidence_score}"
        )

        # Auto-Ingest into RAG Knowledge Base
        try:
            rag_service.ingest_document(
                db=db,
                title=f"RCA: {rca.root_cause_category} in {target_log.service_name}",
                content=f"Error Log: {target_log.message}\n\nRoot Cause: {rca.root_cause}\n\nResolution: {recommendation_text}",
                doc_type="RCA",
                source_id=f"analysis_{analysis.id}"
            )
            logger.info("Auto-ingested RCA into RAG Knowledge Base.")
        except Exception as e:
            logger.error(f"Failed to auto-ingest RCA into RAG: {e}")

        return analysis

    # ─── Incident Grouping / Known-Issue Reuse ─────────────────────────────

    def _parse_recommendation(self, recommendation_text: Optional[str]) -> Dict[str, str]:
        """Split the combined recommendation blob back into its labeled parts."""
        fields = {"immediate_fix": "", "short_term_fix": "", "long_term_fix": "",
                  "recommended_action": "", "incident_recommendation": ""}
        if not recommendation_text:
            return fields
        prefixes = {
            "Immediate: ": "immediate_fix",
            "Short-term: ": "short_term_fix",
            "Long-term: ": "long_term_fix",
            "Action: ": "recommended_action",
            "Incident: ": "incident_recommendation",
        }
        for line in recommendation_text.splitlines():
            for prefix, field in prefixes.items():
                if line.startswith(prefix):
                    fields[field] = line[len(prefix):].strip()
        return fields

    def _create_new_group(self, db: Session, target_log: Log, analysis: LogAnalysis) -> IncidentGroup:
        """First time we've seen this error signature: start tracking it as a group."""
        fingerprint = incident_matcher.compute_fingerprint(target_log)
        group = IncidentGroup(
            fingerprint=fingerprint,
            title=f"{analysis.root_cause_category} in {target_log.service_name}",
            root_cause_category=analysis.root_cause_category,
            representative_analysis_id=analysis.id,
            occurrence_count=1,
        )
        db.add(group)
        db.flush()

        analysis.incident_group_id = group.id
        db.commit()
        db.refresh(group)
        logger.info(f"Created new incident group {group.id} (fingerprint={fingerprint[:12]}...)")
        return group

    def _attach_to_existing_group(
        self, db: Session, analysis: LogAnalysis, group: IncidentGroup
    ) -> None:
        """
        Used when force-regenerating a fresh analysis for a log whose error
        signature already matches a known group: keeps the new (possibly
        different-provider) result linked to the existing group instead of
        spawning a duplicate group for the same underlying issue.
        """
        analysis.incident_group_id = group.id
        analysis.is_recurring = True
        group.occurrence_count += 1
        group.last_seen_at = datetime.utcnow()
        db.commit()
        db.refresh(analysis)
        db.refresh(group)
        logger.info(f"Attached regenerated analysis {analysis.id} to existing group {group.id}")

    def _reuse_known_solution(
        self, db: Session, log_id: int, target_log: Log, match: "incident_matcher.MatchResult"
    ) -> Dict[str, Any]:
        """
        This error is a confirmed recurrence of a known incident. Skip the Gemini
        call entirely and copy the group's existing solution onto a new record,
        so the recurrence is tracked without spending AI tokens re-deriving it.
        """
        group = match.group
        representative = group.representative_analysis

        analysis = LogAnalysis(
            log_id=log_id,
            root_cause=representative.root_cause,
            root_cause_category=representative.root_cause_category,
            severity=representative.severity,
            business_impact=representative.business_impact,
            technical_impact=representative.technical_impact,
            confidence_score=representative.confidence_score,
            recommendation=representative.recommendation,
            summary=representative.summary,
            incident_group_id=group.id,
            is_recurring=True,
            match_score=match.score,
            ai_provider=representative.ai_provider,
            ai_model=representative.ai_model,
        )
        db.add(analysis)
        db.flush()

        for pattern in representative.patterns:
            db.add(AnalysisPattern(analysis_id=analysis.id, pattern=pattern.pattern))
        for dep in representative.dependencies:
            db.add(AnalysisDependency(analysis_id=analysis.id, dependency=dep.dependency))
        for svc in representative.services:
            db.add(AnalysisService(analysis_id=analysis.id, service_name=svc.service_name))

        group.occurrence_count += 1
        group.last_seen_at = datetime.utcnow()

        db.commit()
        db.refresh(analysis)

        logger.info(
            f"Reused known solution from group {group.id} for log_id={log_id} "
            f"(match_type={match.match_type}, score={match.score:.3f}, "
            f"occurrence #{group.occurrence_count})"
        )

        recommendation_fields = self._parse_recommendation(representative.recommendation)
        rca_response = RCAStructuredResponse(
            incident_type=group.title,
            root_cause_category=analysis.root_cause_category,
            root_cause=analysis.root_cause,
            severity=analysis.severity,
            business_impact=analysis.business_impact or "",
            technical_impact=analysis.technical_impact or "",
            affected_services=[s.service_name for s in analysis.services],
            affected_dependencies=[d.dependency for d in analysis.dependencies],
            pattern_detected=[p.pattern for p in analysis.patterns],
            confidence_score=analysis.confidence_score,
            summary=analysis.summary or "",
            **recommendation_fields,
        )

        return {"analysis": analysis, "rca_detail": rca_response, "match": match}

    # ─── Public API ────────────────────────────────────────────────────────

    def analyze(
        self,
        db: Session,
        log_id: int,
        metadata: Optional[RCARequest] = None,
        force_new: bool = False,
    ) -> Dict[str, Any]:
        """
        Main entry point: run a full root cause analysis on a log entry.

        Args:
            db: Database session
            log_id: The ID of the error/fatal log to analyze
            metadata: Optional service metadata (environment, version, deployment time)
            force_new: Bypass the known-issue reuse shortcut and always call the
                configured AI provider fresh -- used to regenerate a suggestion
                (e.g. after switching AI provider in Settings) instead of getting
                back the same cached answer.

        Returns:
            Dict with the analysis record and the full structured RCA response
        """
        # 1. Fetch the target log
        target_log = db.scalar(select(Log).where(Log.id == log_id))
        if not target_log:
            raise LogNotFoundError(f"Log entry with id={log_id} not found.")

        logger.info(
            f"Starting RCA analysis for log_id={log_id}, "
            f"service={target_log.service_name}, level={target_log.log_level}, force_new={force_new}"
        )

        # 2. Known-issue check: is this a confirmed recurrence of an already-analyzed
        #    incident? If so (and not force_new), reuse its solution instead of
        #    spending AI tokens re-deriving it.
        match = incident_matcher.find_matching_group(db, target_log)
        if match and not force_new:
            result = self._reuse_known_solution(db, log_id, target_log, match)
            analysis, rca_response = result["analysis"], result["rca_detail"]
        else:
            # 2a. Gather surrounding context
            context = self._get_surrounding_logs(db, target_log)
            logger.info(
                f"Context gathered: {len(context['previous_logs'])} before, "
                f"{len(context['subsequent_logs'])} after"
            )

            # 2b. Build the prompt
            request_metadata = metadata or RCARequest(service_name=target_log.service_name)
            prompt = self._build_prompt(target_log, context, request_metadata)

            # 2c. Call whichever AI provider is currently configured
            rca_response, provider, model = self._call_ai(db, prompt)

            # 2d. Persist to database, tagging which provider/model produced it
            analysis = self._persist_analysis(db, log_id, target_log, rca_response, ai_provider=provider, ai_model=model)

            # 2e. Group tracking: attach to the existing group if this is a
            #     regenerate of an already-known signature, otherwise start a new one.
            if match:
                self._attach_to_existing_group(db, analysis, match.group)
            else:
                self._create_new_group(db, target_log, analysis)

        # 6. Auto-triage: chain into the Incident Decision Engine
        triage_decision = None
        try:
            triage_decision = triage_engine.triage(
                db=db, log_id=log_id, analysis_id=analysis.id
            )
            logger.info(
                f"Auto-triage completed: priority={triage_decision.priority}, "
                f"action={triage_decision.recommended_action}"
            )
        except Exception as e:
            logger.error(f"Auto-triage failed (non-blocking): {e}")

        return {
            "analysis": analysis,
            "rca_detail": rca_response,
            "triage_decision": triage_decision,
        }

    def get_analysis(self, db: Session, log_id: int) -> Optional[LogAnalysis]:
        """Fetch the most recent analysis for a given log entry."""
        return db.scalar(
            select(LogAnalysis)
            .where(LogAnalysis.log_id == log_id)
            .order_by(LogAnalysis.created_at.desc())
        )

    def get_all_analyses(
        self, db: Session, skip: int = 0, limit: int = 50
    ):
        """Fetch all historical analyses for dashboard/RAG views."""
        query = (
            select(LogAnalysis)
            .order_by(LogAnalysis.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(db.scalars(query).all())


# Singleton instance
rca_agent = RootCauseAnalysisAgent()
