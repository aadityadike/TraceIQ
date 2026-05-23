# Error Log Intelligence API — Design Spec
**Date:** 2026-05-24  
**Status:** Approved  
**Project root:** `/VS Code/TraceIQ/` (root = `error-log-intelligence/` in spec)

---

## What This Is

A production-ready backend API that accepts raw application logs, queues AI analysis asynchronously via Groq (LLaMA3), and returns structured insights: error clusters, root causes, severity ratings, and fix suggestions.

---

## Architecture

```
Client
  │
  ▼
FastAPI (port 8000) ──asyncpg──► PostgreSQL
  │                                   ▲
  ▼                                   │ psycopg2
Redis (broker) ──────────────► Celery Worker ──► Groq API (LLaMA3)
```

**Two async boundaries:**
1. HTTP → FastAPI → Redis: non-blocking task dispatch (202 immediately)
2. Redis → Celery Worker → Groq: background AI analysis (seconds to complete)

---

## Tech Stack

| Layer | Technology | Version |
|---|---|---|
| API Framework | FastAPI (async) | 0.111.0 |
| DB Driver (API) | asyncpg | 0.29.0 |
| DB Driver (Worker) | psycopg2-binary | 2.9.9 |
| ORM + Migrations | SQLAlchemy 2 + Alembic | 2.0.30 / 1.13.1 |
| Queue Broker | Redis | 7-alpine |
| Background Worker | Celery | 5.4.0 |
| AI | Groq API — llama3-8b-8192 | groq 0.9.0 |
| Validation | Pydantic v2 | 2.7.1 |
| Containerization | Docker Compose | v3.9 |
| Python | 3.11 | — |

---

## Project Structure

Built directly inside `/VS Code/TraceIQ/`:

```
TraceIQ/
├── docker-compose.yml
├── .env.example
├── .gitignore
├── README.md
│
├── api/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py                  # FastAPI app + lifespan (runs alembic upgrade head)
│   ├── config.py                # pydantic-settings BaseSettings
│   ├── database.py              # async SQLAlchemy engine + session factory
│   ├── models/
│   │   ├── __init__.py
│   │   └── log_job.py           # LogJob + ErrorPattern ORM models
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── log_job.py           # Pydantic v2 request/response schemas
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── logs.py              # /logs endpoints
│   │   └── patterns.py          # /patterns endpoint
│   └── services/
│       ├── __init__.py
│       └── analysis.py          # DB query logic (no AI here)
│
├── worker/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── celery_app.py            # Celery instance (broker=Redis)
│   └── tasks/
│       ├── __init__.py
│       └── analyze_logs.py      # Core AI task
│
└── alembic/
    ├── alembic.ini
    ├── env.py
    └── versions/
        └── 001_initial_schema.py
```

---

## Database Schema

### `log_jobs` table

| Column | Type | Notes |
|---|---|---|
| id | UUID | PK, default uuid4 |
| raw_log | TEXT | original submitted log |
| source | VARCHAR(100) | nullable, e.g. "payment-service" |
| status | VARCHAR(20) | enum: pending / processing / completed / failed |
| created_at | TIMESTAMPTZ | default now() |
| updated_at | TIMESTAMPTZ | updated on change |
| error_count | INTEGER | nullable, filled post-analysis |

Indexes: `status`, `source`

### `error_patterns` table

| Column | Type | Notes |
|---|---|---|
| id | UUID | PK, default uuid4 |
| log_job_id | UUID | FK → log_jobs.id (CASCADE DELETE) |
| error_type | VARCHAR(200) | e.g. "NullPointerException" |
| severity | VARCHAR(20) | enum: critical / high / medium / low |
| count | INTEGER | occurrences in this log |
| root_cause | TEXT | AI-generated |
| suggested_fix | TEXT | AI-generated |
| example_line | TEXT | one example log line |
| created_at | TIMESTAMPTZ | default now() |

---

## API Endpoints

### POST /api/v1/logs/ingest
- Validates body with Pydantic
- Saves LogJob with `status="pending"`
- Calls `analyze_logs.delay(str(job_id))`
- Returns **202** with job_id and poll URL

### GET /api/v1/logs/{job_id}
- Returns full job + patterns list
- **404** if not found
- Patterns array is empty while pending/processing

### GET /api/v1/logs
- Paginated list: `page`, `limit`, `status`, `source` filters
- Returns total count + items

### GET /api/v1/patterns
- Aggregated across all jobs, grouped by `error_type`
- Filters: `severity`, `source`, `limit`
- SQL: GROUP BY error_type, SUM(count), COUNT(DISTINCT log_job_id), MAX(created_at)

### DELETE /api/v1/logs/{job_id}
- Cascade deletes patterns via FK
- Returns **204 No Content**

### GET /health
- SELECT 1 → DB check
- Redis PING
- Celery inspect active workers
- Returns status of all three

---

## Celery Worker Task — `analyze_logs(job_id)`

1. Fetch LogJob from DB
2. Set `status = "processing"`
3. Build Groq prompt (system + user message with raw_log + source)
4. Call `groq.chat.completions.create(model="llama3-8b-8192", ...)`
5. Strip markdown fencing (` ```json ... ``` `) from response
6. Parse JSON array — retry up to 2 times on parse failure
7. Bulk-insert `ErrorPattern` rows
8. Set `status = "completed"`, `error_count = len(patterns)`
9. On any exception: set `status = "failed"`, log error

**Groq system prompt:** Expert SRE analyzing logs, returns JSON array only, no markdown.

**Driver note:** Worker uses sync SQLAlchemy (`psycopg2`) — separate `DATABASE_URL` with `postgresql+psycopg2://` scheme.

---

## Configuration

All secrets via `.env` / environment variables, loaded by `pydantic-settings`:

```
GROQ_API_KEY
DATABASE_URL          # asyncpg for API
REDIS_URL
```

Worker's `DATABASE_URL` uses `postgresql+psycopg2://` (set in docker-compose environment).

---

## Startup Behavior

`main.py` uses a FastAPI `lifespan` context manager that runs:
```python
subprocess.run(["alembic", "upgrade", "head"], check=True)
```
on startup. No manual migration step needed after `docker-compose up`.

---

## Error Handling

| Scenario | Behavior |
|---|---|
| job_id not found | 404 HTTPException |
| Pydantic validation fail | 422 (FastAPI auto) |
| Groq parse fail (2 retries) | job status → "failed" |
| Unhandled worker exception | try/except → status "failed" + logging.error |
| Service unavailable (DB/Redis) | 500 from health endpoint |

---

## Docker Compose

Four services: `api` (port 8000), `worker`, `db` (postgres:15-alpine, port 5432), `redis` (redis:7-alpine, port 6379).

Health checks on `db` and `redis` — `api` and `worker` depend on both being healthy before starting.

`api` uses `asyncpg` DATABASE_URL. `worker` uses `psycopg2` DATABASE_URL. Both mount their source as volumes for hot-reload during development.

---

## Key Implementation Notes

1. **Two requirements.txt files** — `api/requirements.txt` includes `asyncpg`, `fastapi`, `uvicorn`, `alembic`; `worker/requirements.txt` includes `celery`, `groq`, `psycopg2-binary`, no FastAPI.
2. **UUID handling** — SQLAlchemy models use `uuid.uuid4` as default; Pydantic schemas serialize as strings.
3. **Patterns aggregation** — `GET /api/v1/patterns` uses GROUP BY `error_type` with `SUM(count)`, `COUNT(DISTINCT log_job_id)`, `MAX(created_at)`. The `suggested_fix` field returns the value from the **most recent** pattern row for that error_type (use PostgreSQL `DISTINCT ON (error_type) ORDER BY created_at DESC` subquery). For `source` filter, join back to `log_jobs` on `log_job_id`.
4. **JSON stripping** — regex: `re.sub(r'^```json\s*|\s*```$', '', text, flags=re.MULTILINE)` before `json.loads`.
5. **Celery broker URL** — `REDIS_URL` used as both broker and result backend in `celery_app.py`.
6. **`updated_at` auto-update** — SQLAlchemy column must use `onupdate=func.now()` so the timestamp refreshes on every UPDATE, not just INSERT. Set `server_default=func.now()` for the initial value.
