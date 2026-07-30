import logging
import os

import anthropic
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional

from app.core.config import settings
from app.database.session import get_db
from app.repositories.repositories import app_setting_repo
from app.schemas.schemas import (
    RCARequest,
    RCAStructuredResponse,
    LogAnalysisResponse,
    DiagnoseCodebaseResponse,
    CodebaseCandidateFile,
    AskClaudeRequest,
    AskClaudeResponse,
)
from app.services.rca.rca_agent import rca_agent
from app.services.rca.codebase_diagnostics import parse_stack_trace_frames, search_codebase_for_candidates
from app.api.endpoints.settings import TARGET_CODEBASE_PATH_KEY

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_FILES_SENT_TO_CLAUDE = 3
MAX_CHARS_PER_FILE_TO_CLAUDE = 6000


def _get_configured_codebase_path(db: Session) -> str:
    path = app_setting_repo.get(db, TARGET_CODEBASE_PATH_KEY)
    if not path:
        raise HTTPException(
            status_code=400,
            detail="Target codebase path is not configured. Set it on the Settings page first."
        )
    if not os.path.isdir(path):
        raise HTTPException(
            status_code=400,
            detail=f"Configured target codebase path is unreachable: {path}"
        )
    return path


def _diagnose(db: Session, log_id: int) -> DiagnoseCodebaseResponse:
    analysis = rca_agent.get_analysis(db, log_id)
    if not analysis:
        raise HTTPException(status_code=404, detail=f"No RCA analysis found for log_id={log_id}")

    target_path = _get_configured_codebase_path(db)
    log = analysis.log

    frames = parse_stack_trace_frames(log.stacktrace, log.message)
    keywords = (
        [analysis.root_cause_category]
        + [s.service_name for s in analysis.services]
        + [d.dependency for d in analysis.dependencies]
    )
    candidates, truncated = search_codebase_for_candidates(target_path, frames, keywords)

    return DiagnoseCodebaseResponse(
        log_id=log_id,
        target_path=target_path,
        stack_frames_parsed=[f"{f['file']}:{f['line']}" for f in frames],
        candidates=[CodebaseCandidateFile(**c) for c in candidates],
        truncated=truncated
    )


@router.post("/analyze/{log_id}", response_model=LogAnalysisResponse)
def trigger_analysis(
    log_id: int,
    request: Optional[RCARequest] = None,
    db: Session = Depends(get_db),
):
    """
    Trigger a Root Cause Analysis for a specific log entry.

    The agent will:
    1. Fetch surrounding logs (50 before, 20 after) for context
    2. Build a rich prompt with service metadata
    3. Call Gemini for structured analysis
    4. Persist results to the database
    5. Return the analysis result
    """
    try:
        result = rca_agent.analyze(db, log_id, metadata=request)
        analysis = result["analysis"]
        rca_detail = result["rca_detail"]

        # Build the response manually to include rca_detail
        return LogAnalysisResponse(
            id=analysis.id,
            log_id=analysis.log_id,
            root_cause=analysis.root_cause,
            root_cause_category=analysis.root_cause_category,
            severity=analysis.severity,
            business_impact=analysis.business_impact,
            technical_impact=analysis.technical_impact,
            confidence_score=analysis.confidence_score,
            recommendation=analysis.recommendation,
            summary=analysis.summary,
            created_at=analysis.created_at,
            patterns=[{"id": p.id, "pattern": p.pattern} for p in analysis.patterns],
            dependencies=[{"id": d.id, "dependency": d.dependency} for d in analysis.dependencies],
            services=[{"id": s.id, "service_name": s.service_name} for s in analysis.services],
            rca_detail=rca_detail,
            incident_group_id=analysis.incident_group_id,
            is_recurring=analysis.is_recurring,
            match_score=analysis.match_score,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"RCA analysis failed: {str(e)}"
        )


@router.get("/analysis/{log_id}", response_model=LogAnalysisResponse)
def get_analysis(
    log_id: int,
    db: Session = Depends(get_db),
):
    """
    Fetch the most recent Root Cause Analysis for a specific log entry.
    """
    analysis = rca_agent.get_analysis(db, log_id)
    if not analysis:
        raise HTTPException(
            status_code=404,
            detail=f"No analysis found for log_id={log_id}"
        )
    return analysis


@router.get("/analyses", response_model=List[LogAnalysisResponse])
def get_all_analyses(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """
    Fetch all historical RCA analyses (for dashboard/RAG views).
    """
    analyses = rca_agent.get_all_analyses(db, skip=skip, limit=limit)
    return analyses


@router.post("/{log_id}/diagnose-codebase", response_model=DiagnoseCodebaseResponse)
def diagnose_codebase(log_id: int, db: Session = Depends(get_db)):
    """
    Read-only: searches the configured target codebase for files likely
    responsible for this log's error, using its RCA's stack trace and
    affected services/dependencies. Never writes to the target repo.
    """
    return _diagnose(db, log_id)


@router.post("/{log_id}/ask-claude", response_model=AskClaudeResponse)
def ask_claude_for_fix(log_id: int, payload: Optional[AskClaudeRequest] = None, db: Session = Depends(get_db)):
    """
    Sends the RCA context plus the top candidate files' content to Claude and
    returns a suggested fix as text/diff for the user to review. Never writes
    the suggestion back to the target codebase, creates branches, or commits.
    """
    if not settings.CLAUDE_API_KEY:
        raise HTTPException(
            status_code=400,
            detail="CLAUDE_API_KEY is not configured. Set it in the backend .env file."
        )

    analysis = rca_agent.get_analysis(db, log_id)
    if not analysis:
        raise HTTPException(status_code=404, detail=f"No RCA analysis found for log_id={log_id}")
    log = analysis.log

    requested_paths = payload.candidate_file_paths if payload else None
    if requested_paths:
        _get_configured_codebase_path(db)  # validate configured/reachable
        candidate_paths = requested_paths
    else:
        diagnosis = _diagnose(db, log_id)
        candidate_paths = [c.file_path for c in diagnosis.candidates]

    if not candidate_paths:
        raise HTTPException(
            status_code=400,
            detail='No candidate files found to send to Claude. Run "Diagnose in Codebase" first.'
        )

    file_sections = []
    files_used = []
    for file_path in candidate_paths[:MAX_FILES_SENT_TO_CLAUDE]:
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read(MAX_CHARS_PER_FILE_TO_CLAUDE)
        except Exception as e:
            logger.warning(f"Could not read {file_path} for Claude prompt: {e}")
            continue
        file_sections.append(f"--- {file_path} ---\n{content}")
        files_used.append(file_path)

    if not file_sections:
        raise HTTPException(status_code=400, detail="Candidate files could not be read (unreachable or permission denied).")

    prompt = f"""You are helping diagnose and fix a production application bug.

Root cause analysis:
- Category: {analysis.root_cause_category}
- Severity: {analysis.severity}
- Root cause: {analysis.root_cause}
- Summary: {analysis.summary or "N/A"}
- Recommendation: {analysis.recommendation or "N/A"}

Log message:
{log.message}

Stack trace:
{log.stacktrace or "N/A"}

Candidate source files from the application codebase (most likely responsible, based on the stack trace / RCA):

{chr(10).join(file_sections)}

Based on the above, explain the likely bug in these files and propose a concrete code fix. Where possible, show the fix as a diff or clearly-marked before/after code snippet. Do not assume you can run or apply this change -- just provide your analysis and suggested fix as text for a developer to review.
"""

    try:
        client = anthropic.Anthropic(api_key=settings.CLAUDE_API_KEY)
        response = client.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}]
        )
        suggestion = "".join(block.text for block in response.content if block.type == "text")
    except Exception as e:
        logger.error(f"Claude API call failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=502, detail=f"Claude API call failed: {str(e)}")

    return AskClaudeResponse(
        log_id=log_id,
        model=settings.CLAUDE_MODEL,
        suggestion=suggestion,
        files_used=files_used
    )
