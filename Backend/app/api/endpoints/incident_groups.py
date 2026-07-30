from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import List

from app.database.session import get_db
from app.models.models import IncidentGroup
from app.schemas.schemas import IncidentGroupResponse, IncidentGroupDetailResponse

router = APIRouter()


@router.get("", response_model=List[IncidentGroupResponse])
def list_incident_groups(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """
    Enterprise-level view of recurring incidents: one row per distinct error
    signature, ordered by how often it has recurred so the most repeated
    (and therefore highest-priority-to-permanently-fix) issues surface first.
    """
    groups = db.scalars(
        select(IncidentGroup)
        .order_by(IncidentGroup.occurrence_count.desc(), IncidentGroup.last_seen_at.desc())
        .offset(skip)
        .limit(limit)
    ).all()
    return list(groups)


@router.get("/{group_id}", response_model=IncidentGroupDetailResponse)
def get_incident_group(
    group_id: int,
    db: Session = Depends(get_db),
):
    """Full history of a single recurring incident: its known fix plus every occurrence."""
    group = db.scalar(select(IncidentGroup).where(IncidentGroup.id == group_id))
    if not group:
        raise HTTPException(status_code=404, detail=f"Incident group {group_id} not found")
    return group
