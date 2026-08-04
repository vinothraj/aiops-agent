from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database.session import get_db
from app.models.models import GitlabIssue, IncidentDecision
from app.schemas.schemas import GitlabIssueResponse, GitlabIssueCreateRequest, GitlabIssueCreateFromLogRequest
from app.services.gitlab.gitlab_agent import gitlab_agent, is_gitlab_configured
from sqlalchemy import select

router = APIRouter()

@router.post("/create", response_model=GitlabIssueResponse)
def create_gitlab_issue(request: GitlabIssueCreateRequest, db: Session = Depends(get_db)):
    """Manually create a GitLab issue for a specific incident decision."""
    decision = db.scalar(select(IncidentDecision).where(IncidentDecision.id == request.incident_decision_id))
    if not decision:
        raise HTTPException(status_code=404, detail="IncidentDecision not found")

    issue = gitlab_agent.create_issue(db, decision.id)
    if not issue:
        raise HTTPException(status_code=500, detail="Failed to create GitLab issue. Check server logs and GitLab configuration.")

    return issue

@router.post("/create-from-log", response_model=GitlabIssueResponse)
def create_gitlab_issue_from_log(request: GitlabIssueCreateFromLogRequest, db: Session = Depends(get_db)):
    """
    Manually create a GitLab issue directly from a Log Explorer row. Uses
    that log's most recent triage decision (auto-created alongside its RCA
    analysis) for the issue content -- 404s if the log has no analysis/
    decision yet, since there'd be no root cause/severity/impact to file.
    """
    if not is_gitlab_configured(db):
        raise HTTPException(status_code=400, detail="GitLab is not configured. Set it up in Settings -> GitLab Integration.")

    decision = db.scalar(
        select(IncidentDecision)
        .where(IncidentDecision.log_id == request.log_id)
        .order_by(IncidentDecision.created_at.desc())
    )
    if not decision:
        raise HTTPException(status_code=404, detail="This log has no RCA analysis yet -- run one before creating a GitLab issue.")

    issue = gitlab_agent.create_issue(db, decision.id)
    if not issue:
        raise HTTPException(status_code=500, detail="Failed to create GitLab issue. Check server logs and GitLab configuration.")

    return issue

@router.get("/issues", response_model=List[GitlabIssueResponse])
def get_gitlab_issues(db: Session = Depends(get_db)):
    """List all tracked GitLab issues."""
    issues = db.scalars(select(GitlabIssue).order_by(GitlabIssue.created_at.desc())).all()
    return issues

@router.get("/issues/{issue_id}", response_model=GitlabIssueResponse)
def get_gitlab_issue(issue_id: int, db: Session = Depends(get_db)):
    """Get details and activity for a specific tracked GitLab issue."""
    issue = db.scalar(select(GitlabIssue).where(GitlabIssue.id == issue_id))
    if not issue:
        raise HTTPException(status_code=404, detail="GitlabIssue not found")
    return issue

@router.post("/sync", response_model=List[GitlabIssueResponse])
def sync_gitlab_issues(db: Session = Depends(get_db)):
    """Synchronize local tracking data with the latest status from GitLab."""
    updated_issues = gitlab_agent.sync_issues(db)
    return updated_issues
