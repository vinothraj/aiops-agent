import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from app.database.session import SessionLocal
from app.services.rca.ai_providers import get_provider_config

logger = logging.getLogger(__name__)

FAILURE_LEVELS = {"ERROR", "FATAL"}

# Fire-and-forget worker pool, deliberately small: local models don't
# parallelize well on typical single-GPU/CPU hardware, so this exists to keep
# ingestion from blocking on inference, not to fan analyses out concurrently.
_MAX_WORKERS = 2
_executor = ThreadPoolExecutor(max_workers=_MAX_WORKERS, thread_name_prefix="auto-rca")


def maybe_schedule_auto_rca(log_id: int, log_level: Optional[str]) -> None:
    """
    Schedules an RCA analysis for a newly-ingested log, but ONLY when all of:
    1. The log is ERROR/FATAL level (never DEBUG/INFO/WARN).
    2. The "Automatic Root Cause Analysis" setting is explicitly enabled
       (default: off -- an opt-in the user must turn on in Settings).
    3. The currently configured AI provider is the free local Ollama model.

    Claude/Gemini are cloud, pay-per-token providers -- auto-analyzing every
    single error against them would spend real money without explicit intent,
    so this stays hard-gated to Ollama regardless of the toggle above. Manually
    clicking "Generate Root Cause Analysis" still works with any provider.
    """
    if not log_level or log_level.upper() not in FAILURE_LEVELS:
        return
    _executor.submit(_run, log_id)


def _run(log_id: int) -> None:
    db = SessionLocal()
    try:
        config = get_provider_config(db)
        if not config["auto_rca_enabled"]:
            return
        if config["provider"] != "ollama":
            return

        from app.services.rca.rca_agent import rca_agent
        logger.info(f"Auto-triggering RCA for log_id={log_id} (provider=ollama, free local model)")
        rca_agent.analyze(db, log_id)
    except Exception as e:
        logger.error(f"Auto-RCA failed for log_id={log_id}: {e}", exc_info=True)
    finally:
        db.close()
