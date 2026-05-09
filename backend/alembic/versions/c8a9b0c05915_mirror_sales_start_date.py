"""mirror_sales.sales_start_date 컬럼 추가 (영업 시작일)

Revision ID: c8a9b0c05915
Revises: b7z8a9b05914
Create Date: 2026-05-09 21:00:00.000000

영업 활동 시작 시점. 노션 영업 DB의 "영업시작일" date 컬럼 미러.
주간 보고서의 "영업" 섹션 cutoff 기준 (저번주 범위 내 시작된 영업).

기존 row는 NULL — 회귀 X.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c8a9b0c05915"
down_revision: Union[str, Sequence[str], None] = "b7z8a9b05914"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "mirror_sales",
        sa.Column("sales_start_date", sa.Date(), nullable=True),
    )
    op.create_index(
        "ix_mirror_sales_sales_start_date",
        "mirror_sales",
        ["sales_start_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_mirror_sales_sales_start_date", table_name="mirror_sales")
    op.drop_column("mirror_sales", "sales_start_date")
