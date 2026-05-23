import logging
import subprocess
from contextlib import asynccontextmanager

import redis as redis_lib
from celery import Celery
from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from routers import logs, patterns
from schemas.log_job import HealthResponse

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Running database migrations...")
    subprocess.run(
        ["alembic", "-c", "alembic/alembic.ini", "upgrade", "head"],
        check=True,
    )
    logger.info("Migrations complete.")
    yield


app = FastAPI(
    title="Error Log Intelligence API",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(logs.router, prefix="/api/v1")
app.include_router(patterns.router, prefix="/api/v1")


@app.get("/health", response_model=HealthResponse)
async def health(db: AsyncSession = Depends(get_db)):
    # DB check
    try:
        await db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception:
        db_status = "disconnected"

    # Redis check
    try:
        r = redis_lib.Redis.from_url(settings.redis_url)
        r.ping()
        redis_status = "connected"
    except Exception:
        redis_status = "disconnected"

    # Celery worker check
    try:
        inspector = Celery(broker=settings.redis_url).control.inspect(timeout=2)
        active = inspector.active()
        worker_status = "active" if active else "no workers"
    except Exception:
        worker_status = "unknown"

    overall = (
        "ok"
        if db_status == "connected" and redis_status == "connected"
        else "degraded"
    )
    return HealthResponse(
        status=overall,
        db=db_status,
        redis=redis_status,
        worker=worker_status,
    )
