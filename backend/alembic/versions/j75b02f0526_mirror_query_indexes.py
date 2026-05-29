"""mirror 조회 패턴 복합/부분 인덱스 추가.

pg_stat_statements에서 반복적으로 확인된 아래 패턴을 지원한다.
- mirror_projects: archived=false, completed=false, code 정렬
- mirror_cashflow: archived=false, kind 필터, date 정렬

Revision ID: j75b02f0526
Revises: i75b02f0525
Create Date: 2026-05-26
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import context, op


revision: str = "j75b02f0526"
down_revision: Union[str, Sequence[str], None] = "i75b02f0525"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with context.get_context().autocommit_block():
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_mirror_projects_active_code_page
            ON mirror_projects (code ASC, page_id ASC)
            WHERE archived IS false
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_mirror_projects_active_open_code_page
            ON mirror_projects (code ASC, page_id ASC)
            WHERE archived IS false AND completed IS false
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_mirror_cashflow_active_kind_date
            ON mirror_cashflow (kind ASC, date ASC NULLS LAST, page_id ASC)
            WHERE archived IS false
            """
        )


def downgrade() -> None:
    with context.get_context().autocommit_block():
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS ix_mirror_cashflow_active_kind_date"
        )
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS ix_mirror_projects_active_open_code_page"
        )
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS ix_mirror_projects_active_code_page"
        )
