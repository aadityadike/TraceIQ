import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from celery_client import celery_client
from database import get_db
from models.log_job import LogJob
from schemas.log_job import (
    LogIngestRequest,
    LogIngestResponse,
    LogJobDetailResponse,
    LogJobListItem,
    LogJobListResponse,
)
from services.analysis import get_log_job, list_log_jobs

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/logs", tags=["logs"])


@router.post(
    "/ingest",
    status_code=http_status.HTTP_202_ACCEPTED,
    response_model=LogIngestResponse,
)
async def ingest_log(
    request: LogIngestRequest, db: AsyncSession = Depends(get_db)
):
    job = LogJob(raw_log=request.raw_log, source=request.source)
    db.add(job)
    await db.commit()
    await db.refresh(job)

    celery_client.send_task(
        "tasks.analyze_logs.analyze_logs", args=[str(job.id)]
    )
    logger.info(f"Dispatched analysis task for job {job.id}")

    return LogIngestResponse(
        job_id=job.id,
        status=job.status,
        message=f"Log submitted for analysis. Poll /api/v1/logs/{job.id} for results.",
        created_at=job.created_at,
    )


@router.get("/{job_id}", response_model=LogJobDetailResponse)
async def get_job(job_id: UUID, db: AsyncSession = Depends(get_db)):
    job = await get_log_job(db, job_id)
    if not job:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail="Job not found"
        )
    return job


@router.get("", response_model=LogJobListResponse)
async def list_jobs(
    page: int = 1,
    limit: int = 20,
    status: Optional[str] = None,
    source: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    total, items = await list_log_jobs(
        db, page=page, limit=limit, status=status, source=source
    )
    return LogJobListResponse(
        total=total,
        page=page,
        limit=limit,
        items=[LogJobListItem.model_validate(item) for item in items],
    )


@router.delete("/{job_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_job(job_id: UUID, db: AsyncSession = Depends(get_db)):
    job = await get_log_job(db, job_id)
    if not job:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail="Job not found"
        )
    await db.delete(job)
    await db.commit()
