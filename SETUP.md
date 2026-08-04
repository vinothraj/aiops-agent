# Setup Guide (No Docker)

Steps to install and run the AIOps Platform on a fresh Windows machine without Docker. For the Docker Compose path instead, see `README.md`.

## 1. Prerequisites

Install these first:

| Tool | Version | Notes |
|---|---|---|
| Python | 3.12 | Matches `Backend/Dockerfile`'s base image. Confirm with `python --version`. |
| Node.js | 20+ (ships with npm 10.x) | Frontend pins `"packageManager": "npm@10.8.2"` in `Frontend/package.json`. |
| PostgreSQL | 16 | Or any recent version. Needed unless you use the SQLite dev fallback (see step 3). |
| Git | any recent version | To clone the repo. |
| Ollama | latest | **Optional** — only needed if you want to run the local/free AI provider instead of Claude or Gemini. |

## 2. Clone the repository

```bash
git clone https://github.com/vinothraj/aiops-agent.git
cd aiops-agent
```

(A second remote, `aiops-agent-v2`, also exists — use whichever your team designates as primary. Everything below is identical either way.)

## 3. Database

Create a PostgreSQL database and user matching the app's default connection string (`postgresql://postgres:postgres@localhost:5432/aiops`), or use your own credentials and reflect them in `Backend/.env` in step 4.

```sql
-- via psql, as a superuser
CREATE DATABASE aiops;
-- if you don't already have a "postgres" role with password "postgres",
-- either create one or use your own credentials in DATABASE_URL instead.
```

**SQLite alternative (simpler, dev-only):** set `DATABASE_URL=sqlite:///aiops_dev.db` in `Backend/.env` instead of installing Postgres. Note the app behaves slightly differently in this mode — the log watcher does a one-time synchronous catch-up scan at startup instead of running continuously in the background, so it won't pick up new log lines live without a restart.

## 4. Backend setup

From the repo root:

```bash
cd Backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Create `Backend/.env` (this file is git-ignored and does not exist in a fresh clone — you must create it). Minimum to get the app running:

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/aiops
MONITORED_LOGS_DIR=C:/Logs
```

Add whichever of these you need — none are required just to start the app, but each unlocks a specific feature:

```env
# AI provider for RCA / Ask AI (Claude is the default provider if none is set)
CLAUDE_API_KEY=
GEMINI_API_KEY=
# Ollama needs no key -- see step 7 -- just set the provider to "ollama" in Settings once it's running

# GitLab issue integration
GITLAB_URL=
GITLAB_PRIVATE_TOKEN=
GITLAB_PROJECT_ID=

# Outgoing notification email (defaults to localhost:1025, a dev mail-catcher
# convention like MailHog/Mailpit -- notifications just won't send if nothing
# is listening there, nothing else depends on it)
SMTP_HOST=localhost
SMTP_PORT=1025

# Microsoft Teams incoming webhook for notifications
TEAMS_WEBHOOK_URL=
```

See `Backend/app/core/config.py` for the complete list of supported settings and their defaults.

Create the database schema:

```bash
alembic upgrade head
```

Start the backend:

```bash
uvicorn app.main:app --reload --port 8000
```

Confirm it's up: open `http://localhost:8000/health` — should return `{"status": "healthy", ...}`.

## 5. Frontend setup

From the repo root, in a separate terminal:

```bash
cd Frontend
npm install --legacy-peer-deps
npm start
```

Open `http://localhost:4200`.

The frontend talks to the backend at `http://localhost:8000/api` by default (hardcoded in `Frontend/src/app/services/api.service.ts`) — only change that if your backend runs on a different host/port.

## 6. First-time configuration (via the UI)

Once both are running, open `http://localhost:4200/settings` and configure:

- **RCA Codebase Diagnostics** — local path to the codebase you want "Diagnose in Codebase" / "Ask AI" to search against (optional).
- **AI Provider** — pick Claude, Gemini, or Ollama, and enter the API key directly here if you didn't set it in `.env` (a key entered here is stored in the database and takes precedence over `.env`).
- **Log Retention** — optional; enable if you want old, unanalyzed logs auto-pruned to keep DB size and CPU load down on smaller machines.

Then add at least one monitored log directory from the Log Sources page (or set `MONITORED_LOGS_DIR` in `.env` to point at an existing folder of logs).

## 7. Optional: local AI via Ollama

Only needed if you want a free, fully local model instead of Claude/Gemini.

1. Install Ollama: https://ollama.com/download
2. Pull the app's default model:
   ```bash
   ollama pull llama3.1:8b
   ```
   (An 8B-class model needs roughly 5-8GB of free RAM to run. Larger models like `qwen3.6` may fail to load on machines with less RAM — pick a size that fits your hardware.)
3. Make sure Ollama is running (`ollama serve`, or it may already run as a background service after install).
4. In Settings → AI Provider, select "Local Llama via Ollama" and confirm the base URL (`http://localhost:11434` by default) and model name match.

## 8. Verifying everything works

- Backend health check: `http://localhost:8000/health`
- Frontend loads: `http://localhost:4200`
- Drop a sample log file into your monitored directory and confirm it shows up in the Log Explorer within a few seconds.
- Trigger an RCA analysis on an error log and confirm it returns a populated result (not empty fields — if it comes back empty, the configured AI provider likely isn't reachable or its API key is missing).

## Troubleshooting

- **`alembic upgrade head` fails to connect** — check `DATABASE_URL` in `Backend/.env` and that PostgreSQL is actually running and accepting connections on that port.
- **Frontend shows no data / network errors in console** — confirm the backend is running on port 8000 and check `Frontend/src/app/services/api.service.ts`'s `baseUrl` matches.
- **RCA/Ask AI returns an error** — check Settings → AI Provider shows the expected provider "configured" (green), and that the API key is valid.
- **Ollama times out** — the model may be too large for available RAM; try a smaller model.
