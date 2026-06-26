from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from app.database.session import get_db
from app.repositories.repositories import log_repo, log_file_repo
from app.schemas.schemas import LogResponse, LogReprocessRequest
from app.services.watcher import LogFileProcessor, log_watcher_service

router = APIRouter()

@router.get("", response_model=List[LogResponse])
def get_logs(
    service_name: Optional[str] = None,
    log_level: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    search_query: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """
    Retrieve logs with optional filters and pagination.
    """
    logs = log_repo.get_all(
        db,
        skip=skip,
        limit=limit,
        service_name=service_name,
        log_level=log_level,
        start_date=start_date,
        end_date=end_date,
        search_query=search_query
    )
    return logs

@router.get("/search", response_model=List[LogResponse])
def search_logs(
    q: str = Query(..., min_length=1),
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """
    Search log messages and stack traces matching a string.
    """
    logs = log_repo.get_all(
        db,
        skip=skip,
        limit=limit,
        search_query=q
    )
    return logs

@router.get("/{log_id}", response_model=LogResponse)
def get_log_by_id(log_id: int, db: Session = Depends(get_db)):
    """
    Fetch a single log record by ID.
    """
    log = log_repo.get(db, log_id)
    if not log:
        raise HTTPException(status_code=404, detail="Log record not found")
    return log

@router.post("/reprocess")
def reprocess_logs(
    request: Optional[LogReprocessRequest] = None,
    db: Session = Depends(get_db)
):
    """
    Reprocesses logs for a specific file or all files.
    Deletes the logs associated with the file from database and sets position back to 0.
    """
    request_data = request or LogReprocessRequest()
    files_to_reprocess = []

    if request_data.file_id:
        db_file = log_file_repo.get(db, request_data.file_id)
        if not db_file:
            raise HTTPException(status_code=404, detail="Log source file not found")
        files_to_reprocess.append(db_file)
    elif request_data.file_path:
        db_file = log_file_repo.get_by_path(db, request_data.file_path)
        if not db_file:
            raise HTTPException(status_code=404, detail="Log source file not found")
        files_to_reprocess.append(db_file)
    else:
        # Reprocess all files
        # Synchronously scan directory first to register any newly placed log files (crucial for SQLite environments)
        log_watcher_service.scan_directory()
        files_to_reprocess = log_file_repo.get_all(db)

    for db_file in files_to_reprocess:
        # Delete existing logs from logs table
        log_repo.delete_by_path(db, db_file.file_path)
        
        # Reset position & update status in DB
        db_file.last_processed_position = 0
        db_file.status = "new"
        db.add(db_file)
        db.commit()
        
        # Trigger reprocessing in a background thread or synchronously
        # For small to medium systems, synchronous or deferred call is fine.
        # We will trigger the LogFileProcessor on this path
        try:
            LogFileProcessor.process_file(db_file.file_path)
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Reprocessing failed for {db_file.file_path}: {str(e)}"
            )

    return {"message": f"Reprocessing triggered for {len(files_to_reprocess)} file(s)"}
