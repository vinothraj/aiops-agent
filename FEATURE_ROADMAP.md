# AIOps Platform – Feature Roadmap (Phase 8 onward)

This document captures where the Enterprise AIOps Platform stands today, the gaps against the
original product vision (`AI Agent for AI Ops.docx`), and the phased plan for upcoming work.
Each phase lists its objectives, the data/API changes it introduces, how it plugs into the
existing code, and what "done" means.

---

## 1. Current State (Phases 1–7 and follow-up work)

End-to-end pipeline in production today:

```
Log files → Watcher / Parser → DB → Auto-RCA (Claude / Gemini / Ollama + Qdrant RAG context)
          → Triage (risk score → P1–P4 → action) → GitLab issue → Teams / Email notifications
```

| Phase | Module | Status |
|---|---|---|
| 1 | Log monitoring, parsing, dashboard, multiple monitored source roots | Done |
| 2 | AI Root Cause Analysis (RCA) agent | Done – now multi-provider (Claude, Gemini, Ollama) |
| 4 | Incident Knowledge Intelligence (RAG on Qdrant, self-learning) | Done |
| 5 | Incident Decision & Triage Engine, Incident Queue | Done |
| 6 | GitLab Incident Management Agent (create, sync, per-log issue) | Done |
| 7 | Notification & Collaboration Agent (Teams, Email, digests, timeline) | Done |
| — | Incident grouping, codebase diagnostics, Settings UI, log retention, PII masking before AI calls | Done |

---

## 2. Gaps Identified in the Code

| # | Gap | Where | Impact |
|---|---|---|---|
| 1 | No scheduler – daily digest, weekly insights, notification retry and GitLab sync only run when an API is called | `services/notification/notification_agent.py`, `api/endpoints/gitlab.py` | Reports and retries never happen automatically |
| 2 | Weak triage scoring – business/technical impact scores are derived from the *length* of the AI's text (`min(len(text)/500, 1)`) | `services/triage/triage_engine.py` | P1–P4 priority and escalation decisions are unreliable |
| 3 | Knowledge base pollution – every RCA is ingested into Qdrant, including wrong ones; resolutions from closed GitLab issues are not captured; no user feedback on RCAs | `services/rca/rca_agent.py`, `services/rag/rag_service.py` | RAG quality degrades over time |
| 4 | No authentication / roles (vision Module 12) – Settings, including stored API keys, are open to anyone who can reach the API | `api/endpoints/settings.py`, `app_settings` table | Security risk; blocks approval workflow |
| 5 | No human approval workflow (Module 11) and no LangGraph orchestration (Module 10) | — | Critical incidents are escalated without review |
| 6 | No automated test suite – only ad hoc scripts (`test_parser.py`, `test_rag.py`) | `Backend/` | Regressions go unnoticed |
| 7 | Architecture documentation is out of date (still describes Gemini 1.5 only and SQLite) | `AIOPS_PROJECT_DOCUMENTATION.md` | Onboarding confusion |

---

## 3. Integration Principles

Every new phase plugs into the platform through a clear seam instead of rewriting existing agents:

- **New service package** under `Backend/app/services/<feature>/`.
- **New endpoint router** registered in `Backend/app/api/router.py`.
- **New state or columns** on `incident_decisions` (the hub table linking RCA, GitLab and notifications) plus an Alembic migration.
- **New Angular component** under `Frontend/src/app/components/<feature>/`, wired into `app.routes.ts` and `api.service.ts`.
- **Existing agents stay callable as plain functions**, so Phase 12 (LangGraph) can wrap them as graph nodes without a rewrite.

---

## 4. Phases

Phases are ordered by dependency – each builds on the one before it.

### Phase 8 – Stabilize & Harden *(start here)*

The scoring and scheduler fixes change how every later phase behaves, so they come first.

**Objectives**
1. Add test coverage for the PII masking already in place (`services/rca/pii_masking.py`, commit `c9e392b`).
2. Add a pytest suite covering the parser (multiline stack traces, partial lines, rotation), triage engine, incident matcher and PII masking.
3. Add a scheduler (APScheduler, started in the FastAPI lifespan) for:
   - Daily operational digest
   - Weekly reliability insights
   - Failed-notification retry
   - GitLab issue status sync
4. Replace length-based triage scoring with:
   - The AI-reported severity
   - A category-based impact score (e.g. `DATABASE`, `PAYMENT`, `NETWORK` weighted by business criticality, configurable in Settings)
   - Frequency and confidence as today
5. Refresh `AIOPS_PROJECT_DOCUMENTATION.md` (multi-provider AI, PostgreSQL, new modules).

**Data / API**
- `app_settings`: scheduler cron expressions, category impact weights.
- `GET /api/settings/scheduler`, `PUT /api/settings/scheduler`.

**Done when**
- `pytest` runs green locally and in CI.
- Digests and retries fire on schedule without manual API calls.
- Two errors with the same category and severity get the same priority regardless of AI text length.

---

### Phase 9 – Administration, Authentication & RBAC (Module 12)

The approval workflow in Phase 10 needs to know *who* approved, so identity comes first.

**Objectives**
1. User management with roles: **Admin**, **DevOps**, **Viewer**.
2. JWT login and a FastAPI dependency that protects endpoints by role.
3. Lock down Settings and log-source management to Admin.
4. Encrypt secrets (AI API keys, GitLab token, SMTP password, Teams webhook) at rest in `app_settings`.
5. Audit log of configuration changes and incident actions.
6. Angular login page, route guards and a Users admin screen.

**Data / API**
- Tables: `users`, `roles`, `audit_log`.
- `POST /api/auth/login`, `GET /api/auth/me`, `GET|POST|PUT|DELETE /api/users`, `GET /api/audit`.

**Done when**
- Unauthenticated requests are rejected (except health and login).
- Viewers cannot change settings or trigger GitLab/notifications.
- Secrets never appear in plain text in the DB or in API responses.

---

### Phase 10 – Human Approval Workflow (Module 11)

**Objectives**
1. P1 and P2 decisions enter a `PENDING_APPROVAL` state before GitLab issue creation or notifications.
2. Approve / reject (with comment) from the Incident Queue, restricted to DevOps and Admin.
3. Optional auto-approve timeout per priority (configurable).
4. Approval events appear in the incident timeline and audit log.
5. Notify approvers when an incident is waiting.

**Data / API**
- `incident_decisions`: `approval_status`, `approved_by`, `approved_at`, `approval_comment`.
- `POST /api/incidents/{id}/approve`, `POST /api/incidents/{id}/reject`, `GET /api/incidents?approval_status=PENDING_APPROVAL`.

**Done when**
- No P1/P2 incident reaches GitLab or Teams/Email without an approval record (or an explicit auto-approve).

---

### Phase 11 – Closed-Loop Learning & Knowledge Quality

**Objectives**
1. Only ingest RCAs into Qdrant after human verification (approved or rated helpful).
2. When a GitLab issue closes, capture the resolution (closing comment / linked MR) into `incident_history` and the knowledge base.
3. 👍 / 👎 feedback with an optional correction on each RCA.
4. Runbook upload (Markdown / PDF) with chunking and re-embedding.
5. A small evaluation set to measure retrieval quality (hit rate / MRR) and track it over time.

**Data / API**
- Tables: `rca_feedback`; `knowledge_documents` gets `verified`, `source`, `chunk_index`.
- `POST /api/rca/{id}/feedback`, `POST /api/knowledge/upload`, `GET /api/knowledge/eval`.

**Done when**
- Unverified RCAs are not retrievable as RAG context.
- Closing a GitLab issue produces a searchable resolution document.

---

### Phase 12 – LangGraph Multi-Agent Orchestration (Module 10)

**Objectives**
1. Wrap existing services as graph nodes:
   `Supervisor → Log Analysis → Knowledge → RCA → Decision → (Approval) → GitLab → Notify`.
2. Shared, persisted agent state per incident (checkpointer on PostgreSQL).
3. The Phase 10 approval step becomes a LangGraph interrupt that resumes on approve/reject.
4. Replace the ad hoc chain in `services/rca/auto_trigger.py` with graph invocation.
5. Graph run visualization in the incident timeline.

**Rule:** wrap, don't rewrite – existing agents remain the node implementations.

**Done when**
- An ingested ERROR flows through the graph end to end, pauses for approval on P1/P2, and resumes correctly after a backend restart.

---

### Phase 13 – Integrations Expansion

**Objectives**
1. `LogSource` interface with implementations for local files (existing), Docker, Kubernetes and AWS CloudWatch; later Azure Monitor and Splunk.
2. `IssueTracker` interface (GitLab existing) with Jira and ServiceNow adapters.
3. `Notifier` interface (Teams / Email existing) with a Slack adapter.
4. MCP server exposing platform tools (search logs, get RCA, list incidents, create issue) to external AI assistants.

**Done when**
- A new source, tracker or notifier can be added by implementing one interface and enabling it in Settings.

---

### Phase 14 – AI Observability & Guarded Remediation

**Objectives**
1. Track token usage, cost, latency and error rate per AI provider and model.
2. Track RCA accuracy from Phase 11 feedback, per provider.
3. Runbook-driven remediation actions (e.g. restart service, scale pool) executed only after approval, with dry-run and rollback.
4. AI usage dashboard in the UI.

**Done when**
- Provider cost and accuracy are visible in the dashboard.
- No remediation runs without an approval record and an audit entry.

---

## 5. Deferred

- **OpenSearch** – PostgreSQL with log retention handles the current volume. Revisit only if log search latency or volume demands it.
- **Voice-based incident assistant** – after Phase 13.

---

## 6. Summary

| Phase | Theme | Depends on | Vision module |
|---|---|---|---|
| 8 | Stabilize & harden | — | — |
| 9 | Auth, roles, admin | 8 | 12 |
| 10 | Human approval | 9 | 11 |
| 11 | Closed-loop learning | 10 | 8, 9 |
| 12 | LangGraph orchestration | 10, 11 | 10 |
| 13 | Integrations | 12 | Future enhancements |
| 14 | AI observability & remediation | 11, 12 | Future enhancements |
