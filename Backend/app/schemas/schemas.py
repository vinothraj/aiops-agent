from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Dict

class LogFileBase(BaseModel):
    file_name: str
    file_path: str
    service_name: str
    instance_id: Optional[str] = None
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

class MonitoredSourceRootCreate(BaseModel):
    path: str
    label: Optional[str] = None

class MonitoredSourceRootResponse(BaseModel):
    id: int
    path: str
    label: Optional[str] = None
    is_active: bool
    status: str
    last_checked_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True

class LogBase(BaseModel):
    timestamp: datetime
    service_name: str
    instance_id: Optional[str] = None
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
    has_rca: bool = False
    rca_severity: Optional[str] = None
    rca_root_cause_category: Optional[str] = None
    # Whether a GitLab issue already exists for this log's incident group
    # (any occurrence, not just this exact log) -- if so, gitlab_issue_url
    # points at it and can_create_gitlab_issue is false to prevent duplicate
    # filing for what's really one recurring problem.
    can_create_gitlab_issue: bool = False
    gitlab_issue_url: Optional[str] = None

    class Config:
        from_attributes = True

class LogStatsSummary(BaseModel):
    total_logs: int
    error_logs: int
    warning_logs: int
    services: int
    instances: int

class LogReprocessRequest(BaseModel):
    file_path: Optional[str] = None
    file_id: Optional[int] = None

class LogServiceBreakdown(BaseModel):
    service_name: str
    count: int
    error_count: int

class LogTimeSeriesPoint(BaseModel):
    bucket: datetime
    count: int
    error_count: int

class AppSettingResponse(BaseModel):
    key: str
    value: Optional[str] = None
    updated_at: Optional[datetime] = None

class TargetCodebasePathUpdate(BaseModel):
    path: str

class AiProviderSettingsResponse(BaseModel):
    provider: str
    ollama_base_url: str
    ollama_model: str
    claude_configured: bool = False
    gemini_configured: bool = False
    auto_rca_enabled: bool = False

class AiProviderSettingsUpdate(BaseModel):
    provider: str
    ollama_base_url: Optional[str] = None
    ollama_model: Optional[str] = None
    auto_rca_enabled: Optional[bool] = None
    # Write-only: never echoed back in AiProviderSettingsResponse. Omit to
    # leave the stored key untouched; send "" to explicitly clear it back to
    # falling through to the .env value.
    claude_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None

class LogRetentionSettingsResponse(BaseModel):
    enabled: bool
    retention_hours: int

class LogRetentionSettingsUpdate(BaseModel):
    enabled: bool

class GitlabSettingsResponse(BaseModel):
    url: str = ""
    project_id: str = ""
    configured: bool = False
    code_project: str = ""  # repository AI fixes are pushed to; "" = auto-detect
    detected_code_project: Optional[str] = None  # from the target codebase's origin remote

class GitlabSettingsUpdate(BaseModel):
    url: Optional[str] = None
    project_id: Optional[str] = None
    code_project: Optional[str] = None
    # Write-only: never echoed back in GitlabSettingsResponse. Omit to leave
    # the stored token untouched; send "" to explicitly clear it back to
    # falling through to the .env value.
    private_token: Optional[str] = None

class LogSummaryResponse(BaseModel):
    """Aggregated view of the currently filtered logs, for the Log Explorer's chart panel."""
    total_matched: int
    level_counts: Dict[str, int]
    top_services: List[LogServiceBreakdown]
    time_series: List[LogTimeSeriesPoint]
    bucket_granularity: str
    errors_total: int
    errors_with_rca: int

# ─── RCA Agent Schemas ────────────────────────────────────────────────────────

class RCARequest(BaseModel):
    """Input payload for triggering a root cause analysis."""
    service_name: Optional[str] = None
    environment: Optional[str] = "production"
    version: Optional[str] = None
    deployment_timestamp: Optional[datetime] = None
    force_new: bool = False

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
    incident_group_id: Optional[int] = None
    is_recurring: bool = False
    match_score: Optional[float] = None
    ai_provider: Optional[str] = None
    ai_model: Optional[str] = None

    class Config:
        from_attributes = True

# ─── Phase 8: Incident Grouping Schemas ───────────────────────────────────────

class IncidentGroupResponse(BaseModel):
    """Summary of a recurring-incident cluster, for the enterprise grouping view."""
    id: int
    title: str
    root_cause_category: str
    representative_analysis_id: Optional[int] = None
    occurrence_count: int
    status: str
    first_seen_at: datetime
    last_seen_at: datetime

    class Config:
        from_attributes = True

class IncidentGroupDetailResponse(IncidentGroupResponse):
    """Group summary plus the representative fix and every recorded occurrence."""
    representative_analysis: Optional[LogAnalysisResponse] = None
    occurrences: List[LogAnalysisResponse] = []

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

class GitlabIssueCreateFromLogRequest(BaseModel):
    log_id: int

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

# ─── Codebase Diagnostics (RCA -> source code) ────────────────────────────────

class CodebaseCandidateFile(BaseModel):
    file_path: str
    match_reason: str
    matched_line: Optional[int] = None
    snippet: Optional[str] = None

class DiagnoseCodebaseResponse(BaseModel):
    log_id: int
    target_path: str
    stack_frames_parsed: List[str] = []
    candidates: List[CodebaseCandidateFile] = []
    truncated: bool = False

class AskAiRequest(BaseModel):
    candidate_file_paths: Optional[List[str]] = None

class CodeFixSuggestion(BaseModel):
    file_path: str
    relative_path: str
    rationale: Optional[str] = None
    original: str
    replacement: str
    applied: bool = False  # False when `original` wasn't found in the current file
    start_line: Optional[int] = None
    diff: Optional[str] = None  # unified diff against the current file

class AskAiResponse(BaseModel):
    log_id: int
    provider: str
    model: str
    suggestion: str  # explanation (or raw AI text if it didn't return structured fixes)
    files_used: List[str] = []
    fixes: List[CodeFixSuggestion] = []
    combined_patch: Optional[str] = None  # all applicable diffs, `git apply`-able from the codebase root

class GitlabFixEdit(BaseModel):
    file_path: str  # local path the fix was diffed against
    relative_path: str
    original: str
    replacement: str
    start_line: Optional[int] = None

class GitlabFixDefaultsResponse(BaseModel):
    configured: bool
    project: Optional[str] = None  # code repository, e.g. "CAP/Endor"
    base_branch: Optional[str] = None  # target codebase checkout's current branch
    branch_name: str
    commit_message: str
    linked_issue_url: Optional[str] = None

class GitlabFixPushRequest(BaseModel):
    fixes: List[GitlabFixEdit]
    base_branch: str
    branch_name: str
    commit_message: str
    create_merge_request: bool = True
    explanation: Optional[str] = None  # AI analysis, used as the MR description

class GitlabFixPushResponse(BaseModel):
    project: str
    base_branch: str
    branch: str
    branch_url: str
    commit_sha: str
    commit_url: str
    merge_request_url: Optional[str] = None
    files: List[str] = []
    diff: str = ""  # what was actually committed, against the base branch


# ─── Remediation: fix sessions ──────────────────────────────────────────────

class FixSessionEventResponse(BaseModel):
    id: int
    status: str
    message: Optional[str] = None
    source: str
    created_at: datetime

    class Config:
        from_attributes = True

class FixSessionResponse(BaseModel):
    id: int
    log_id: int
    incident_decision_id: Optional[int] = None
    trigger: str
    executor: str
    priority: Optional[str] = None
    status: str
    gitlab_project: Optional[str] = None
    base_branch: Optional[str] = None
    branch: Optional[str] = None
    commit_sha: Optional[str] = None
    merge_request_url: Optional[str] = None
    summary: Optional[str] = None
    root_cause_confirmed: Optional[str] = None
    files_changed: List[str] = []
    tests_summary: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    # Denormalized for list views
    service_name: Optional[str] = None
    log_level: Optional[str] = None
    log_message: Optional[str] = None
    events: List[FixSessionEventResponse] = []

class FixSessionCreateRequest(BaseModel):
    log_id: int
    ai_hypothesis: Optional[str] = None  # "Ask AI" suggestion text, if the user already ran it
    base_branch: Optional[str] = None

class FixSessionBriefResponse(BaseModel):
    session: FixSessionResponse
    brief: str  # Markdown prompt for Claude Code; embeds a fresh callback token

class FixSessionEventCreate(BaseModel):
    status: Optional[str] = None  # agent status or "note"
    message: Optional[str] = None
    summary: Optional[str] = None
    root_cause_confirmed: Optional[str] = None
    branch: Optional[str] = None
    commit_sha: Optional[str] = None
    merge_request_url: Optional[str] = None
    files_changed: Optional[List[str]] = None
    tests_summary: Optional[str] = None

class FixSessionCancelRequest(BaseModel):
    reason: Optional[str] = None

class AutoFixSettingsResponse(BaseModel):
    enabled: bool
    min_priority: str  # P1..P4: queue sessions for incidents at or above this priority
    base_branch: str = ""  # default base branch for fixes ("" = target codebase's current branch)

class AutoFixSettingsUpdate(BaseModel):
    enabled: Optional[bool] = None
    min_priority: Optional[str] = None
    base_branch: Optional[str] = None
