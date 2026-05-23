from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from schemas.log_job import AggregatedPattern, PatternsListResponse
from services.analysis import get_aggregated_patterns

router = APIRouter(prefix="/patterns", tags=["patterns"])


@router.get("", response_model=PatternsListResponse)
async def list_patterns(
    severity: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
):
    patterns = await get_aggregated_patterns(
        db, severity=severity, source=source, limit=limit
    )
    return PatternsListResponse(
        total=len(patterns),
        patterns=[AggregatedPattern(**p) for p in patterns],
    )
