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
    
    # CORS Origins (allow all or configure specific)
    BACKEND_CORS_ORIGINS: List[str] = ["*"]

    # Gemini Configuration
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_EMBEDDING_MODEL: str = "models/text-embedding-004"

    # Qdrant Configuration
    QDRANT_PATH: str = "qdrant_data"

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
