"""mirror_sales.parent_lead_id 컬럼 drop (PR-M4b)

Revision ID: w2u3v4w05409
Revises: v1t2u3v05308
Create Date: 2026-05-08 00:00:00.000000

PR-M (영업당 다중 견적) 모델로 전환되며 parent_lead_id 자식 영업 grouping
패턴 폐기. 사용자 확인 — 노션 영업 row의 "상위 영업건" relation에 데이터 없음.

downgrade는 컬럼 + index 복원만 (저장된 값 복원 X — 데이터 영구 손실).
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "w2u3v4w05409"
down_revision: Union[str, Sequence[str], None] = "v1t2u3v05308"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index(
        "ix_mirror_sales_parent_lead_id", table_name="mirror_sales"
    )
    op.drop_column("mirror_sales", "parent_lead_id")


def downgrade() -> None:
    op.add_column(
        "mirror_sales",
        sa.Column(
            "parent_lead_id", sa.String(), nullable=False, server_default=""
        ),
    )
    op.create_index(
        "ix_mirror_sales_parent_lead_id",
        "mirror_sales",
        ["parent_lead_id"],
    )
