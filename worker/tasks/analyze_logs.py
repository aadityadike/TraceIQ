import json
import logging
import os
import re
import uuid
from typing import Optional

from celery_app import celery_app
from groq import Groq
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker
from sqlalchemy.sql import func

logger = logging.getLogger(__name__)

_engine = None
_SessionLocal = None


def _get_session():
    global _engine, _SessionLocal
    if _engine is None:
        _engine = create_engine(os.environ["DATABASE_URL"])
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
    return _SessionLocal()


class Base(DeclarativeBase):
    pass


class LogJob(Base):
    __tablename__ = "log_jobs"

    id = Column(PG_UUID(as_uuid=True), primary_key=True)
    raw_log = Column(Text)
    source = Column(String(100))
    status = Column(String(20))
    error_count = Column(Integer)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    patterns = relationship(
        "ErrorPattern", back_populates="log_job", cascade="all, delete-orphan"
    )


class ErrorPattern(Base):
    __tablename__ = "error_patterns"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    log_job_id = Column(
        PG_UUID(as_uuid=True), ForeignKey("log_jobs.id", ondelete="CASCADE")
    )
    error_type = Column(String(200))
    severity = Column(String(20))
    count = Column(Integer)
    root_cause = Column(Text)
    suggested_fix = Column(Text)
    example_line = Column(Text)

    log_job = relationship("LogJob", back_populates="patterns")


SYSTEM_PROMPT = """You are an expert backend engineer and SRE (Site Reliability Engineer).
You analyze application log files and identify error patterns, root causes, and actionable fixes.

Analyze the provided log file and return a JSON array of error patterns found.
Each pattern must follow this exact schema:

{
  "error_type": "short name for this error category (e.g. ConnectionTimeout, NullPointerException)",
  "severity": "critical | high | medium | low",
  "count": <integer — how many times this pattern appears>,
  "root_cause": "2-3 sentence technical explanation of WHY this error is happening",
  "suggested_fix": "2-3 sentence actionable fix with specific code/config suggestions where possible",
  "example_line": "one example log line from the input that shows this error"
}

Severity guide:
- critical: service is down or data loss risk
- high: major functionality broken, affecting users
- medium: degraded performance or intermittent failures
- low: warnings, deprecations, minor issues

Return ONLY a valid JSON array. No markdown. No explanation. Just the JSON array.
If no errors found, return an empty array []."""


def strip_markdown_json(content: str) -> str:
    return re.sub(r"^```json\s*|\s*```$", "", content.strip(), flags=re.MULTILINE)


def json_loads_safe(text: str) -> list:
    return json.loads(text)


def parse_groq_response(content: str, retries: int = 2) -> Optional[list]:
    for attempt in range(retries + 1):
        try:
            return json_loads_safe(strip_markdown_json(content))
        except Exception as exc:
            logger.warning(f"JSON parse attempt {attempt + 1} failed: {exc}")
    return None


@celery_app.task(name="tasks.analyze_logs.analyze_logs")
def analyze_logs(job_id: str) -> None:
    db: Session = _get_session()
    try:
        job = db.query(LogJob).filter(LogJob.id == uuid.UUID(job_id)).first()
        if not job:
            logger.error(f"Job {job_id} not found in database")
            return

        job.status = "processing"
        db.commit()

        client = Groq(api_key=os.environ["GROQ_API_KEY"])
        user_message = (
            f"Analyze these application logs:\n\n{job.raw_log}\n\n"
            f"Source service: {job.source or 'unknown'}"
        )

        completion = client.chat.completions.create(
            model="llama3-8b-8192",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.1,
        )

        raw_content = completion.choices[0].message.content
        patterns = parse_groq_response(raw_content)

        if patterns is None:
            logger.error(f"Failed to parse Groq response for job {job_id}")
            job.status = "failed"
            db.commit()
            return

        for p in patterns:
            db.add(
                ErrorPattern(
                    log_job_id=job.id,
                    error_type=p.get("error_type", "Unknown"),
                    severity=p.get("severity", "medium"),
                    count=int(p.get("count", 1)),
                    root_cause=p.get("root_cause"),
                    suggested_fix=p.get("suggested_fix"),
                    example_line=p.get("example_line"),
                )
            )

        job.status = "completed"
        job.error_count = len(patterns)
        db.commit()
        logger.info(f"Job {job_id} completed — {len(patterns)} patterns found")

    except Exception:
        logger.exception(f"Job {job_id} failed with unhandled exception")
        try:
            job = db.query(LogJob).filter(LogJob.id == uuid.UUID(job_id)).first()
            if job:
                job.status = "failed"
                db.commit()
        except Exception:
            pass
    finally:
        db.close()
