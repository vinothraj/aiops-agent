import json
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.session import get_db
from app.models.models import FixSession
from app.schemas.schemas import (
    FixSessionResponse,
    FixSessionEventResponse,
    FixSessionCreateRequest,
    FixSessionBriefResponse,
    FixSessionEventCreate,
    FixSessionCancelRequest,
)
from app.services.remediation.fix_sessions import (
    FixSessionError,
    STATUSES,
    TERMINAL_STATUSES,
    build_brief,
    cancel_session,
    create_or_resume_session,
    record_event,
    verify_token,
)

router = APIRouter()

# Agents report through this header; the token is per session and only ever
# shown inside the brief (stored hashed).
TOKEN_HEADER = "X-AIOps-Session-Token"


def to_response(session: FixSession, include_events: bool = True) -> FixSessionResponse:
    log = session.log
    return FixSessionResponse(
        id=session.id,
        log_id=session.log_id,
        incident_decision_id=session.incident_decision_id,
        trigger=session.trigger,
        executor=session.executor,
        priority=session.priority,
        status=session.status,
        gitlab_project=session.gitlab_project,
        base_branch=session.base_branch,
        branch=session.branch,
        commit_sha=session.commit_sha,
        merge_request_url=session.merge_request_url,
        summary=session.summary,
        root_cause_confirmed=session.root_cause_confirmed,
        files_changed=json.loads(session.files_changed) if session.files_changed else [],
        tests_summary=session.tests_summary,
        created_at=session.created_at,
        updated_at=session.updated_at,
        started_at=session.started_at,
        finished_at=session.finished_at,
        service_name=log.service_name if log else None,
        log_level=log.log_level if log else None,
        log_message=(log.message[:300] if log and log.message else None),
        events=[FixSessionEventResponse.model_validate(e) for e in session.events] if include_events else [],
    )


def _get_session(db: Session, session_id: int) -> FixSession:
    session = db.get(FixSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Fix session not found.")
    return session


def _aiops_url(request: Request) -> str:
    # The agent runs on the developer's machine and calls the backend directly.
    # Behind a reverse proxy the request's own URL isn't reachable from there,
    # so an explicitly configured public URL wins.
    return (settings.AIOPS_PUBLIC_URL or str(request.base_url)).rstrip("/")


@router.post("", response_model=FixSessionBriefResponse)
def create_fix_session(payload: FixSessionCreateRequest, request: Request, db: Session = Depends(get_db)):
    """
    "Debug with Claude": opens (or resumes) the fix session for a log and
    returns the Claude Code brief, with a freshly issued callback token.
    """
    try:
        session, token = create_or_resume_session(
            db, payload.log_id, trigger="manual",
            ai_hypothesis=payload.ai_hypothesis, base_branch=payload.base_branch,
        )
    except FixSessionError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    return FixSessionBriefResponse(session=to_response(session), brief=build_brief(db, session, token, _aiops_url(request)))


@router.get("", response_model=List[FixSessionResponse])
def list_fix_sessions(
    status: Optional[str] = Query(None, description="Filter by status; 'active' = any non-terminal status"),
    log_id: Optional[int] = None,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = select(FixSession).order_by(FixSession.updated_at.desc()).limit(limit)
    if status == "active":
        query = query.where(FixSession.status.notin_(TERMINAL_STATUSES))
    elif status:
        if status not in STATUSES:
            raise HTTPException(status_code=400, detail=f"Unknown status '{status}'.")
        query = query.where(FixSession.status == status)
    if log_id is not None:
        query = query.where(FixSession.log_id == log_id)
    return [to_response(s, include_events=False) for s in db.scalars(query).all()]


@router.get("/{session_id}", response_model=FixSessionResponse)
def get_fix_session(session_id: int, db: Session = Depends(get_db)):
    return to_response(_get_session(db, session_id))


@router.post("/{session_id}/brief", response_model=FixSessionBriefResponse)
def reissue_brief(session_id: int, request: Request, db: Session = Depends(get_db)):
    """
    Re-issues the brief for an open session (e.g. one queued by Auto-Fix).
    Rotates the callback token, so any earlier copy can no longer report.
    """
    session = _get_session(db, session_id)
    if session.status in TERMINAL_STATUSES:
        raise HTTPException(status_code=409, detail="Session is closed; start a new one from the log.")
    try:
        session, token = create_or_resume_session(db, session.log_id)
    except FixSessionError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    return FixSessionBriefResponse(session=to_response(session), brief=build_brief(db, session, token, _aiops_url(request)))


@router.post("/{session_id}/events", response_model=FixSessionResponse)
def report_progress(
    session_id: int,
    payload: FixSessionEventCreate,
    db: Session = Depends(get_db),
    x_aiops_session_token: Optional[str] = Header(None, alias=TOKEN_HEADER),
):
    """Agent callback: status changes and progress notes. Requires the session token from the brief."""
    session = _get_session(db, session_id)
    if not verify_token(session, x_aiops_session_token):
        raise HTTPException(status_code=401, detail=f"Missing or invalid {TOKEN_HEADER}.")
    try:
        session = record_event(db, session, payload.model_dump(), source="agent")
    except FixSessionError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    return to_response(session)


@router.post("/{session_id}/cancel", response_model=FixSessionResponse)
def cancel_fix_session(session_id: int, payload: Optional[FixSessionCancelRequest] = None, db: Session = Depends(get_db)):
    session = _get_session(db, session_id)
    try:
        session = cancel_session(db, session, payload.reason if payload else None)
    except FixSessionError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    return to_response(session)
