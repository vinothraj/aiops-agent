from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List

from app.database.session import get_db
from app.repositories.repositories import log_file_repo
from app.schemas.schemas import LogFileResponse

router = APIRouter()

@router.get("", response_model=List[LogFileResponse])
def get_log_sources(db: Session = Depends(get_db)):
    """
    Get list of all monitored log files and their status.
    """
    sources = log_file_repo.get_all(db)
    return sources
