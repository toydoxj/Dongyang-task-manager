"""mirror read-heavy endpoint 보조 인덱스 추가.

Revision ID: l75b02f0602
Revises: k75b02f0530
Create Date: 2026-06-02
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import context, op

revision: str = "l75b02f0602"
down_revision: str | Sequence[str] | None = "k75b02f0530"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with context.get_context().autocommit_block():
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_mirror_tasks_active_end_page
            ON mirror_tasks (end_date ASC NULLS LAST, page_id ASC)
            WHERE archived IS false
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_mirror_tasks_active_start_created
            ON mirror_tasks (created_time ASC, page_id ASC)
            WHERE archived IS false AND status = '시작 전'
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_mirror_tasks_sales_ids_gin
            ON mirror_tasks USING GIN (sales_ids)
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_mirror_cashflow_active_date_page
            ON mirror_cashflow (date ASC NULLS LAST, page_id ASC)
            WHERE archived IS false
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_mirror_seal_requests_active_created
            ON mirror_seal_requests (created_time DESC, page_id ASC)
            WHERE archived IS false
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_mirror_seal_requests_project_ids_gin
            ON mirror_seal_requests USING GIN (project_ids)
            """
        )


def downgrade() -> None:
    with context.get_context().autocommit_block():
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS ix_mirror_seal_requests_project_ids_gin"
        )
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS ix_mirror_seal_requests_active_created"
        )
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS ix_mirror_cashflow_active_date_page"
        )
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_mirror_tasks_sales_ids_gin")
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS ix_mirror_tasks_active_start_created"
        )
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_mirror_tasks_active_end_page")
