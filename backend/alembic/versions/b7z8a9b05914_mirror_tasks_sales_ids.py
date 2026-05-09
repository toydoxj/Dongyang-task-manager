"""mirror_tasks.sales_ids 컬럼 추가 (task ↔ 영업 relation)

Revision ID: b7z8a9b05914
Revises: a6y7z8a05913
Create Date: 2026-05-09 20:00:00.000000

노션 task DB의 "영업" relation을 미러. project_ids와 동일 패턴 (다대다 ARRAY).
운영자가 노션 task DB에 "영업" 라는 이름의 relation 컬럼(→ 영업 DB)을 직접
추가해야 sync가 활성화된다 (notion_schema 자동 보강은 relation 미지원).

기존 row는 빈 array default — 회귀 X.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b7z8a9b05914"
down_revision: Union[str, Sequence[str], None] = "a6y7z8a05913"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "mirror_tasks",
        sa.Column(
            "sales_ids",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("mirror_tasks", "sales_ids")
