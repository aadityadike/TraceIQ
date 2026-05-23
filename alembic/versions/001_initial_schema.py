"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-05-24
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "log_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("raw_log", sa.Text(), nullable=False),
        sa.Column("source", sa.String(100), nullable=True),
        sa.Column(
            "status", sa.String(20), nullable=False, server_default="pending"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("error_count", sa.Integer(), nullable=True),
    )
    op.create_index("ix_log_jobs_status", "log_jobs", ["status"])
    op.create_index("ix_log_jobs_source", "log_jobs", ["source"])

    op.create_table(
        "error_patterns",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "log_job_id",
            UUID(as_uuid=True),
            sa.ForeignKey("log_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("error_type", sa.String(200), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("root_cause", sa.Text(), nullable=True),
        sa.Column("suggested_fix", sa.Text(), nullable=True),
        sa.Column("example_line", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("error_patterns")
    op.drop_index("ix_log_jobs_source", table_name="log_jobs")
    op.drop_index("ix_log_jobs_status", table_name="log_jobs")
    op.drop_table("log_jobs")
