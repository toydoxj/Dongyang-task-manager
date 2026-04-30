"""calendar_event_links 테이블 + employees.works_user_id 컬럼

Revision ID: n3l4m5n60511
Revises: m2k3l4m50410
Create Date: 2026-04-30 13:30:00.000000

NAVER WORKS Calendar 동기화 도입:
- calendar_event_links: 노션 task ↔ WORKS event 매핑 보관 (중복 생성·갱신·삭제용)
- employees.works_user_id: 직원 명부에 NAVER WORKS userId 저장 (Calendar API path 용)
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "n3l4m5n60511"
down_revision: Union[str, Sequence[str], None] = "m2k3l4m50410"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "calendar_event_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("notion_task_id", sa.String(), nullable=False),
        sa.Column("target_user_id", sa.String(), nullable=False),
        sa.Column("calendar_id", sa.String(), nullable=False, server_default=""),
        sa.Column("event_id", sa.String(), nullable=False),
        sa.Column(
            "is_shared", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint(
            "notion_task_id",
            "target_user_id",
            "calendar_id",
            name="uq_cal_link_task_user_cal",
        ),
    )
    op.create_index(
        "ix_cal_link_task", "calendar_event_links", ["notion_task_id"]
    )

    op.add_column(
        "employees",
        sa.Column(
            "works_user_id", sa.String(), nullable=False, server_default=""
        ),
    )
    op.create_index(
        "ix_employees_works_user_id", "employees", ["works_user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_employees_works_user_id", table_name="employees")
    op.drop_column("employees", "works_user_id")
    op.drop_index("ix_cal_link_task", table_name="calendar_event_links")
    op.drop_table("calendar_event_links")
