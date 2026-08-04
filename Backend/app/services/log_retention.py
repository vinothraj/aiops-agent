import logging
import time
from datetime import datetime, timedelta
from threading import Thread
from typing import Optional

from sqlalchemy import exists

from app.database.session import SessionLocal
from app.models.models import Log, LogAnalysis, IncidentDecision
from app.repositories.repositories import app_setting_repo

logger = logging.getLogger(__name__)

LOG_RETENTION_ENABLED_KEY = "log_retention_enabled"
RETENTION_HOURS = 24

# How often the background loop re-checks the setting and runs a sweep.
# Deliberately coarse -- this is a housekeeping job, not a real-time one.
CHECK_INTERVAL_SECONDS = 300


class LogRetentionService:
    """
    When enabled via Settings, periodically deletes raw ingested logs older
    than RETENTION_HOURS to keep DB size (and the CPU/disk load that comes
    with it) bounded on resource-constrained machines.

    Only unanalyzed logs are ever deleted: any log referenced by a
    LogAnalysis or IncidentDecision is preserved regardless of age, since
    both cascade-delete from logs.id and deleting the log would silently
    destroy that RCA/incident history too.
    """

    def __init__(self):
        self._thread: Optional[Thread] = None
        self._stop = False

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop = False
        self._thread = Thread(target=self._run, daemon=True, name="log-retention")
        self._thread.start()
        logger.info(f"Log retention service started (checks every {CHECK_INTERVAL_SECONDS}s)")

    def stop(self) -> None:
        self._stop = True

    def _run(self) -> None:
        while not self._stop:
            try:
                self.run_once_if_enabled()
            except Exception as e:
                logger.error(f"Log retention sweep failed: {e}", exc_info=True)
            for _ in range(CHECK_INTERVAL_SECONDS):
                if self._stop:
                    break
                time.sleep(1)

    def run_once_if_enabled(self) -> int:
        db = SessionLocal()
        try:
            enabled = (app_setting_repo.get(db, LOG_RETENTION_ENABLED_KEY) or "false").lower() == "true"
            if not enabled:
                return 0
            deleted = self._purge_old_logs(db)
            if deleted:
                logger.info(f"Log retention: deleted {deleted} unanalyzed log(s) older than {RETENTION_HOURS}h")
            return deleted
        finally:
            db.close()

    def _purge_old_logs(self, db) -> int:
        cutoff = datetime.utcnow() - timedelta(hours=RETENTION_HOURS)
        has_analysis = exists().where(LogAnalysis.log_id == Log.id)
        has_decision = exists().where(IncidentDecision.log_id == Log.id)
        deleted = (
            db.query(Log)
            .filter(Log.timestamp < cutoff, ~has_analysis, ~has_decision)
            .delete(synchronize_session=False)
        )
        db.commit()
        return deleted


log_retention_service = LogRetentionService()
