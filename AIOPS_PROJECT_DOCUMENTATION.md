# Enterprise AIOps Platform: Multi-Agent Architecture and Workflow Documentation

This document provides a comprehensive overview of the **Enterprise AI-Powered AIOps and Incident Management Platform**. It details the architectural design, core technologies, database schemas, and the step-by-step workflow of the AI agents that collaborate to automate production issue monitoring, root cause analysis, retrieval-augmented resolution recommendation, issue tracking, and dynamic alert notifications.

---

## 1. Project Overview & Vision

Modern software operations produce massive volumes of logs. Identifying critical system errors, performing root cause analyses (RCA), researching historical resolutions, and notifying the right engineering teams is traditionally a manual, slow, and error-prone process.

The **Enterprise AIOps Platform** automates these processes by orchestrating a pipeline of specialized AI services and software agents. The platform monitors directories, ingests logs incrementally, performs multiline stack-trace grouping, triggers automated AI-driven root cause analysis using Google Gemini, searches for historical incidents using a local vector database (RAG), decides priority and triages incidents, logs issues to GitLab, and dispatches dynamic, category-routed alerts to email or Microsoft Teams.

---

## 2. Technology Stack

| Component | Technology | Description / Role |
| :--- | :--- | :--- |
| **Backend Framework** | FastAPI (Python 3.12+) | High-performance asynchronous API endpoints for UI communication and agent routing. |
| **Log Monitoring** | Watchdog | Cross-platform filesystem event listener tracking files in the `./Logs` folder. |
| **Database ORM** | SQLAlchemy & Alembic | Python SQL toolkit and migration manager mapping state to the relational database. |
| **Primary Database** | SQLite (Dev) / PostgreSQL (Prod) | Stores parsed logs, generated RCAs, triage decisions, GitLab issues, and notification queues. |
| **AI Reasoning Model** | Google Gemini (1.5 Flash) | Computes root cause, business/technical impact, recommends immediate fixes, and generates digests. |
| **AI Vector Embeddings** | Google Gemini (`text-embedding-004`) | Converts log messages, incident records, and runbooks into 768-dimensional vector representations. |
| **Vector Database (RAG)** | Qdrant | Local-directory embedded vector store matching current error messages against historical resolutions. |
| **Issue Management** | python-gitlab | Automates ticket generation, status tracking, and assignment workflows in GitLab. |
| **Collaboration & Alerts** | SMTP Server & MS Teams Webhooks | Delivers Adaptive Cards and HTML alerts dynamically to specific teams. |
| **Frontend Dashboard** | Angular & Vanilla CSS | Sleek glassmorphic dark-mode interface exposing logs, RCA history, triage decisions, and GitLab tracking. |

---

## 3. High-Level Agentic Architecture

The system transitions through a series of stages from log detection to notification. Rather than a monolithic program, it is built as a pipeline of modular processors and AI agents.

```mermaid
flowchart TD
    subgraph Monitored Directory
        LogFile[Logs/ecommerce-site.log]
    end

    Watcher[Log Watcher Service - Watchdog] -->|File Modified / Created| Parser[Log Parser]
    LogFile -->|Byte Offset Scan| Watcher

    Parser -->|Parse timestamp, service, level| DB_Logs[(SQLite/Postgres Logs)]
    Parser -->|Identify ERROR or FATAL| RCA[AI Root Cause Analysis Agent]

    subgraph RAG & Knowledge Base
        Qdrant[(Qdrant Vector DB)]
        RAG[RAG Service]
        RAG -->|Similarity Search| Qdrant
        RCA -->|Query Log Message| RAG
        RAG -->|Top 5 Context & Runbooks| RCA
    end

    RCA -->|Gather +/- Log Context| Context[Log Context Window]
    Context --> RCA
    RCA -->|Build Prompt & Call Gemini| Gemini[Google Gemini 1.5 Flash]
    Gemini -->|Returns Structured JSON| RCA
    RCA -->|Save Analysis| DB_Analyses[(Log Analyses DB)]
    RCA -->|Auto-Ingest Report| Qdrant

    DB_Analyses --> Triage[Incident Decision & Triage Engine]
    Triage -->|Compute Risk Score| ActionRouter{Triage Action?}

    ActionRouter -->|IGNORE / MONITOR| Ignore[No external action]
    ActionRouter -->|INVESTIGATE| LogOnly[Update Status in UI]
    ActionRouter -->|CREATE_INCIDENT / IMMEDIATE_ESCALATION| Gitlab[GitLab Agent]
    ActionRouter -->|All Priority Alerts| Notify[Notification Agent]

    subgraph Integrations
        Gitlab -->|Create Issue| GitlabRepo[GitLab Repository Issues]
        Gitlab -->|Save Issue ID & Sync| DB_Gitlab[(GitLab Issues DB)]
        Notify -->|Teams Webhook| Teams[MS Teams Channels]
        Notify -->|SMTP / MailHog| Email[Email Alerts]
        Notify -->|Save Alert Status| DB_Notifications[(Notification DB)]
    end
```

---

## 4. End-to-End Workflow & Execution Trace

When a service appends an error to a monitored log file, the agents collaborate in the following order:

```mermaid
sequenceDiagram
    autonumber
    participant Watcher as Log Watcher
    participant Parser as Log Parser
    participant DB as SQLite / Postgres DB
    participant RCA as RCA Agent
    participant RAG as RAG Service
    participant Gemini as Google Gemini
    participant Qdrant as Qdrant Vector DB
    participant Triage as Triage Engine
    participant GitLab as GitLab Agent
    participant Notify as Notification Agent

    Watcher->>Parser: New lines in log file
    Parser->>DB: Store parsed logs
    Note over Parser: Log level is ERROR or FATAL
    Parser->>RCA: Trigger Root Cause Analysis
    RCA->>DB: Fetch surrounding log context (+/- window)
    RCA->>RAG: Request similar historical issues
    RAG->>Qdrant: Semantic search (vector query)
    Qdrant-->>RAG: Top 5 runbooks / resolutions
    RAG-->>RCA: Inject context documents
    RCA->>Gemini: Send prompt (Context + Logs + Runbooks)
    Gemini-->>RCA: Return Structured JSON RCA
    RCA->>DB: Persist RCA Report (RCA, patterns, dependencies)
    RCA->>RAG: Ingest new RCA report for future queries
    RAG->>Qdrant: Upsert new analysis vector
    RCA->>Triage: Trigger Auto-Triage
    Triage->>DB: Calculate & persist Incident Decision (Risk, Priority, Action)
    alt Action is CREATE_INCIDENT or IMMEDIATE_ESCALATION
        Triage->>GitLab: Request Issue Creation
        GitLab->>DB: Check if issue already exists
        GitLab->>GitLab: Create GitLab Issue (API)
        GitLab->>DB: Save GitLab Issue Metadata
    end
    Triage->>Notify: Dispatch Notifications
    Notify->>DB: Fetch Recipient Routing (by category)
    alt Priority is P1
        Notify->>Gemini: Generate Executive Summary
        Gemini-->>Notify: Executive text
    end
    Notify->>Notify: Format Alert Message
    Notify->>Teams: Post Webhook card (Teams channel)
    Notify->>Email: Send SMTP email
    Notify->>DB: Persist notification records (Status: SENT/FAILED)
```

---

## 5. Core Architectural Components & Code Walkthrough

### 5.1. Log Watcher & Ingestion Pipeline
* **File Location**: [watcher.py](file:///c:/Vino/Personal/AI%20Enterprise%20Project/Backend/app/services/watcher.py) & [parser.py](file:///c:/Vino/Personal/AI%20Enterprise%20Project/Backend/app/services/parser.py)
* **Mechanics**:
  1. **Incremental Monitoring**: Keeps a persistent record of the byte offsets of all files in the database (`log_files` table).
  2. **File Rotation Detection**: If a log file is rotated (resulting in a file size smaller than the `last_processed_position`), the watcher automatically resets its pointer to `0` and reads from the start.
  3. **Partial Line Handling**: If a log entry is written mid-cycle and lacks a trailing newline character (`\n`), the watcher truncates the buffer, backs up the database cursor offset, and reads the completed line in the next cycle.
  4. **Multiline Stacktrace Parser**: Recognizes standard timestamps using regular expressions. If a line does not begin with a timestamp (e.g., standard stacktrace lines), the parser automatically groups it into the `stacktrace` column of the preceding log entry.

### 5.2. Root Cause Analysis (RCA) Agent
* **File Location**: [rca_agent.py](file:///c:/Vino/Personal/AI%20Enterprise%20Project/Backend/app/services/rca/rca_agent.py)
* **Mechanics**:
  1. **Context Window Extraction**: Queries the SQL database for up to 50 logs preceding the failure and 20 logs following it to analyze cascading failures across services.
  2. **Runbook & Historical Query**: Queries the RAG knowledge base using the current error message.
  3. **Structured Generation**: Builds a dynamic system prompt directing Gemini to return a structured JSON response matching the Pydantic schema: `RCAStructuredResponse`.
  4. **Self-Learning Loop**: Auto-ingests every successfully generated RCA back into Qdrant, allowing the AI to learn from its own resolutions.

### 5.3. Incident Knowledge Intelligence (RAG Engine)
* **File Location**: [rag_service.py](file:///c:/Vino/Personal/AI%20Enterprise%20Project/Backend/app/services/rag/rag_service.py)
* **Mechanics**:
  1. **Dual Storage**: Stores raw text metadata in the SQL `knowledge_documents` table and high-dimensional vectors in the local Qdrant collection (`knowledge_base`).
  2. **Gemini Embeddings**: Integrates Gemini's `text-embedding-004` to generate vectors representing runbooks and resolved incidents.
  3. **Similarity Search**: Performs a cosine similarity vector search on incoming errors to inject resolutions into the active prompt context.

### 5.4. Incident Decision & Triage Engine
* **File Location**: [triage_engine.py](file:///c:/Vino/Personal/AI%20Enterprise%20Project/Backend/app/services/triage/triage_engine.py)
* **Mechanics**:
  1. **Score Metrics**: Evaluates:
     - **Business Impact** (Heuristic length of the Gemini business impact assessment text)
     - **Technical Impact** (Heuristic length of the technical impact assessment text)
     - **Frequency** (Percentage of failures for that service in the last 24 hours, capped at 10)
     - **RCA Confidence** (Derived directly from Gemini's confidence assessment score)
  2. **Risk Formula**: Calculates a weighted score:
     $$\text{Risk} = (0.3 \times \text{Business}) + (0.3 \times \text{Technical}) + (0.2 \times \text{Frequency}) + (0.2 \times \text{Confidence})$$
  3. **Priority & Action Mapping**:
     - $\text{Risk} \ge 0.8 \rightarrow$ **P1** $\rightarrow$ `IMMEDIATE_ESCALATION`
     - $\text{Risk} \ge 0.6 \rightarrow$ **P2** $\rightarrow$ `CREATE_INCIDENT`
     - $\text{Risk} \ge 0.4 \rightarrow$ **P3** $\rightarrow$ `INVESTIGATE`
     - $\text{Risk} < 0.4 \rightarrow$ **P4** $\rightarrow$ `IGNORE`

### 5.5. GitLab Incident Agent
* **File Location**: [gitlab_agent.py](file:///c:/Vino/Personal/AI%20Enterprise%20Project/Backend/app/services/gitlab/gitlab_agent.py)
* **Mechanics**:
  1. **Ticket Generation**: Automatically triggers for triage actions requiring escalation.
  2. **Rich Markdown Formatting**: Compiles the final issue description with sections for Triage Rationale, Root Cause, Business/Technical Impact, and Recommended Actions.
  3. **Bi-directional Sync**: Routinely syncs issue state (opened vs. closed) and assignment updates from GitLab back to the database.

### 5.6. Collaboration & Notification Agent
* **File Location**: [notification_agent.py](file:///c:/Vino/Personal/AI%20Enterprise%20Project/Backend/app/services/notification/notification_agent.py)
* **Mechanics**:
  1. **Dynamic Category Routing**: Reads the root cause category resolved by the RCA agent (e.g. `DATABASE`, `NETWORK`) and routes alerts to the configured team (e.g. database issues are routed directly to the DBA team).
  2. **MS Teams Adaptive Cards**: Transmits detailed Markdown cards to Teams webhook endpoints.
  3. **Email (SMTP)**: Compiles and sends clean HTML emails (using MailHog for development).
  4. **AI Summaries**: Uses Gemini to generate executive summaries for P1 outages, daily operational digests, and weekly insights reports.
  5. **Retry Queue**: Implements an automatic retry loop for failed notifications, capped at 3 attempts.

---

## 6. Database Schema Design

```
                     ┌───────────────────┐
                     │     log_files     │ (Monitored paths & offset tracker)
                     └─────────┬─────────┘
                               │ 1
                               │
                               │ *
                     ┌─────────▼─────────┐
                     │       logs        │ (Core system log messages)
                     └─────────┬─────────┘
                               │ 1
                               │
                               │ *
                     ┌─────────▼─────────┐
                     │   log_analyses    │ (Gemini-generated root causes)
                     └────┬────┬────┬────┘
        ┌─────────────────┘    │    └─────────────────┐
        │ *                    │ *                    │ *
┌───────▼───────────┐  ┌───────▼───────────┐  ┌───────▼───────────┐
│ analysis_patterns │  │ analysis_deps     │  │ analysis_services │
└───────────────────┘  └───────────────────┘  └───────────────────┘
                               ▲
                               │ 0..1
                               │
                               │ 1
                     ┌─────────┴─────────┐
                     │incident_decisions │ (Triage score, priority, action)
                     └─────────┬─────────┘
        ┌──────────────────────┘──────────────────────┐
        │ 1                                           │ 1
        │                                             │
        │ 0..1                                        │ *
┌───────▼───────────┐                         ┌───────▼───────────┐
│   gitlab_issues   │                         │   notifications   │ (Alert records)
└───────┬───────────┘                         └───────────────────┘
        │ 1
        │
        │ *
┌───────▼───────────┐
│  issue_activity   │ (GitLab sync log)
└───────────────────┘
```

### 6.1. System Core Tables
* **`log_files`**: Tracks monitored files, offsets, and scanning status.
* **`logs`**: Stores raw parsed log entries (service name, timestamp, log level, message, and stack trace).
* **`log_analyses`**: Stores root cause analysis records, impact assessments, recommendations, and confidence scores.
* **`analysis_patterns` / `analysis_dependencies` / `analysis_services`**: Child tables mapping details detected during Gemini analysis.

### 6.2. Knowledge Base & RAG Tables
* **`knowledge_documents`**: Links raw runbook texts to their Qdrant point IDs.
* **`incident_history`**: Holds resolution records.
* **`runbooks`**: Contains predefined error patterns and resolutions.

### 6.3. Triage & Notification Queue Tables
* **`incident_decisions`**: Stores triage results (risk scores, priority status, recommended actions).
* **`gitlab_issues`**: Maps incident decisions to GitLab tickets.
* **`issue_activity`**: Tracks updates from GitLab sync runs.
* **`notifications`**: Queue containing message templates, destinations, and delivery statuses.
* **`notification_recipients`**: Configuration mapping system categories to Teams channels and email addresses.
* **`notification_templates`**: Predefined text skeletons for notifications.

---

## 7. Operational & Setup Guide

### 7.1. Setup Environment Configuration
Create a `.env` file inside the `Backend/` folder with the following variables:
```bash
# General Configurations
PROJECT_NAME="Enterprise AIOps Platform"
API_V1_STR="/api/v1"
DATABASE_URL="sqlite:///./aiops.db"

# Google Gemini Credentials
GEMINI_API_KEY="AIzaSyYourGeminiApiKeyHere"
GEMINI_MODEL="gemini-1.5-flash"
GEMINI_EMBEDDING_MODEL="models/text-embedding-004"

# Qdrant Vector DB Settings
QDRANT_PATH="./qdrant_data"

# GitLab Repository Configurations
GITLAB_URL="https://gitlab.biw-services.com"
GITLAB_PRIVATE_TOKEN="glpat-YourPrivateTokenHere"
GITLAB_PROJECT_ID="YourProjectID"

# Notification Configurations
SMTP_HOST="localhost"
SMTP_PORT=1025
SMTP_FROM="aiops@company.internal"
SMTP_USERNAME=""
SMTP_PASSWORD=""
TEAMS_WEBHOOK_URL="https://outlook.office.com/webhook/placeholder-teams"
```

### 7.2. Run Locally (Development Setup)

#### 1. Start the Backend API
1. Navigate to the `Backend/` folder:
   ```bash
   cd Backend
   ```
2. Set up and activate a Python virtual environment:
   ```bash
   python -m venv venv
   .\venv\Scripts\activate
   ```
3. Install the dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run migrations:
   ```bash
   alembic upgrade head
   ```
5. Run the server:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```
   *The FastAPI interactive documentation is available at [http://localhost:8000/docs](http://localhost:8000/docs)*.

#### 2. Start the Frontend Dashboard
1. Navigate to the `Frontend/` folder:
   ```bash
   cd Frontend
   ```
2. Install dependencies:
   ```bash
   npm install --legacy-peer-deps
   ```
3. Start the application:
   ```bash
   npm run dev
   ```
   *The Angular application is available at [http://localhost:4200](http://localhost:4200)*.

---

## 8. Summary of Agent Operations

The multi-agent platform implements a structured workflow:
1. **The Log Watcher Agent** continuously tracks files for new entries.
2. **The Parser Agent** extracts structured logs and handles multiline stack traces.
3. **The RCA Agent** gathers surrounding context and retrieves relevant historical incidents from the **RAG Engine**.
4. **The Gemini Reasoning Core** produces structured root cause reports.
5. **The Incident Triage Engine** calculates risk scores and decides priority levels.
6. **The GitLab Agent** creates issues and tracks ticket updates.
7. **The Notification Agent** generates AI operational digests and emails specific teams based on root cause categories.
