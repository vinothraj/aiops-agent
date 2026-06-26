import re
import os
from datetime import datetime
from typing import List, Optional
from app.schemas.schemas import LogCreate
import logging

logger = logging.getLogger(__name__)

# Pattern to match: YYYY-MM-DD HH:MM:SS[,.]SSS LEVEL ServiceName Message
# ServiceName must be a single alphanumeric/hyphen/underscore word to prevent capturing parts of message.
PATTERN_WITH_SERVICE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:[.,]\d+)?)\s+([A-Z]+)\s+([a-zA-Z0-9_\-]+)\s+(.*)$"
)

# Pattern to match: YYYY-MM-DD HH:MM:SS[,.]SSS LEVEL Message (fallback to file's service name)
PATTERN_WITHOUT_SERVICE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:[.,]\d+)?)\s+([A-Z]+)\s+(.*)$"
)

class LogParser:
    @staticmethod
    def parse_timestamp(ts_str: str) -> datetime:
        """
        Parses timestamps of formats YYYY-MM-DD HH:MM:SS,SSS or YYYY-MM-DD HH:MM:SS.
        """
        # Split at comma or dot to ignore milliseconds
        clean_ts = re.split(r'[.,]', ts_str)[0]
        try:
            return datetime.strptime(clean_ts, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return datetime.utcnow()

    def parse_line(self, line: str, default_service: str) -> Optional[dict]:
        """
        Tries to parse a single line with either the service-specific or fallback format.
        """
        # Try pattern with explicit service name first
        match = PATTERN_WITH_SERVICE.match(line)
        if match:
            timestamp_str, log_level, service_name, message = match.groups()
            return {
                "timestamp": self.parse_timestamp(timestamp_str),
                "log_level": log_level,
                "service_name": service_name,
                "message": message,
                "stacktrace": None
            }
        
        # Try fallback pattern without service name
        match = PATTERN_WITHOUT_SERVICE.match(line)
        if match:
            timestamp_str, log_level, message = match.groups()
            return {
                "timestamp": self.parse_timestamp(timestamp_str),
                "log_level": log_level,
                "service_name": default_service,
                "message": message,
                "stacktrace": None
            }
        
        return None

    def parse_lines(self, lines: List[str], file_name: str, file_path: str) -> List[LogCreate]:
        """
        Parses multiple lines, handling multiline stack traces.
        """
        parsed_logs: List[LogCreate] = []
        current_log: Optional[dict] = None
        
        # Derive default service name from the filename (e.g. ecommerce-site from ecommerce-site.log)
        base = os.path.basename(file_path)
        name, _ = os.path.splitext(base)
        default_service = name

        for raw_line in lines:
            line = raw_line.rstrip("\r\n")
            if not line:
                continue

            parsed_line = self.parse_line(line, default_service)
            if parsed_line:
                if current_log:
                    parsed_logs.append(LogCreate(**current_log, file_name=file_name, file_path=file_path))
                current_log = parsed_line
            else:
                if current_log:
                    if current_log["stacktrace"] is None:
                        current_log["stacktrace"] = line
                    else:
                        current_log["stacktrace"] += "\n" + line
                else:
                    logger.debug(f"Orphaned line skipped: {line}")

        if current_log:
            parsed_logs.append(LogCreate(**current_log, file_name=file_name, file_path=file_path))

        return parsed_logs
