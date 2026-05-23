from typing import Optional
from uuid import UUID

from sqlalchemy import func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from models.log_job import ErrorPattern, LogJob


async def get_log_job(db: AsyncSession, job_id: UUID) -> Optional[LogJob]:
    result = await db.execute(
        select(LogJob)
        .options(selectinload(LogJob.patterns))
        .where(LogJob.id == job_id)
    )
    return result.scalar_one_or_none()


async def list_log_jobs(
    db: AsyncSession,
    page: int = 1,
    limit: int = 20,
    status: Optional[str] = None,
    source: Optional[str] = None,
) -> tuple[int, list[LogJob]]:
    query = select(LogJob)
    count_query = select(func.count()).select_from(LogJob)

    if status:
        query = query.where(LogJob.status == status)
        count_query = count_query.where(LogJob.status == status)
    if source:
        query = query.where(LogJob.source == source)
        count_query = count_query.where(LogJob.source == source)

    total = (await db.execute(count_query)).scalar()

    query = (
        query.order_by(LogJob.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    items = (await db.execute(query)).scalars().all()

    return total, items


async def get_aggregated_patterns(
    db: AsyncSession,
    severity: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = 10,
) -> list[dict]:
    """
    Uses a PostgreSQL CTE with DISTINCT ON to get:
    - Aggregated count/job_count/latest_seen per error_type
    - suggested_fix and severity from the most recent pattern of that type
    """
    params: dict = {"limit": limit}
    join_clause = ""
    conditions: list[str] = []

    if source:
        join_clause = "JOIN log_jobs lj ON ep.log_job_id = lj.id"
        conditions.append("lj.source = :source")
        params["source"] = source

    if severity:
        conditions.append("ep.severity = :severity")
        params["severity"] = severity

    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    sql = text(
        f"""
        WITH latest_per_type AS (
            SELECT DISTINCT ON (ep.error_type)
                ep.error_type,
                ep.suggested_fix,
                ep.severity
            FROM error_patterns ep
            {join_clause}
            {where_clause}
            ORDER BY ep.error_type, ep.created_at DESC
        ),
        aggregated AS (
            SELECT
                ep.error_type,
                SUM(ep.count)                 AS total_occurrences,
                COUNT(DISTINCT ep.log_job_id) AS job_count,
                MAX(ep.created_at)            AS latest_seen
            FROM error_patterns ep
            {join_clause}
            {where_clause}
            GROUP BY ep.error_type
        )
        SELECT
            a.error_type,
            a.total_occurrences,
            a.job_count,
            a.latest_seen,
            l.severity,
            l.suggested_fix
        FROM aggregated a
        JOIN latest_per_type l ON a.error_type = l.error_type
        ORDER BY a.total_occurrences DESC
        LIMIT :limit
        """
    )

    result = await db.execute(sql, params)
    return [dict(row._mapping) for row in result.all()]
