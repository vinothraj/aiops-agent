import logging
import time
from threading import Lock, Thread
from typing import Dict, Optional

from fastapi import APIRouter

from app.database.session import SessionLocal
from app.repositories.repositories import log_repo
from app.schemas.schemas import LogStatsSummary

logger = logging.getLogger(__name__)

router = APIRouter()

# The summary scans the whole logs table, which takes seconds once it holds
# millions of rows. Cache it briefly and refresh in the background, so the
# dashboard (which polls this endpoint) gets an instant answer on every call
# after the first, at the cost of numbers up to STATS_CACHE_TTL_SECONDS old.
STATS_CACHE_TTL_SECONDS = 30

_cache: Optional[Dict[str, int]] = None
_cached_at = 0.0
_refresh_lock = Lock()


def _refresh_stats() -> Dict[str, int]:
    global _cache, _cached_at
    db = SessionLocal()
    try:
        stats = log_repo.get_stats_summary(db)
    finally:
        db.close()
    _cache, _cached_at = stats, time.monotonic()
    return stats


def _refresh_in_background() -> None:
    try:
        _refresh_stats()
    except Exception as e:
        logger.error(f"Error refreshing stats summary cache: {str(e)}")
    finally:
        _refresh_lock.release()


def warm_stats_cache() -> None:
    """Fill the cache in the background at startup so the first dashboard load is instant."""
    if _refresh_lock.acquire(blocking=False):
        Thread(target=_refresh_in_background, daemon=True, name="stats-refresh").start()


@router.get("/summary", response_model=LogStatsSummary)
def get_stats_summary():
    """
    Get summary stats of logs: total counts, levels, and unique services.
    """
    if _cache is None:
        # First call: nothing cached yet, so compute synchronously (one caller at a time).
        with _refresh_lock:
            if _cache is None:
                return _refresh_stats()
        return _cache

    if time.monotonic() - _cached_at > STATS_CACHE_TTL_SECONDS and _refresh_lock.acquire(blocking=False):
        # Stale: serve the cached numbers now and recompute behind the scenes.
        Thread(target=_refresh_in_background, daemon=True, name="stats-refresh").start()

    return _cache
