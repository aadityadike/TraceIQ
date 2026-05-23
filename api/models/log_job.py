import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base

__all__ = ["Base", "LogJob", "ErrorPattern"]


class LogJob(Base):
    __tablename__ = "log_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    raw_log = Column(Text, nullable=False)
    source = Column(String(100), nullable=True)
    status = Column(String(20), nullable=False, default="pending")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    error_count = Column(Integer, nullable=True)

    patterns = relationship(
        "ErrorPattern", back_populates="log_job", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_log_jobs_status", "status"),
        Index("ix_log_jobs_source", "source"),
    )


class ErrorPattern(Base):
    __tablename__ = "error_patterns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    log_job_id = Column(
        UUID(as_uuid=True),
        ForeignKey("log_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    error_type = Column(String(200), nullable=False)
    severity = Column(String(20), nullable=False)
    count = Column(Integer, nullable=False)
    root_cause = Column(Text)
    suggested_fix = Column(Text)
    example_line = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    log_job = relationship("LogJob", back_populates="patterns")
