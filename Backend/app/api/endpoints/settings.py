import logging
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings as app_settings
from app.database.session import Base, engine, get_db
from app.repositories.repositories import app_setting_repo
from app.schemas.schemas import AppSettingResponse, TargetCodebasePathUpdate, AiProviderSettingsResponse, AiProviderSettingsUpdate
from app.services.rca.ai_providers import (
    get_provider_config,
    is_claude_configured,
    is_gemini_configured,
    AI_PROVIDER_KEY,
    OLLAMA_BASE_URL_KEY,
    OLLAMA_MODEL_KEY,
    AUTO_RCA_ENABLED_KEY,
    CLAUDE_API_KEY_SETTING,
    GEMINI_API_KEY_SETTING,
    VALID_PROVIDERS,
)

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


@router.get("/ai-provider", response_model=AiProviderSettingsResponse)
def get_ai_provider_settings(db: Session = Depends(get_db)):
    """
    Returns the currently configured AI provider (Claude / Gemini / local
    Ollama) used by RCA's "Ask AI" feature, plus whether each cloud
    provider's API key is actually set (never the key values themselves --
    checks both a Settings-stored key and the .env fallback).
    """
    config = get_provider_config(db)
    return AiProviderSettingsResponse(
        provider=config["provider"],
        ollama_base_url=config["ollama_base_url"],
        ollama_model=config["ollama_model"],
        claude_configured=is_claude_configured(db),
        gemini_configured=is_gemini_configured(db),
        auto_rca_enabled=config["auto_rca_enabled"],
    )


@router.put("/ai-provider", response_model=AiProviderSettingsResponse)
def set_ai_provider_settings(payload: AiProviderSettingsUpdate, db: Session = Depends(get_db)):
    """
    Switches which AI provider RCA's "Ask AI" feature uses, and/or updates
    the local Ollama connection details, toggles automatic RCA on
    newly-ingested ERROR logs, and/or sets the Claude/Gemini API key directly
    from this UI (stored in the database, taking precedence over the .env
    file -- so both providers are fully configurable without touching the
    codebase). Send an empty string for claude_api_key/gemini_api_key to
    clear the stored key and fall back to .env; omit the field entirely to
    leave whatever's currently stored untouched. Note: auto-RCA only ever
    actually runs when the provider is Ollama, regardless of that flag --
    see auto_trigger.py.
    """
    provider = payload.provider.strip().lower()
    if provider not in VALID_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Provider must be one of: {', '.join(sorted(VALID_PROVIDERS))}")

    app_setting_repo.set(db, AI_PROVIDER_KEY, provider)
    if payload.ollama_base_url is not None:
        app_setting_repo.set(db, OLLAMA_BASE_URL_KEY, payload.ollama_base_url.strip())
    if payload.ollama_model is not None:
        app_setting_repo.set(db, OLLAMA_MODEL_KEY, payload.ollama_model.strip())
    if payload.auto_rca_enabled is not None:
        app_setting_repo.set(db, AUTO_RCA_ENABLED_KEY, "true" if payload.auto_rca_enabled else "false")
    if payload.claude_api_key is not None:
        app_setting_repo.set(db, CLAUDE_API_KEY_SETTING, payload.claude_api_key.strip())
    if payload.gemini_api_key is not None:
        app_setting_repo.set(db, GEMINI_API_KEY_SETTING, payload.gemini_api_key.strip())

    config = get_provider_config(db)
    return AiProviderSettingsResponse(
        provider=config["provider"],
        ollama_base_url=config["ollama_base_url"],
        ollama_model=config["ollama_model"],
        claude_configured=is_claude_configured(db),
        gemini_configured=is_gemini_configured(db),
        auto_rca_enabled=config["auto_rca_enabled"],
    )


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
