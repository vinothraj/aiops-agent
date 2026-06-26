from sqlalchemy import Column, Integer, String, Text, DateTime, BigInteger, Float, ForeignKey, func, Boolean
from sqlalchemy.orm import relationship
from app.database.session import Base

class LogFile(Base):
    __tablename__ = "log_files"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    file_name = Column(String(255), nullable=False)
    file_path = Column(String(1024), nullable=False, unique=True, index=True)
    service_name = Column(String(100), nullable=False)
    last_processed_position = Column(BigInteger, default=0, nullable=False)
    last_processed_time = Column(DateTime, nullable=True)
    status = Column(String(50), default="new", nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

class Log(Base):
    __tablename__ = "logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    service_name = Column(String(100), nullable=False, index=True)
    log_level = Column(String(50), nullable=False, index=True)
    message = Column(Text, nullable=False)
    stacktrace = Column(Text, nullable=True)
    file_name = Column(String(255), nullable=False)
    file_path = Column(String(1024), nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)

class LogAnalysis(Base):
    __tablename__ = "log_analyses"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    log_id = Column(Integer, ForeignKey("logs.id", ondelete="CASCADE"), nullable=False, index=True)
    root_cause = Column(Text, nullable=False)
    root_cause_category = Column(String(100), nullable=False)
    severity = Column(String(50), nullable=False)
    business_impact = Column(Text, nullable=True)
    technical_impact = Column(Text, nullable=True)
    confidence_score = Column(Float, nullable=False)
    recommendation = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    # Relationships
    log = relationship("Log", backref="analyses")
    patterns = relationship("AnalysisPattern", back_populates="analysis", cascade="all, delete-orphan")
    dependencies = relationship("AnalysisDependency", back_populates="analysis", cascade="all, delete-orphan")
    services = relationship("AnalysisService", back_populates="analysis", cascade="all, delete-orphan")

class AnalysisPattern(Base):
    __tablename__ = "analysis_patterns"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    analysis_id = Column(Integer, ForeignKey("log_analyses.id", ondelete="CASCADE"), nullable=False, index=True)
    pattern = Column(String(255), nullable=False)

    analysis = relationship("LogAnalysis", back_populates="patterns")

class AnalysisDependency(Base):
    __tablename__ = "analysis_dependencies"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    analysis_id = Column(Integer, ForeignKey("log_analyses.id", ondelete="CASCADE"), nullable=False, index=True)
    dependency = Column(String(255), nullable=False)

    analysis = relationship("LogAnalysis", back_populates="dependencies")

class AnalysisService(Base):
    __tablename__ = "analysis_services"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    analysis_id = Column(Integer, ForeignKey("log_analyses.id", ondelete="CASCADE"), nullable=False, index=True)
    service_name = Column(String(255), nullable=False)

    analysis = relationship("LogAnalysis", back_populates="services")

# ─── Phase 4: RAG Knowledge Models ─────────────────────────────────────────

class KnowledgeDocument(Base):
    """Generic table to store knowledge base text (Runbooks, Incidents, RCAs)."""
    __tablename__ = "knowledge_documents"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    doc_type = Column(String(50), nullable=False) # e.g. 'RUNBOOK', 'INCIDENT', 'RCA'
    source_id = Column(String(100), nullable=True) # e.g. Issue #120
    qdrant_point_id = Column(String(36), nullable=False, index=True) # UUID mapped to Qdrant
    created_at = Column(DateTime, default=func.now(), nullable=False)

class IncidentHistory(Base):
    """Structured history of past resolved incidents."""
    __tablename__ = "incident_history"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    incident_number = Column(String(100), nullable=False, unique=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    resolution = Column(Text, nullable=False)
    service_name = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)

class Runbook(Base):
    """Known fixes and troubleshooting guides."""
    __tablename__ = "runbooks"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    error_pattern = Column(String(255), nullable=False)
    resolution_steps = Column(Text, nullable=False)
    service_name = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)

# ─── Phase 5: Incident Decision & Triage ───────────────────────────────────

class IncidentDecision(Base):
    """AI-generated triage decisions for log incidents."""
    __tablename__ = "incident_decisions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    log_id = Column(Integer, ForeignKey("logs.id", ondelete="CASCADE"), nullable=False, index=True)
    analysis_id = Column(Integer, ForeignKey("log_analyses.id", ondelete="SET NULL"), nullable=True, index=True)

    # Scoring (0.0 – 1.0)
    risk_score = Column(Float, nullable=False, default=0.0)
    business_impact_score = Column(Float, nullable=False, default=0.0)
    technical_impact_score = Column(Float, nullable=False, default=0.0)
    frequency_score = Column(Float, nullable=False, default=0.0)

    # Decision
    priority = Column(String(10), nullable=False)           # P1, P2, P3, P4
    recommended_action = Column(String(50), nullable=False) # IGNORE, MONITOR, INVESTIGATE, CREATE_INCIDENT, IMMEDIATE_ESCALATION
    rationale = Column(Text, nullable=False)

    # Context
    affected_services = Column(Text, nullable=True)         # JSON array string
    similar_incident_count = Column(Integer, default=0)

    # Integration (future GitLab)
    gitlab_issue_id = Column(String(100), nullable=True)
    status = Column(String(50), default="OPEN", nullable=False)  # OPEN, ACKNOWLEDGED, RESOLVED

    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    log = relationship("Log", backref="decisions")
    analysis = relationship("LogAnalysis", backref="decisions")

# ─── Phase 6: GitLab Integration ───────────────────────────────────────────

class GitlabIssue(Base):
    """Tracks incidents that have been synced to GitLab."""
    __tablename__ = "gitlab_issues"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    incident_decision_id = Column(Integer, ForeignKey("incident_decisions.id", ondelete="CASCADE"), nullable=False, index=True)
    gitlab_issue_id = Column(Integer, nullable=False, unique=True, index=True)
    gitlab_issue_iid = Column(Integer, nullable=False)
    web_url = Column(String(1024), nullable=False)
    title = Column(String(512), nullable=False)
    state = Column(String(50), nullable=False)  # opened, closed
    assignee = Column(String(255), nullable=True)
    labels = Column(Text, nullable=True)  # JSON array of strings

    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    decision = relationship("IncidentDecision", backref="gitlab_issue")
    # Relationship to activities with proper cascade on the "one" side
    activities = relationship("IssueActivity", back_populates="issue", cascade="all, delete-orphan")

class IssueActivity(Base):
    """Tracks activity on GitLab issues."""
    __tablename__ = "issue_activity"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    gitlab_issue_id = Column(Integer, ForeignKey("gitlab_issues.id", ondelete="CASCADE"), nullable=False, index=True)
    action_type = Column(String(100), nullable=False)  # status_change, comment, assigned
    description = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=func.now(), nullable=False)

    # Relationship back to GitlabIssue without cascade (handled on the "one" side)
    issue = relationship("GitlabIssue", back_populates="activities")

# ─── Phase 7: Collaboration & Notifications ─────────────────────────────────

class Notification(Base):
    """Notification history and delivery tracking."""
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    incident_decision_id = Column(Integer, ForeignKey("incident_decisions.id", ondelete="SET NULL"), nullable=True, index=True)
    channel = Column(String(50), nullable=False) # 'teams', 'email'
    recipient_destination = Column(String(512), nullable=False) # Email address or Teams webhook URL
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    status = Column(String(50), default="PENDING", nullable=False) # PENDING, SENT, FAILED
    retry_count = Column(Integer, default=0, nullable=False)
    error_message = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    decision = relationship("IncidentDecision", backref="notifications")

class NotificationRecipient(Base):
    """Dynamic routing configurations mapped to incident root cause categories."""
    __tablename__ = "notification_recipients"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    category = Column(String(100), nullable=False, index=True) # e.g. 'DATABASE', 'NETWORK', 'APPLICATION_BUG', 'DEFAULT'
    channel = Column(String(50), nullable=False) # 'email', 'teams'
    destination = Column(String(512), nullable=False) # email address or webhook URL
    recipient_name = Column(String(255), nullable=False) # e.g. 'DBA Team', 'NetOps Webhook'
    is_active = Column(Boolean, default=True, nullable=False)

class NotificationTemplate(Base):
    """Templates for different notification events and channels."""
    __tablename__ = "notification_templates"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    template_name = Column(String(100), nullable=False, unique=True, index=True) # e.g. 'p1_teams', 'p1_email', 'daily_digest', 'weekly_insights'
    channel = Column(String(50), nullable=False) # 'email', 'teams'
    subject_template = Column(String(255), nullable=True)
    body_template = Column(Text, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)

