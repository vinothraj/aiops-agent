from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database.session import get_db
from app.repositories.repositories import log_file_repo, monitored_source_root_repo
from app.schemas.schemas import LogFileResponse, MonitoredSourceRootCreate, MonitoredSourceRootResponse
from app.services.watcher import log_watcher_service, validate_root_path

router = APIRouter()

@router.get("", response_model=List[LogFileResponse])
def get_log_sources(db: Session = Depends(get_db)):
    """
    Get list of all monitored log files and their status.
    """
    sources = log_file_repo.get_all(db)
    return sources

@router.get("/roots", response_model=List[MonitoredSourceRootResponse])
def get_monitored_roots(db: Session = Depends(get_db)):
    """
    Lists every additional monitored root path (e.g. UNC network shares)
    configured on top of the default env-configured log directory.
    """
    return monitored_source_root_repo.get_all(db)

@router.post("/roots", response_model=MonitoredSourceRootResponse)
def add_monitored_root(payload: MonitoredSourceRootCreate, db: Session = Depends(get_db)):
    """
    Registers a new monitored root path. Validates the path exists and is
    readable (read-only check only), rejects duplicates, then hot-adds it
    to the running watcher without requiring a restart.
    """
    path = payload.path.strip()

    existing = monitored_source_root_repo.get_by_path(db, path)
    if existing:
        raise HTTPException(status_code=400, detail=f"Path is already monitored: {existing.path}")

    ok, reason = validate_root_path(path)
    if not ok:
        raise HTTPException(status_code=400, detail=reason)

    db_root = monitored_source_root_repo.create(db, MonitoredSourceRootCreate(path=path, label=payload.label))
    db_root = monitored_source_root_repo.update_status(db, db_root, "ok")

    log_watcher_service.add_root(path)

    return db_root

@router.delete("/roots/{root_id}")
def delete_monitored_root(root_id: int, db: Session = Depends(get_db)):
    """
    Stops watching a previously added root. Previously ingested log records
    are left untouched — only the watch itself is removed.
    """
    db_root = monitored_source_root_repo.get(db, root_id)
    if not db_root:
        raise HTTPException(status_code=404, detail="Monitored root not found")

    log_watcher_service.remove_root(db_root.path)
    monitored_source_root_repo.delete(db, db_root)

    return {"message": f"Stopped monitoring {db_root.path}"}
