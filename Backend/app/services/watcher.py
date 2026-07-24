import os
import time
import logging
import re
from datetime import datetime, timedelta
from threading import Thread
from typing import Optional, List, Dict, Any

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from app.core.config import settings
from app.database.session import SessionLocal
from app.repositories.repositories import log_file_repo, log_repo, monitored_source_root_repo
from app.schemas.schemas import LogFileCreate, LogFileUpdate
from app.services.parser import LogParser

logger = logging.getLogger(__name__)
parser = LogParser()

# Matches folder names that identify a single deployment instance rather than a
# service, e.g. instance01, instance-02, node3, host_4, pod07, prod0353m1 (case-insensitive).
# Configurable via settings.INSTANCE_FOLDER_PATTERN for environments with different naming.
INSTANCE_FOLDER_PATTERN = re.compile(settings.INSTANCE_FOLDER_PATTERN, re.IGNORECASE)

def get_active_root_paths(db) -> List[str]:
    """
    Returns every directory the watcher should monitor: the legacy
    env-configured settings.MONITORED_LOGS_DIR plus any additional roots
    (e.g. UNC network paths) added via the Log Sources UI, deduplicated.
    """
    roots = [settings.MONITORED_LOGS_DIR]
    roots.extend(r.path for r in monitored_source_root_repo.get_all_active(db))

    seen = set()
    deduped = []
    for root in roots:
        key = os.path.normcase(os.path.normpath(root))
        if key not in seen:
            seen.add(key)
            deduped.append(root)
    return deduped

def validate_root_path(path: str) -> tuple[bool, str]:
    """
    Validates a candidate monitored root path (local or UNC network path).
    Read-only check only — never creates, modifies, or removes anything.
    """
    if not path or not path.strip():
        return False, "Path cannot be empty"
    if not os.path.exists(path):
        return False, "Path does not exist or is unreachable (check network share connectivity/permissions)"
    if not os.path.isdir(path):
        return False, "Path is not a directory"
    if not os.access(path, os.R_OK):
        return False, "Path is not readable (permission denied)"
    return True, "ok"

def _find_matching_root(file_path: str, monitored_roots: List[str]) -> str:
    """
    Picks the most specific (longest) monitored root that contains file_path.
    Falls back to the first configured root if none match (e.g. file passed
    directly rather than discovered via a scan).
    """
    norm_path = os.path.normpath(file_path)
    best_root = None
    for root in monitored_roots:
        norm_root = os.path.normpath(root)
        try:
            rel = os.path.relpath(norm_path, norm_root)
        except ValueError:
            # Paths on different drives/UNC hosts — can't be relative to each other
            continue
        if rel == os.curdir or not rel.startswith(os.pardir):
            if best_root is None or len(norm_root) > len(os.path.normpath(best_root)):
                best_root = root
    return best_root if best_root is not None else (monitored_roots[0] if monitored_roots else "")

def parse_source_identity(file_path: str, monitored_roots) -> tuple[str, Optional[str]]:
    """
    Determines (service_name, instance_id) based on directory structure,
    relative to whichever monitored root actually contains this file.

    Examples (relative to the monitored root):
      instance01/ecommerce-site.log        -> service="ecommerce-site", instance="instance01"
      ProductService/instance02/app.log    -> service="ProductService", instance="instance02"
      ProductService/application.log       -> service="ProductService", instance=None
      application.log                      -> service="application",   instance=None
    """
    if isinstance(monitored_roots, str):
        monitored_roots = [monitored_roots]

    norm_path = os.path.normpath(file_path)
    norm_monitored = os.path.normpath(_find_matching_root(file_path, monitored_roots))

    rel_path = os.path.relpath(norm_path, norm_monitored)
    parts = rel_path.split(os.sep)
    dir_parts = parts[:-1]
    filename = parts[-1]

    instance_id: Optional[str] = None
    service_parts = []
    for part in dir_parts:
        if instance_id is None and INSTANCE_FOLDER_PATTERN.match(part):
            instance_id = part
        else:
            service_parts.append(part)

    if service_parts:
        service_name = service_parts[0]
    else:
        name, _ = os.path.splitext(filename)
        service_name = name

    return service_name, instance_id

class LogFileProcessor:
    @staticmethod
    def should_process_file(file_path: str) -> bool:
        """
        Determines whether the file should be processed based on:
        1. Extension (.log or .txt)
        2. Modification time (within settings.LOG_FILE_MAX_AGE_HOURS)
        3. Excludes historical/rotated files containing date patterns,
           except if the date corresponds to today or yesterday.
        """
        if not os.path.isfile(file_path):
            return False

        _, ext = os.path.splitext(file_path)
        if ext.lower() not in [".log", ".txt"]:
            return False

        # Filter by modification time (configurable freshness window)
        try:
            mtime = os.path.getmtime(file_path)
            if time.time() - mtime > settings.LOG_FILE_MAX_AGE_HOURS * 3600:
                return False
        except Exception as e:
            logger.error(f"Error checking modification time for {file_path}: {e}")
            return False

        # Exclude historical files containing date patterns (e.g. YYYY-MM-DD or YYYYMMDD)
        # unless they represent today's or yesterday's active rotated logs.
        filename = os.path.basename(file_path)
        date_patterns = [
            r'\d{4}-\d{2}-\d{2}',
            r'\d{8}'
        ]
        
        has_date_pattern = False
        found_date_str = None
        for pattern in date_patterns:
            match = re.search(pattern, filename)
            if match:
                has_date_pattern = True
                found_date_str = match.group(0)
                break
                
        if has_date_pattern and found_date_str:
            today = datetime.now()
            yesterday = today - timedelta(days=1)
            allowed_dates = [
                today.strftime("%Y-%m-%d"),
                today.strftime("%Y%m%d"),
                yesterday.strftime("%Y-%m-%d"),
                yesterday.strftime("%Y%m%d")
            ]
            if found_date_str not in allowed_dates:
                return False

        return True

    @staticmethod
    def process_file(file_path: str) -> None:
        """
        Processes new lines of a log file starting from its last processed position.
        Updates position and status in the database.
        """
        if not LogFileProcessor.should_process_file(file_path):
            return

        db = SessionLocal()
        try:
            file_name = os.path.basename(file_path)
            service_name, instance_id = parse_source_identity(file_path, get_active_root_paths(db))

            # 1. Fetch or create log file record
            db_log_file = log_file_repo.get_by_path(db, file_path)
            if not db_log_file:
                db_log_file = log_file_repo.create(
                    db,
                    LogFileCreate(
                        file_name=file_name,
                        file_path=file_path,
                        service_name=service_name,
                        instance_id=instance_id,
                        last_processed_position=0,
                        status="new"
                    )
                )

            start_pos = db_log_file.last_processed_position
            file_size = os.path.getsize(file_path)

            # 2. Check for rotation/truncation
            if file_size < start_pos:
                logger.info(f"File truncated or rotated: {file_path}. Resetting position to 0.")
                start_pos = 0

            if file_size == start_pos:
                # No new data to process
                return

            # Update status to processing
            log_file_repo.update(db, db_log_file, LogFileUpdate(status="processing"))

            # 3. Read new content
            with open(file_path, "rb") as f:
                f.seek(start_pos)
                content_bytes = f.read()
                new_pos = f.tell()

            if not content_bytes:
                log_file_repo.update(db, db_log_file, LogFileUpdate(status="completed"))
                return

            content = content_bytes.decode("utf-8", errors="replace")

            # 4. Handle partial line writes: back up position to exclude incomplete last line
            lines_to_process = []
            if not content.endswith("\n") and not content.endswith("\r"):
                lines = content.splitlines()
                if lines:
                    last_line = lines[-1]
                    lines_to_process = lines[:-1]
                    new_pos -= len(last_line.encode("utf-8"))
            else:
                lines_to_process = content.splitlines()

            # 5. Parse and save logs
            if lines_to_process:
                parsed_logs = parser.parse_lines(
                    lines_to_process, file_name, file_path,
                    default_service=service_name, instance_id=instance_id
                )
                if parsed_logs:
                    log_repo.create_many(db, parsed_logs)

            # 6. Update file info
            log_file_repo.update(
                db,
                db_log_file,
                LogFileUpdate(
                    last_processed_position=new_pos,
                    last_processed_time=datetime.utcnow(),
                    status="completed"
                )
            )
            logger.info(f"Processed {len(lines_to_process)} lines from {file_path}. Position: {start_pos} -> {new_pos}")

        except Exception as e:
            logger.error(f"Error processing file {file_path}: {str(e)}", exc_info=True)
            # Try to mark as failed
            try:
                db_log_file = log_file_repo.get_by_path(db, file_path)
                if db_log_file:
                    log_file_repo.update(db, db_log_file, LogFileUpdate(status="failed"))
            except Exception as inner_e:
                logger.error(f"Failed to update status to failed for {file_path}: {str(inner_e)}")
        finally:
            db.close()


class LogWatcherHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if not event.is_directory:
            LogFileProcessor.process_file(event.src_path)

    def on_created(self, event):
        if not event.is_directory:
            LogFileProcessor.process_file(event.src_path)


class LogWatcherService:
    def __init__(self):
        self.observer: Optional[Observer] = None
        self.thread: Optional[Thread] = None
        self.running = False
        self._handler: Optional[LogWatcherHandler] = None
        self._watches: Dict[str, Any] = {}  # normalized root path -> ObservedWatch

    def _get_active_roots(self) -> List[str]:
        db = SessionLocal()
        try:
            return get_active_root_paths(db)
        finally:
            db.close()

    def _scan_root(self, root: str) -> None:
        logger.info(f"Scanning monitored directory: {root}")
        if not os.path.exists(root):
            # Default legacy dir gets auto-created; additional (e.g. UNC) roots are
            # left alone — they're expected to already exist on their own host/share,
            # and the periodic re-scan will pick them up once reachable.
            if os.path.normcase(os.path.normpath(root)) == os.path.normcase(os.path.normpath(settings.MONITORED_LOGS_DIR)):
                logger.warning(f"Directory {root} does not exist. Creating it.")
                os.makedirs(root, exist_ok=True)
            else:
                logger.warning(f"Monitored root {root} is not currently reachable. Will retry on next scan cycle.")
            return

        try:
            for dirpath, _, files in os.walk(root):
                for file in files:
                    file_path = os.path.join(dirpath, file)
                    LogFileProcessor.process_file(file_path)
        except Exception as e:
            logger.error(f"Error scanning monitored root {root}: {str(e)}")

    def scan_all_roots(self) -> None:
        """
        Recursively scans every active monitored root (legacy dir + any
        additional roots added via the Log Sources UI) to catch up on files.
        """
        for root in self._get_active_roots():
            self._scan_root(root)

    def scan_directory(self) -> None:
        """Kept for backward compatibility with existing call sites (e.g. main.py)."""
        self.scan_all_roots()

    def _schedule_watch(self, root: str) -> None:
        if self.observer is None or self._handler is None:
            return
        norm = os.path.normcase(os.path.normpath(root))
        if norm in self._watches:
            return
        if not os.path.isdir(root):
            logger.warning(f"Cannot schedule watchdog observer on {root}: not reachable yet. Periodic scan will retry.")
            return
        try:
            watch = self.observer.schedule(self._handler, root, recursive=True)
            self._watches[norm] = watch
            logger.info(f"Watchdog Observer scheduled on: {root}")
        except Exception as e:
            logger.error(f"Failed to schedule watchdog observer on {root}: {str(e)}")

    def _run_observer(self) -> None:
        self._handler = LogWatcherHandler()
        self.observer = Observer()
        for root in self._get_active_roots():
            self._schedule_watch(root)
        self.observer.start()

        # Periodic full re-scan safety net: filesystem change events aren't always
        # delivered reliably across bind/network mounts, so this guarantees files
        # are eventually caught even if an individual on_modified/on_created event
        # was dropped. Byte-offset tracking makes repeated scans of unchanged
        # files a no-op, so this is safe to run indefinitely. It also retries
        # scheduling watches on roots (e.g. network shares) that were unreachable
        # at startup or briefly dropped.
        scan_interval = max(settings.LOG_SCAN_INTERVAL_SECONDS, 1)
        elapsed = 0
        try:
            while self.running:
                time.sleep(1)
                elapsed += 1
                if elapsed >= scan_interval:
                    elapsed = 0
                    try:
                        self.scan_all_roots()
                        for root in self._get_active_roots():
                            self._schedule_watch(root)
                    except Exception as e:
                        logger.error(f"Error during periodic log directory scan: {str(e)}")
        except Exception as e:
            logger.error(f"Error in Watchdog Observer loop: {str(e)}")
        finally:
            self.observer.stop()
            self.observer.join()
            logger.info("Watchdog Observer stopped")

    def start(self) -> None:
        if self.running:
            return

        # 1. Catch up on historical modifications
        self.scan_all_roots()

        # 2. Start watchdog observer in background thread
        self.running = True
        self.thread = Thread(target=self._run_observer, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
            self.thread = None

    def add_root(self, path: str) -> None:
        """
        Hot-adds a newly registered monitored root: runs an immediate catch-up
        scan and, if the observer is running, schedules a live watch on it.
        """
        try:
            self._scan_root(path)
        except Exception as e:
            logger.error(f"Error during initial scan of new root {path}: {str(e)}")

        if self.running and self.observer is not None:
            self._schedule_watch(path)

    def remove_root(self, path: str) -> None:
        """
        Stops watching a root removed via the API. Never touches previously
        ingested LogFile/Log rows or the source filesystem itself.
        """
        norm = os.path.normcase(os.path.normpath(path))
        watch = self._watches.pop(norm, None)
        if watch is not None and self.observer is not None:
            try:
                self.observer.unschedule(watch)
                logger.info(f"Watchdog Observer unscheduled from: {path}")
            except Exception as e:
                logger.error(f"Error unscheduling watch on {path}: {str(e)}")

# Global service instance
log_watcher_service = LogWatcherService()
