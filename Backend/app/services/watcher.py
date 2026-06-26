import os
import time
import logging
import re
from datetime import datetime, timedelta
from threading import Thread
from typing import Optional

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from app.core.config import settings
from app.database.session import SessionLocal
from app.repositories.repositories import log_file_repo, log_repo
from app.schemas.schemas import LogFileCreate, LogFileUpdate
from app.services.parser import LogParser

logger = logging.getLogger(__name__)
parser = LogParser()

def get_service_name(file_path: str, monitored_dir: str) -> str:
    """
    Determines service name based on directory structure.
    If Logs/ProductService/application.log -> ProductService
    If Logs/application.log -> application
    """
    norm_path = os.path.normpath(file_path)
    norm_monitored = os.path.normpath(monitored_dir)
    
    rel_path = os.path.relpath(norm_path, norm_monitored)
    parts = rel_path.split(os.sep)
    
    if len(parts) > 1:
        return parts[0]
    else:
        base = os.path.basename(file_path)
        name, _ = os.path.splitext(base)
        return name

class LogFileProcessor:
    @staticmethod
    def should_process_file(file_path: str) -> bool:
        """
        Determines whether the file should be processed based on:
        1. Extension (.log or .txt)
        2. Modification time (within last 24 hours)
        3. Excludes historical/rotated files containing date patterns, 
           except if the date corresponds to today or yesterday.
        """
        if not os.path.isfile(file_path):
            return False

        _, ext = os.path.splitext(file_path)
        if ext.lower() not in [".log", ".txt"]:
            return False

        # Filter by modification time (within last 24 hours)
        try:
            mtime = os.path.getmtime(file_path)
            if time.time() - mtime > 86400:  # 24 hours in seconds
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
            service_name = get_service_name(file_path, settings.MONITORED_LOGS_DIR)

            # 1. Fetch or create log file record
            db_log_file = log_file_repo.get_by_path(db, file_path)
            if not db_log_file:
                db_log_file = log_file_repo.create(
                    db,
                    LogFileCreate(
                        file_name=file_name,
                        file_path=file_path,
                        service_name=service_name,
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
                parsed_logs = parser.parse_lines(lines_to_process, file_name, file_path)
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

    def scan_directory(self) -> None:
        """
        Recursively scans the monitored directory to catch up on files.
        """
        logger.info(f"Scanning monitored directory: {settings.MONITORED_LOGS_DIR}")
        if not os.path.exists(settings.MONITORED_LOGS_DIR):
            logger.warning(f"Directory {settings.MONITORED_LOGS_DIR} does not exist. Creating it.")
            os.makedirs(settings.MONITORED_LOGS_DIR, exist_ok=True)
            return

        for root, _, files in os.walk(settings.MONITORED_LOGS_DIR):
            for file in files:
                file_path = os.path.join(root, file)
                LogFileProcessor.process_file(file_path)

    def _run_observer(self) -> None:
        event_handler = LogWatcherHandler()
        self.observer = Observer()
        self.observer.schedule(event_handler, settings.MONITORED_LOGS_DIR, recursive=True)
        self.observer.start()
        logger.info(f"Watchdog Observer started on: {settings.MONITORED_LOGS_DIR}")
        
        try:
            while self.running:
                time.sleep(1)
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
        self.scan_directory()

        # 2. Start watchdog observer in background thread
        self.running = True
        self.thread = Thread(target=self._run_observer, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
            self.thread = None

# Global service instance
log_watcher_service = LogWatcherService()
