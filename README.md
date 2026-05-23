# Error Log Intelligence API

A production-ready backend API that accepts application logs, uses AI (Groq LLaMA3) to analyze them asynchronously, and returns structured insights including error patterns, root causes, severity ratings, and suggested fixes. Built with FastAPI, Celery, PostgreSQL, and Redis — all containerized with Docker Compose.

---

## Architecture

```
Client
  │
  ▼
FastAPI (port 8000)
  │         │
  │         ▼
  │      PostgreSQL ◄──── Celery Worker
  │                            │
  ▼                            ▼
Redis (job queue) ────────► Groq API (LLaMA3)
```

---

## Tech Stack

| Component | Technology | Why |
|---|---|---|
| API Framework | FastAPI (async) | High throughput, automatic OpenAPI docs, async-native |
| Database | PostgreSQL 15 | Relational integrity, UUID support, DISTINCT ON for aggregations |
| ORM | SQLAlchemy 2.0 | Async-first, type-safe queries, Alembic integration |
| Queue | Redis 7 | Low-latency broker; Celery's most reliable backend |
| Worker | Celery 5 | Distributed task queue, retry support, concurrency control |
| AI | Groq / LLaMA3 | Free tier, ~10x faster inference than OpenAI for same model class |
| Validation | Pydantic v2 | Runtime validation, serialization, OpenAPI schema generation |

---

## Prerequisites

- Docker Desktop installed and running
- Groq API key (free at https://console.groq.com)
- Git

---

## Getting Started

```bash
# 1. Clone the repo
git clone <repo-url>
cd error-log-intelligence

# 2. Add your Groq API key
cp .env.example .env
# Edit .env and set GROQ_API_KEY=your_actual_key

# 3. Start everything
docker-compose up --build

# 4. Verify it's running
curl http://localhost:8000/health

# 5. Submit your first log (see Usage below)
```

---

## API Usage

### Submit logs for analysis

```bash
curl -X POST http://localhost:8000/api/v1/logs/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "raw_log": "2024-01-15 10:23:45 ERROR PaymentService - NullPointerException at com.example.PaymentProcessor.charge(PaymentProcessor.java:234)\n2024-01-15 10:23:46 ERROR PaymentService - Connection timeout to DB after 30s\n2024-01-15 10:23:47 ERROR PaymentService - Connection timeout to DB after 30s\n2024-01-15 10:23:48 WARN  PaymentService - Retry attempt 1/3 for transaction TX-8821\n2024-01-15 10:23:49 ERROR PaymentService - Connection timeout to DB after 30s\n2024-01-15 10:24:01 FATAL PaymentService - Circuit breaker OPEN — all DB calls rejected",
    "source": "payment-service"
  }'
```

Response (202):
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "message": "Log submitted for analysis. Poll /api/v1/logs/550e8400... for results.",
  "created_at": "2024-01-15T10:23:45Z"
}
```

### Poll for results

```bash
curl http://localhost:8000/api/v1/logs/550e8400-e29b-41d4-a716-446655440000
```

### List all jobs

```bash
curl "http://localhost:8000/api/v1/logs?page=1&limit=20&status=completed"
```

### Get aggregated patterns (cross-job insights)

```bash
curl "http://localhost:8000/api/v1/patterns?severity=critical&limit=5"
```

### Delete a job

```bash
curl -X DELETE http://localhost:8000/api/v1/logs/550e8400-e29b-41d4-a716-446655440000
```

### Health check

```bash
curl http://localhost:8000/health
```

---

## Component Deep Dive

**FastAPI** handles all HTTP traffic asynchronously using Python's asyncio. It validates requests with Pydantic, persists jobs to PostgreSQL via asyncpg, then immediately dispatches work to Celery and returns 202 — the caller never waits for AI analysis.

**PostgreSQL** stores two tables: `log_jobs` (one per submission, tracks status lifecycle) and `error_patterns` (many per job, cascade-deleted). The `patterns` endpoint uses a CTE with `DISTINCT ON` for efficient cross-job aggregation.

**Redis** is Celery's message broker and result backend. FastAPI writes task messages to Redis; the Celery worker reads and executes them. Redis itself holds no application data — all results go to PostgreSQL.

**Celery Worker** runs with 4 concurrent processes (`--concurrency=4`). Each process picks up an `analyze_logs` task, calls Groq, parses the JSON response, writes `ErrorPattern` rows, and updates the `LogJob` status. The entire task is wrapped in try/except — exceptions always set status to `"failed"`, never leave jobs stuck in `"processing"`.

**Groq** provides free-tier inference for `llama3-8b-8192`. At ~800 tokens/sec, analysis of a typical log file completes in 1-3 seconds. The system prompt instructs the model to return only a JSON array, which the worker strips of any markdown fencing before parsing.

---

## How the AI Analysis Works

1. Developer POSTs a raw log string to `/api/v1/logs/ingest`
2. FastAPI saves a `LogJob` with `status="pending"` to PostgreSQL
3. FastAPI calls `celery_client.send_task("tasks.analyze_logs.analyze_logs", [job_id])`
4. FastAPI returns 202 immediately — the developer gets a `job_id`
5. Celery worker picks up the task from Redis
6. Worker sets `status="processing"`, then calls Groq with the log + system prompt
7. Groq returns a JSON array of error patterns
8. Worker strips any markdown fencing, parses JSON (2 retries on failure)
9. Worker bulk-inserts `ErrorPattern` rows and sets `status="completed"`
10. Developer polls `GET /api/v1/logs/{job_id}` and gets back structured patterns

---

## Extending This Project

- **Authentication** — Add JWT + API key middleware; scope jobs to tenants
- **Webhook notifications** — POST to a callback URL when analysis completes
- **Slack/PagerDuty integration** — Alert on `critical` patterns in real time
- **Dashboard UI** — React frontend with job list, pattern timeline, severity charts
- **Log streaming via WebSocket** — Stream analysis progress as the worker processes
- **Anomaly detection** — Track error rate over time; alert on sudden spikes
- **Export as PDF** — Generate structured incident reports from pattern data
- **Multi-tenancy** — Isolate jobs/patterns per team with row-level security

---

## Running Tests

Tests use pytest + pytest-asyncio + httpx AsyncClient. Example structure:

```python
# api/tests/test_logs_router.py
import pytest
from httpx import AsyncClient, ASGITransport
from main import app

@pytest.mark.asyncio
async def test_ingest_returns_202():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/logs/ingest", json={
            "raw_log": "ERROR: something broke",
            "source": "test-service"
        })
    assert response.status_code == 202
    assert "job_id" in response.json()
```

Run existing unit tests:
```bash
docker compose exec api pytest tests/ -v
docker compose exec worker pytest tests/ -v
```
