"""
Incident Matcher

Detects whether a new failing log is a recurrence of a previously analyzed
incident, so the platform can reuse the existing solution instead of paying
for (and waiting on) a brand-new Gemini analysis.

Two layers of matching, cheapest first:
1. Exact fingerprint match - a deterministic hash of the normalized error
   signature (service, level, message template, top stack frame). Catches
   the common case: the same bug throwing the same error again.
2. Near-duplicate match - falls back to the existing RAG vector index
   (Qdrant) and accepts a hit only above INCIDENT_MATCH_SIMILARITY_THRESHOLD,
   for cases where wording differs slightly but it's clearly the same issue.
"""

import hashlib
import logging
import re
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.config import settings
from app.models.models import Log, LogAnalysis, IncidentGroup
from app.services.rag.rag_service import rag_service

logger = logging.getLogger(__name__)

_DIGIT_RE = re.compile(r"\d+")
_UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_QUOTED_RE = re.compile(r"(['\"])(?:(?=(\\?))\2.)*?\1")
_HEX_ADDR_RE = re.compile(r"0x[0-9a-fA-F]+")
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass
class MatchResult:
    group: IncidentGroup
    match_type: str  # "EXACT" or "NEAR_DUPLICATE"
    score: float


def _normalize_message(message: str) -> str:
    """Collapse variable parts of an error message into a stable template."""
    text = message.strip().lower()
    text = _UUID_RE.sub("<uuid>", text)
    text = _HEX_ADDR_RE.sub("<hex>", text)
    text = _QUOTED_RE.sub("<str>", text)
    text = _DIGIT_RE.sub("#", text)
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip()


def _top_stack_frame(stacktrace: Optional[str]) -> str:
    """Pull the first meaningful line of a stacktrace (exception type / first frame)."""
    if not stacktrace:
        return ""
    for line in stacktrace.splitlines():
        stripped = line.strip()
        if stripped:
            return _normalize_message(stripped)
    return ""


def compute_fingerprint(log: Log) -> str:
    """Deterministic signature for a failing log, stable across recurrences."""
    signature = "|".join([
        log.service_name or "",
        log.log_level or "",
        _normalize_message(log.message or ""),
        _top_stack_frame(log.stacktrace),
    ])
    return hashlib.sha256(signature.encode("utf-8")).hexdigest()


def find_matching_group(db: Session, target_log: Log) -> Optional[MatchResult]:
    """
    Look for an existing IncidentGroup this log is a recurrence of.
    Returns None if this looks like a genuinely new issue.
    """
    fingerprint = compute_fingerprint(target_log)

    exact = db.scalar(select(IncidentGroup).where(IncidentGroup.fingerprint == fingerprint))
    if exact:
        logger.info(f"Incident matcher: exact fingerprint match -> group {exact.id}")
        return MatchResult(group=exact, match_type="EXACT", score=1.0)

    # Fall back to vector similarity against previously ingested RCA docs.
    query_text = f"{target_log.service_name} {target_log.message} {target_log.stacktrace or ''}".strip()
    hits = rag_service.search_similar_incidents(query=query_text, limit=3)
    for hit in hits:
        if hit.get("doc_type") != "RCA" or hit.get("score", 0) < settings.INCIDENT_MATCH_SIMILARITY_THRESHOLD:
            continue
        source_id = hit.get("source_id") or ""
        if not source_id.startswith("analysis_"):
            continue
        try:
            analysis_id = int(source_id.removeprefix("analysis_"))
        except ValueError:
            continue

        matched_analysis = db.scalar(select(LogAnalysis).where(LogAnalysis.id == analysis_id))
        if not matched_analysis or not matched_analysis.incident_group_id:
            continue

        group = db.scalar(select(IncidentGroup).where(IncidentGroup.id == matched_analysis.incident_group_id))
        if group:
            logger.info(
                f"Incident matcher: near-duplicate match (score={hit['score']:.3f}) -> group {group.id}"
            )
            return MatchResult(group=group, match_type="NEAR_DUPLICATE", score=hit["score"])

    return None
