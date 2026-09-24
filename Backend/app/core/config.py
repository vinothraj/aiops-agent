import os
from typing import List, Union, Optional
from pydantic import AnyHttpUrl, validator
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "AIOps Platform"
    API_V1_STR: str = "/api"
    
    # Database Configuration
    # Fallback to postgresql://postgres:postgres@db:5432/aiops inside docker compose, or localhost for local run
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/aiops"

    # Monitored Logs Directory
    # Default is C:/Logs on Windows, but let's allow env configuration
    MONITORED_LOGS_DIR: str = "C:/Logs"

    # Regex matching a folder name that identifies a single deployment instance/host
    # rather than a service (e.g. instance01, node-3, host_4, prod0353m1..m5).
    # Override via env if your naming convention differs.
    INSTANCE_FOLDER_PATTERN: str = r'^(instance|node|host|pod|replica)[-_]?\d+$|^prod\d+m\d+$'

    # How often (seconds) to do a full re-scan of the monitored directory in addition
    # to the real-time watchdog observer. Needed because filesystem change events
    # aren't always delivered reliably across bind/network mounts (e.g. Docker
    # Desktop on Windows), so a periodic catch-up scan guarantees nothing is missed.
    LOG_SCAN_INTERVAL_SECONDS: int = 30

    # A log file is only ingested if it was modified within this many hours.
    # Kept generous by default: per-file byte-offset tracking already prevents
    # reprocessing/duplication, so this filter only exists to skip genuinely
    # ancient one-off archive dumps on first boot, not to gate normal ingestion.
    LOG_FILE_MAX_AGE_HOURS: int = 720

    # CORS Origins (allow all or configure specific)
    BACKEND_CORS_ORIGINS: List[str] = ["*"]

    # Gemini Configuration
    #GEMINI_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_EMBEDDING_MODEL: str = "models/text-embedding-004"

    # Claude Configuration
    CLAUDE_API_KEY: Optional[str] = None
    CLAUDE_MODEL: str = "claude-sonnet-4"

    # Qdrant Configuration
    QDRANT_PATH: str = "qdrant_data"

    # PII / Sensitive Data Masking
    # When true, customer/order/account/site/user identifiers and email
    # addresses embedded in log messages are redacted before any text is
    # sent to an external AI provider (Claude, Gemini) or used to generate
    # a Gemini embedding. Does not affect what's stored in Postgres/Qdrant.
    MASK_SENSITIVE_DATA_IN_AI_REQUESTS: bool = True

    # Incident Grouping / Known-Issue Matching
    # Cosine similarity (0-1) above which a new error is treated as a confirmed
    # recurrence of an existing incident group rather than a fresh analysis.
    INCIDENT_MATCH_SIMILARITY_THRESHOLD: float = 0.93

    # GitLab Configuration
    GITLAB_URL: Optional[str] = None
    GITLAB_PRIVATE_TOKEN: Optional[str] = None
    GITLAB_PROJECT_ID: Optional[str] = None

    # SMTP Configuration
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 1025
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM: str = "noreply@aiops.enterprise"

    # Microsoft Teams Configuration
    TEAMS_WEBHOOK_URL: Optional[str] = None

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
