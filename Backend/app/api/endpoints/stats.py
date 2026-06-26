from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.repositories.repositories import log_repo
from app.schemas.schemas import LogStatsSummary

router = APIRouter()

@router.get("/summary", response_model=LogStatsSummary)
def get_stats_summary(db: Session = Depends(get_db)):
    """
    Get summary stats of logs: total counts, levels, and unique services.
    """
    stats = log_repo.get_stats_summary(db)
    return stats
