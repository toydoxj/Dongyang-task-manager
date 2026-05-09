"""mirror_tasks.weekly_plan_text 컬럼 추가 (PR-W Phase 2.2)

Revision ID: z5x6y7z05912
Revises: y4w5x6y05911
Create Date: 2026-05-09 19:00:00.000000

노션 task DB의 "금주예정사항" rich_text를 mirror에 정규화. 주간 보고서
팀별 표 우측 컬럼 출력용. 기존 `note`(영구 비고)와 분리.

빈 문자열 default — 기존 task row 회귀 X.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "z5x6y7z05912"
down_revision: Union[str, Sequence[str], None] = "y4w5x6y05911"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "mirror_tasks",
        sa.Column("weekly_plan_text", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("mirror_tasks", "weekly_plan_text")
