from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List

class LogFileBase(BaseModel):
    file_name: str
    file_path: str
    service_name: str
    last_processed_position: int = 0
    status: str = "new"

class LogFileCreate(LogFileBase):
    pass

class LogFileUpdate(BaseModel):
    last_processed_position: Optional[int] = None
    last_processed_time: Optional[datetime] = None
    status: Optional[str] = None

class LogFileResponse(LogFileBase):
    id: int
    last_processed_time: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class LogBase(BaseModel):
    timestamp: datetime
    service_name: str
    log_level: str
    message: str
    stacktrace: Optional[str] = None
    file_name: str
    file_path: str

class LogCreate(LogBase):
    pass

class LogResponse(LogBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True

class LogStatsSummary(BaseModel):
    total_logs: int
    error_logs: int
    warning_logs: int
    services: int

class LogReprocessRequest(BaseModel):
    file_path: Optional[str] = None
    file_id: Optional[int] = None

# ─── RCA Agent Schemas ────────────────────────────────────────────────────────

class RCARequest(BaseModel):
    """Input payload for triggering a root cause analysis."""
    service_name: Optional[str] = None
    environment: Optional[str] = "production"
    version: Optional[str] = None
    deployment_timestamp: Optional[datetime] = None

class RCAStructuredResponse(BaseModel):
    """Structured JSON output expected from the Gemini RCA agent."""
    incident_type: str = ""
    root_cause_category: str = ""
    root_cause: str = ""
    severity: str = ""
    business_impact: str = ""
    technical_impact: str = ""
    affected_services: List[str] = []
    affected_dependencies: List[str] = []
    pattern_detected: List[str] = []
    deployment_related: bool = False
    recommended_action: str = ""
    immediate_fix: str = ""
    short_term_fix: str = ""
    long_term_fix: str = ""
    incident_recommendation: str = ""
    confidence_score: float = 0.0
    severity_confidence: float = 0.0
    recommendation_confidence: float = 0.0
    summary: str = ""

class AnalysisPatternResponse(BaseModel):
    id: int
    pattern: str
    class Config:
        from_attributes = True

class AnalysisDependencyResponse(BaseModel):
    id: int
    dependency: str
    class Config:
        from_attributes = True

class AnalysisServiceResponse(BaseModel):
    id: int
    service_name: str
    class Config:
        from_attributes = True

class LogAnalysisResponse(BaseModel):
    """Output schema for a stored RCA result."""
    id: int
    log_id: int
    root_cause: str
    root_cause_category: str
    severity: str
    business_impact: Optional[str] = None
    technical_impact: Optional[str] = None
    confidence_score: float
    recommendation: Optional[str] = None
    summary: Optional[str] = None
    created_at: datetime
    patterns: List[AnalysisPatternResponse] = []
    dependencies: List[AnalysisDependencyResponse] = []
    services: List[AnalysisServiceResponse] = []
    rca_detail: Optional[RCAStructuredResponse] = None

    class Config:
        from_attributes = True

# ─── Phase 5: Incident Triage Schemas ─────────────────────────────────────────

class TriageRequest(BaseModel):
    """Input payload for triggering incident triage."""
    log_id: int
    service_name: Optional[str] = None
    environment: Optional[str] = "production"

class TriageScores(BaseModel):
    """Breakdown of scoring dimensions."""
    risk_score: float = 0.0
    business_impact_score: float = 0.0
    technical_impact_score: float = 0.0
    frequency_score: float = 0.0

class TriageDecisionResponse(BaseModel):
    """Full triage decision output — consumable by frontend and future GitLab agent."""
    id: int
    log_id: int
    analysis_id: Optional[int] = None
    risk_score: float
    business_impact_score: float
    technical_impact_score: float
    frequency_score: float
    priority: str
    recommended_action: str
    rationale: str
    affected_services: Optional[str] = None
    similar_incident_count: int = 0
    gitlab_issue_id: Optional[str] = None
    status: str = "OPEN"
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# ─── Phase 6: GitLab Schemas ──────────────────────────────────────────────────

class GitlabIssueCreateRequest(BaseModel):
    incident_decision_id: int

class IssueActivityResponse(BaseModel):
    id: int
    gitlab_issue_id: int
    action_type: str
    description: str
    timestamp: datetime

    class Config:
        from_attributes = True

class GitlabIssueResponse(BaseModel):
    id: int
    incident_decision_id: int
    gitlab_issue_id: int
    gitlab_issue_iid: int
    web_url: str
    title: str
    state: str
    assignee: Optional[str] = None
    labels: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    activities: List[IssueActivityResponse] = []

    class Config:
        from_attributes = True

# ─── Phase 7: Notification Schemas ───────────────────────────────────────────

class NotificationSendRequest(BaseModel):
    incident_decision_id: int
    channels: Optional[List[str]] = None

class NotificationTestRequest(BaseModel):
    channel: str
    destination: str

class NotificationResponse(BaseModel):
    id: int
    incident_decision_id: Optional[int] = None
    channel: str
    recipient_destination: str
    title: str
    message: str
    status: str
    retry_count: int
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class NotificationRecipientCreate(BaseModel):
    category: str
    channel: str
    destination: str
    recipient_name: str
    is_active: bool = True

class NotificationRecipientResponse(BaseModel):
    id: int
    category: str
    channel: str
    destination: str
    recipient_name: str
    is_active: bool

    class Config:
        from_attributes = True

class NotificationTemplateResponse(BaseModel):
    id: int
    template_name: str
    channel: str
    subject_template: Optional[str] = None
    body_template: str
    created_at: datetime

    class Config:
        from_attributes = True

class TimelineEventResponse(BaseModel):
    timestamp: datetime
    event_type: str  # e.g., 'LOG', 'RCA', 'TRIAGE', 'GITLAB', 'NOTIFICATION'
    title: str
    description: str
    status: Optional[str] = None
    meta: Optional[dict] = None

