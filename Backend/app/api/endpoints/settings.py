import logging
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database.session import Base, engine, get_db
from app.repositories.repositories import app_setting_repo
from app.schemas.schemas import AppSettingResponse, TargetCodebasePathUpdate

logger = logging.getLogger(__name__)

router = APIRouter()

RESET_CONFIRMATION_PHRASE = "RESET DATABASE"

# App configuration, not ingested data -- excluded from the Danger Zone's
# stats display and from what "Reset Database" clears.
NON_RESETTABLE_TABLES = {"app_settings"}

TARGET_CODEBASE_PATH_KEY = "target_codebase_path"


class DatabaseResetRequest(BaseModel):
    confirm: str


@router.get("/database/stats")
def get_database_stats(db: Session = Depends(get_db)):
    """
    Row counts per application table, shown on the settings screen so
    the user knows what a reset would actually delete.
    """
    stats = {}
    for table in Base.metadata.sorted_tables:
        if table.name in NON_RESETTABLE_TABLES:
            continue
        count = db.execute(text(f'SELECT COUNT(*) FROM "{table.name}"')).scalar()
        stats[table.name] = count
    return stats


@router.get("/codebase-path", response_model=AppSettingResponse)
def get_codebase_path(db: Session = Depends(get_db)):
    """Returns the currently configured target codebase path used for RCA code diagnostics."""
    row = app_setting_repo.get_row(db, TARGET_CODEBASE_PATH_KEY)
    return AppSettingResponse(
        key=TARGET_CODEBASE_PATH_KEY,
        value=row.value if row else None,
        updated_at=row.updated_at if row else None,
    )


@router.put("/codebase-path", response_model=AppSettingResponse)
def set_codebase_path(payload: TargetCodebasePathUpdate, db: Session = Depends(get_db)):
    """
    Updates the target codebase path used by RCA's "Diagnose in Codebase" and
    "Ask Claude" features. Validates the path exists and is a readable
    directory (read-only check only -- this never touches the target repo).
    """
    path = payload.path.strip()
    if path and not os.path.isdir(path):
        raise HTTPException(status_code=400, detail="Path does not exist or is not a directory")
    if path and not os.access(path, os.R_OK):
        raise HTTPException(status_code=400, detail="Path is not readable (permission denied)")

    row = app_setting_repo.set(db, TARGET_CODEBASE_PATH_KEY, path)
    return AppSettingResponse(key=row.key, value=row.value, updated_at=row.updated_at)


@router.post("/database/reset")
def reset_database(payload: DatabaseResetRequest, db: Session = Depends(get_db)):
    """
    Clears all application data (logs, RCA analyses, incidents, notifications, etc.)
    while leaving the schema itself intact. Requires the exact confirmation phrase
    as a server-side guard in addition to the two-step confirmation in the UI.
    """
    if payload.confirm != RESET_CONFIRMATION_PHRASE:
        raise HTTPException(
            status_code=400,
            detail=f'Confirmation phrase must be exactly "{RESET_CONFIRMATION_PHRASE}"',
        )

    table_names = [table.name for table in Base.metadata.sorted_tables if table.name not in NON_RESETTABLE_TABLES]

    try:
        if engine.dialect.name == "sqlite":
            for name in reversed(table_names):
                db.execute(text(f'DELETE FROM "{name}"'))
        else:
            quoted = ", ".join(f'"{name}"' for name in table_names)
            db.execute(text(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE"))
        db.commit()
    except Exception:
        db.rollback()
        raise

    logger.warning("Database reset performed: all application tables cleared (%d tables).", len(table_names))
    return {"message": "Database reset complete.", "tables_cleared": table_names}
