from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import List, Optional

from app.database.session import get_db
from app.models.models import IncidentDecision
from app.schemas.schemas import TriageRequest, TriageDecisionResponse
from app.services.triage.triage_engine import triage_engine

router = APIRouter()


@router.post("/triage", response_model=TriageDecisionResponse)
def trigger_triage(request: TriageRequest, db: Session = Depends(get_db)):
    """Manually trigger incident triage for a given log_id."""
    try:
        decision = triage_engine.triage(db=db, log_id=request.log_id)
        return decision
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Triage failed: {e}")


@router.get("", response_model=List[TriageDecisionResponse])
def list_incidents(
    priority: Optional[str] = None,
    status: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """List all incident decisions with optional filters."""
    query = select(IncidentDecision).order_by(IncidentDecision.created_at.desc())

    if priority:
        query = query.where(IncidentDecision.priority == priority)
    if status:
        query = query.where(IncidentDecision.status == status)

    query = query.offset(skip).limit(limit)
    results = db.execute(query).scalars().all()
    return results


@router.get("/{incident_id}", response_model=TriageDecisionResponse)
def get_incident(incident_id: int, db: Session = Depends(get_db)):
    """Get a single incident decision by ID."""
    decision = db.execute(
        select(IncidentDecision).where(IncidentDecision.id == incident_id)
    ).scalar_one_or_none()

    if not decision:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found.")
    return decision
