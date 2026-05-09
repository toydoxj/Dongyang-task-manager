"""project_snapshots 테이블 추가 (PR-W weekly_snapshot 인프라)

Revision ID: y4w5x6y05911
Revises: x3v4w5x05510
Create Date: 2026-05-09 18:00:00.000000

매주 일요일 23:59 KST에 진행 중 프로젝트의 진행률·단계·담당자를 박제.
주간 보고서 Δ 표시용. 4주 누적 후 활용 — 1차에서는 cron만 켜고 출력은 미사용.

(project_id, week_start) UNIQUE — 한 주차에 한 row만 존재.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "y4w5x6y05911"
down_revision: Union[str, Sequence[str], None] = "x3v4w5x05510"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_snapshots",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("code", sa.String(), nullable=False, server_default=""),
        sa.Column("name", sa.String(), nullable=False, server_default=""),
        sa.Column("stage", sa.String(), nullable=False, server_default=""),
        sa.Column("progress", sa.Float(), nullable=False, server_default="0"),
        sa.Column(
            "assignees",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "teams",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "extra",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "snapshot_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "week_start",
            name="uq_project_snapshots_project_week",
        ),
    )
    op.create_index(
        "ix_project_snapshots_project_id",
        "project_snapshots",
        ["project_id"],
    )
    op.create_index(
        "ix_project_snapshots_week_start",
        "project_snapshots",
        ["week_start"],
    )


def downgrade() -> None:
    op.drop_index("ix_project_snapshots_week_start", table_name="project_snapshots")
    op.drop_index("ix_project_snapshots_project_id", table_name="project_snapshots")
    op.drop_table("project_snapshots")
