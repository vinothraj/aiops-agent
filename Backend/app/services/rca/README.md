# Enterprise AI Root Cause Analysis Agent

## Overview

The RCA Agent is an enterprise-grade AI-powered Site Reliability Engineer (SRE) that analyzes production failures, identifies probable root causes, assesses impact, and suggests remediation actions using Google Gemini.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   RCA Agent                         │
│                                                     │
│  1. Context Gatherer  →  Fetches surrounding logs   │
│  2. Prompt Builder    →  Constructs rich prompt     │
│  3. Gemini Caller     →  Sends to AI for analysis   │
│  4. Result Persister  →  Saves to database          │
│                                                     │
└─────────────────────────────────────────────────────┘
```

## Agent Responsibilities

For every ERROR or FATAL log, the agent performs:

| # | Responsibility | Description |
|---|---------------|-------------|
| 1 | Log Analysis | Understand the failure event |
| 2 | Root Cause Analysis | Identify the probable root cause |
| 3 | Severity Classification | Assign P1/P2/P3/P4 with justification |
| 4 | Business Impact Assessment | Impact in business language |
| 5 | Service Impact Assessment | Identify affected services |
| 6 | Dependency Impact Detection | Identify affected dependencies |
| 7 | Pattern Detection | Detect error patterns (bursts, leaks, storms) |
| 8 | Resolution Recommendation | Immediate, short-term, and long-term fixes |
| 9 | Incident Recommendation | CREATE_INCIDENT / MONITOR / IGNORE / REQUIRES_HUMAN_REVIEW |
| 10 | Confidence Scoring | Score for root cause, severity, and recommendation |

## API Endpoints

### `POST /api/rca/analyze/{log_id}`
Trigger a root cause analysis for a specific log entry.

**Request Body (optional):**
```json
{
  "service_name": "ecommerce-site",
  "environment": "production",
  "version": "2.1.3",
  "deployment_timestamp": "2024-01-15T10:30:00"
}
```

### `GET /api/rca/analysis/{log_id}`
Fetch the most recent analysis for a specific log entry.

### `GET /api/rca/analyses?skip=0&limit=50`
Fetch all historical analyses.

## Structured JSON Response

```json
{
  "incident_type": "Database Connection Failure",
  "root_cause_category": "DATABASE",
  "root_cause": "Connection pool exhaustion due to unclosed connections...",
  "severity": "P2",
  "business_impact": "Checkout unavailable for 15% of users...",
  "technical_impact": "PostgreSQL connection pool at 100% capacity...",
  "affected_services": ["Product Service", "Payment Service"],
  "affected_dependencies": ["PostgreSQL", "Redis"],
  "pattern_detected": ["Connection Leak Pattern", "Error Burst"],
  "deployment_related": false,
  "recommended_action": "Restart connection pool and investigate leak",
  "immediate_fix": "Restart exhausted connection pool",
  "short_term_fix": "Increase pool size to 50 connections",
  "long_term_fix": "Fix connection leak in ProductRepository.java",
  "incident_recommendation": "CREATE_INCIDENT",
  "confidence_score": 0.91,
  "severity_confidence": 0.95,
  "recommendation_confidence": 0.88,
  "summary": "Database connection pool exhaustion detected..."
}
```

## Root Cause Categories

| Category | Description |
|----------|-------------|
| DATABASE | Database-related failures |
| API_FAILURE | API call failures |
| AUTHENTICATION | Auth failures |
| AUTHORIZATION | Permission failures |
| NETWORK | Network connectivity issues |
| TIMEOUT | Request/connection timeouts |
| MEMORY | Memory-related issues |
| CPU | CPU exhaustion |
| DISK | Disk space/IO issues |
| CACHE | Cache failures |
| MESSAGE_QUEUE | Message queue issues |
| CONFIGURATION | Config errors |
| DEPENDENCY_FAILURE | Downstream dependency failures |
| THIRD_PARTY_FAILURE | External service failures |
| APPLICATION_BUG | Code-level bugs |
| DATA_INTEGRITY | Data corruption/consistency issues |
| UNKNOWN | Cannot determine root cause |

## Database Tables

- `log_analyses` - Core analysis records
- `analysis_patterns` - Detected patterns per analysis
- `analysis_dependencies` - Impacted dependencies per analysis
- `analysis_services` - Impacted services per analysis

## Configuration

Set in `Backend/.env`:
```
GEMINI_API_KEY=your_api_key_here
GEMINI_MODEL=gemini-1.5-flash
```

## Future Enhancements (Module 4+)

- **RAG Integration**: Store analyses in Qdrant for similar incident retrieval
- **Agent Tools**: Incident DB lookup, deployment history, GitLab integration
- **Multi-Agent**: Supervisor agent orchestrating RCA, Knowledge, Notification agents
