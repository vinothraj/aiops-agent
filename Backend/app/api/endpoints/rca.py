from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database.session import get_db
from app.schemas.schemas import (
    RCARequest,
    RCAStructuredResponse,
    LogAnalysisResponse,
)
from app.services.rca.rca_agent import rca_agent

router = APIRouter()


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
