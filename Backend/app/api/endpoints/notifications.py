from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import List, Optional

from app.database.session import get_db
from app.models.models import Notification, NotificationRecipient, NotificationTemplate, IncidentDecision, Log, LogAnalysis, GitlabIssue, IssueActivity
from app.schemas.schemas import (
    NotificationResponse,
    NotificationSendRequest,
    NotificationTestRequest,
    NotificationRecipientResponse,
    NotificationRecipientCreate,
    TimelineEventResponse
)
from app.services.notification.notification_agent import notification_agent

router = APIRouter()

# ─── Core Notification APIs ───────────────────────────────────────────────────

@router.post("/send", response_model=List[NotificationResponse])
def send_incident_notification(request: NotificationSendRequest, db: Session = Depends(get_db)):
    """Triggers dynamic notification dispatch for an incident decision."""
    try:
        notifications = notification_agent.send_notification(
            db=db,
            incident_decision_id=request.incident_decision_id,
            channels=request.channels
        )
        return notifications
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to dispatch notifications: {e}")

@router.get("", response_model=List[NotificationResponse])
def get_notifications(
    channel: Optional[str] = None,
    status: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Retrieve notification log history."""
    query = select(Notification).order_by(Notification.created_at.desc())
    if channel:
        query = query.where(Notification.channel == channel)
    if status:
        query = query.where(Notification.status == status)
    
    query = query.offset(skip).limit(limit)
    results = db.execute(query).scalars().all()
    return results

@router.get("/digest")
def get_daily_operational_digest(db: Session = Depends(get_db)):
    """Generates and retrieves an SRE daily operational digest using Gemini."""
    try:
        digest = notification_agent.generate_daily_digest(db)
        return {"digest": digest}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate daily digest: {e}")

@router.get("/insights")
def get_weekly_reliability_insights(db: Session = Depends(get_db)):
    """Generates and retrieves weekly SRE reliability insights using Gemini."""
    try:
        insights = notification_agent.generate_weekly_insights(db)
        return {"insights": insights}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate weekly insights: {e}")

@router.get("/{id}", response_model=NotificationResponse)
def get_notification(id: int, db: Session = Depends(get_db)):
    """Retrieve details for a specific notification log."""
    notification = db.scalar(select(Notification).where(Notification.id == id))
    if not notification:
        raise HTTPException(status_code=404, detail=f"Notification {id} not found.")
    return notification

@router.post("/test")
def test_notification_connection(request: NotificationTestRequest):
    """Utility API to test webhook or email notification configurations."""
    success = False
    if request.channel == "teams":
        success = notification_agent.send_teams_message(
            webhook_url=request.destination,
            title="[AIOps Integration Test]",
            markdown_body="This is a test notification from the AIOps platform. Verification successful."
        )
    elif request.channel == "email":
        success = notification_agent.send_email_message(
            destination=request.destination,
            subject="[AIOps Integration Test]",
            html_body="<h3>AIOps Verification Test</h3><p>This email verifies that email notification routing is functioning correctly.</p>"
        )
    else:
        raise HTTPException(status_code=400, detail="Invalid notification channel. Use 'teams' or 'email'.")
    
    return {"status": "success" if success else "failed", "message": "Notification dispatched."}

@router.post("/retry/{id}", response_model=NotificationResponse)
def retry_failed_alert(id: int, db: Session = Depends(get_db)):
    """Manually triggers retry for a failed notification."""
    notification = db.scalar(select(Notification).where(Notification.id == id))
    if not notification:
        raise HTTPException(status_code=404, detail=f"Notification {id} not found.")
    
    # Reset status
    notification.status = "PENDING"
    notification.retry_count += 1
    db.commit()

    success = False
    if notification.channel == "teams":
        success = notification_agent.send_teams_message(notification.recipient_destination, notification.title, notification.message)
    elif notification.channel == "email":
        success = notification_agent.send_email_message(notification.recipient_destination, notification.title, f"<p>{notification.message}</p>")

    notification.status = "SENT" if success else "FAILED"
    if not success:
        notification.error_message = f"Manual retry failed."
    
    db.commit()
    db.refresh(notification)
    return notification

# ─── Notification Preferences / Recipients APIs ────────────────────────────────

@router.get("/recipients/list", response_model=List[NotificationRecipientResponse])
def list_notification_recipients(db: Session = Depends(get_db)):
    """List all dynamic notification routing rules."""
    recipients = db.execute(select(NotificationRecipient)).scalars().all()
    
    # If empty, run _get_recipients with a dummy category to bootstrap defaults automatically
    if not recipients:
        notification_agent._get_recipients(db, "DEFAULT")
        recipients = db.execute(select(NotificationRecipient)).scalars().all()
        
    return recipients

@router.post("/recipients", response_model=NotificationRecipientResponse)
def create_notification_recipient(request: NotificationRecipientCreate, db: Session = Depends(get_db)):
    """Creates a new dynamic routing rule."""
    recipient = NotificationRecipient(
        category=request.category.upper(),
        channel=request.channel.lower(),
        destination=request.destination,
        recipient_name=request.recipient_name,
        is_active=request.is_active
    )
    db.add(recipient)
    db.commit()
    db.refresh(recipient)
    return recipient

@router.put("/recipients/{id}", response_model=NotificationRecipientResponse)
def update_notification_recipient(id: int, request: NotificationRecipientCreate, db: Session = Depends(get_db)):
    """Updates an existing dynamic routing rule."""
    recipient = db.scalar(select(NotificationRecipient).where(NotificationRecipient.id == id))
    if not recipient:
        raise HTTPException(status_code=404, detail=f"Routing rule {id} not found.")
    
    recipient.category = request.category.upper()
    recipient.channel = request.channel.lower()
    recipient.destination = request.destination
    recipient.recipient_name = request.recipient_name
    recipient.is_active = request.is_active
    
    db.commit()
    db.refresh(recipient)
    return recipient

@router.delete("/recipients/{id}")
def delete_notification_recipient(id: int, db: Session = Depends(get_db)):
    """Deletes an dynamic routing rule."""
    recipient = db.scalar(select(NotificationRecipient).where(NotificationRecipient.id == id))
    if not recipient:
        raise HTTPException(status_code=404, detail=f"Routing rule {id} not found.")
    
    db.delete(recipient)
    db.commit()
    return {"message": "Recipient deleted successfully."}

# ─── Incident Chronological Timeline API ──────────────────────────────────────

@router.get("/timeline/{incident_id}", response_model=List[TimelineEventResponse])
def get_incident_timeline(incident_id: int, db: Session = Depends(get_db)):
    """Fetches chronological audit timeline events combining Logs, RCA, Triage, GitLab, and Notifications."""
    decision = db.scalar(select(IncidentDecision).where(IncidentDecision.id == incident_id))
    if not decision:
        raise HTTPException(status_code=404, detail=f"Incident Decision {incident_id} not found.")

    timeline = []

    # 1. Log Ingestion Event
    if decision.log:
        timeline.append(TimelineEventResponse(
            timestamp=decision.log.timestamp,
            event_type="LOG",
            title="Log Alert Ingested",
            description=f"Log event detected from service '{decision.log.service_name}'. Level: {decision.log.log_level}.",
            status="SUCCESS",
            meta={"message": decision.log.message}
        ))

    # 2. RCA Analysis Event
    if decision.analysis:
        timeline.append(TimelineEventResponse(
            timestamp=decision.analysis.created_at,
            event_type="RCA",
            title="AI Root Cause Analysis",
            description=f"Gemini analyzed log context. Root Cause Category identified: {decision.analysis.root_cause_category}.",
            status="SUCCESS",
            meta={
                "root_cause": decision.analysis.root_cause,
                "severity": decision.analysis.severity,
                "confidence": decision.analysis.confidence_score
            }
        ))

    # 3. Incident Triage Event
    timeline.append(TimelineEventResponse(
        timestamp=decision.created_at,
        event_type="TRIAGE",
        title="Incident Triage & Risk Decision",
        description=f"Triage engine evaluated risk score: {decision.risk_score:.2f}. Assigned priority: {decision.priority}.",
        status="SUCCESS",
        meta={
            "recommended_action": decision.recommended_action,
            "rationale": decision.rationale
        }
    ))

    # 4. GitLab Issues Activity Events
    gitlab_issue = db.scalar(select(GitlabIssue).where(GitlabIssue.incident_decision_id == decision.id))
    if gitlab_issue:
        # Initial creation event
        timeline.append(TimelineEventResponse(
            timestamp=gitlab_issue.created_at,
            event_type="GITLAB",
            title=f"GitLab Issue Created #{gitlab_issue.gitlab_issue_iid}",
            description=f"Auto-escalated to GitLab project. Issue State: {gitlab_issue.state}.",
            status="SUCCESS",
            meta={"url": gitlab_issue.web_url, "title": gitlab_issue.title}
        ))

        # Subsequent sync/activities
        activities = db.scalars(
            select(IssueActivity).where(IssueActivity.gitlab_issue_id == gitlab_issue.id).order_by(IssueActivity.timestamp.asc())
        ).all()
        for act in activities:
            timeline.append(TimelineEventResponse(
                timestamp=act.timestamp,
                event_type="GITLAB",
                title=f"GitLab Activity: {act.action_type.capitalize()}",
                description=act.description,
                status="SUCCESS"
            ))

    # 5. Notifications Dispatch Events
    notifications = db.scalars(
        select(Notification).where(Notification.incident_decision_id == decision.id).order_by(Notification.created_at.asc())
    ).all()
    for n in notifications:
        timeline.append(TimelineEventResponse(
            timestamp=n.created_at,
            event_type="NOTIFICATION",
            title=f"Notification Dispatched ({n.channel.capitalize()})",
            description=f"Sent to {n.recipient_destination}.",
            status=n.status,
            meta={"error": n.error_message} if n.status == "FAILED" else None
        ))

    # Sort chronological
    timeline.sort(key=lambda x: x.timestamp)
    return timeline
