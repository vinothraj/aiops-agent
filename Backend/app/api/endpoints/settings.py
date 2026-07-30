import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database.session import Base, engine, get_db

logger = logging.getLogger(__name__)

router = APIRouter()

RESET_CONFIRMATION_PHRASE = "RESET DATABASE"


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
        count = db.execute(text(f'SELECT COUNT(*) FROM "{table.name}"')).scalar()
        stats[table.name] = count
    return stats


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

    table_names = [table.name for table in Base.metadata.sorted_tables]

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
