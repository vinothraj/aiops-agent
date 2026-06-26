# Enterprise AIOps Platform - Phase 1 Foundation

This project sets up the foundational pipeline for an Enterprise AI-Powered AIOps Platform. It establishes directory monitoring, incremental log file ingestion, log parsing with multiline stack trace support, query APIs, and a dashboard frontend.

---

## Folder Structure

```text
aiops-platform/
│
├── Backend/
│   ├── app/
│   │   ├── api/                    # API Routers and Route endpoints
│   │   │   ├── endpoints/
│   │   │   │   ├── logs.py         # Log Explorer, search, and reprocessing APIs
│   │   │   │   ├── stats.py        # Log aggregation metrics
│   │   │   │   └── sources.py      # Monitored file source status
│   │   │   └── router.py           # Main routing module
│   │   │
│   │   ├── core/                   # Global configuration and logger setups
│   │   │   ├── config.py
│   │   │   └── logging.py
│   │   │
│   │   ├── database/               # Database connection and session management
│   │   │   └── session.py
│   │   │
│   │   ├── models/                 # SQLAlchemy DB Model declarations
│   │   │   └── models.py
│   │   │
│   │   ├── schemas/                # Pydantic schema validation structures
│   │   │   └── schemas.py
│   │   │
│   │   ├── repositories/           # Repository Pattern implementations
│   │   │   └── repositories.py
│   │   │
│   │   ├── services/               # Core business logic handlers
│   │   │   ├── parser.py           # Regex log parser with multiline trace support
│   │   │   └── watcher.py          # Watchdog service for incremental file scan
│   │   │
│   │   └── main.py                 # FastAPI initialization and startup lifecycle
│   │
│   ├── alembic/                    # Alembic Database migration revisions
│   ├── alembic.ini                 # Migration settings
│   ├── Dockerfile                  # Container instructions for Backend run
│   ├── requirements.txt            # Python dependencies
│   └── test_parser.py              # Parser validation verification script
│
├── Frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── components/
│   │   │   │   ├── dashboard/      # Observability dashboard containing SVG chart
│   │   │   │   ├── log-viewer/     # Log Explorer with query filters & stack trace detail
│   │   │   │   └── log-sources/    # Monitored file paths and reprocessing console
│   │   │   ├── services/
│   │   │   │   └── api.service.ts  # Api HTTP client service
│   │   │   ├── app.ts              # Root standalone component
│   │   │   ├── app.html            # Main UI shell template
│   │   │   ├── app.css             # Root styles
│   │   │   └── app.routes.ts       # Route configurations
│   │   ├── index.html              # Main HTML file
│   │   └── styles.css              # Custom Dark-Mode CSS design system
│   ├── Dockerfile                  # Production Nginx host instructions
│   └── nginx.conf                  # Nginx configuration for Client-side SPA routing
│
├── Logs/                           # Monitored folder (mount path)
│   └── ecommerce-site.log          # Target log file
│
├── docker-compose.yml              # Combined orchestrator configurations
└── README.md                       # Documentation and startup guide
```

---

## Setup & Running Instructions

### Option 1: Running with Docker Compose (Recommended)

To start the database, backend services, and host the frontend altogether, run:

1. Make sure Docker Desktop is active on your machine.
2. In the project root folder, execute:
   ```bash
   docker compose up --build
   ```
3. Docker will automatically:
   - Start a PostgreSQL container (`db`).
   - Run the Backend container, trigger database migrations using Alembic, and listen on port `8000`.
   - Start the Frontend container and host the Angular build on port `80`.
4. Open your browser and navigate to:
   - **Frontend Console**: [http://localhost](http://localhost)
   - **FastAPI OpenAPI Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
5. To test real-time monitoring inside Docker:
   - Simply append a new log line or drop a `.log` file inside your local `./Logs` folder. It will be scanned in real-time.

---

### Option 2: Running Locally for Development

#### 1. Setup Backend
1. Create a Python virtual environment:
   ```bash
   cd Backend
   python -m venv venv
   .\venv\Scripts\activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the validation test script:
   ```bash
   python test_parser.py
   ```
4. Configure database settings inside `Backend/.env` to point to your local PostgreSQL, or run database migrations:
   ```bash
   alembic upgrade head
   ```
5. Launch FastAPI development server:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

#### 2. Setup Frontend
1. Change into Frontend folder:
   ```bash
   cd Frontend
   ```
2. Install npm dependencies:
   ```bash
   npm install --legacy-peer-deps
   ```
3. Launch Angular dev server:
   ```bash
   npm run dev
   ```
4. Open the UI at [http://localhost:4200](http://localhost:4200).

---

## Ingestion & Parsing Mechanics
1. **Incremental Watcher**: On application boot, the platform does a recursive scan of `Logs/` directory and logs current byte offsets. Watchdog then starts monitoring files.
2. **Rotation Detection**: If a file size becomes smaller than `last_processed_position`, the watcher automatically resets offset to 0 and reads from start.
3. **Partial Line Handling**: If a write is ongoing and a line does not end with `\n`, the watcher truncates the read buffer and backs up the cursor offset to read the complete line during the next cycle.
4. **Multiline Stacktrace Grouping**: The parser joins any line not matching the timestamp pattern (e.g. stack traces, nested exceptions) to the message body of the previous log record.
