"""mirror_sales에 code(영업코드) + probability(수주확률) 컬럼 추가

Revision ID: t9r0s1t05106
Revises: s8q9r0s05055
Create Date: 2026-05-05 14:00:00.000000

사장 결정에 따라:
- code: {YY}-영업-{NNN} 형식 자동 부여 (서버 측), 노션 수동 수정 허용
- probability: PM이 0~100 직접 입력. 단계별 자동 확률 모델 폐기.
- expected_revenue = 견적금액 × probability/100 (Sale.computed_field)
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "t9r0s1t05106"
down_revision: Union[str, Sequence[str], None] = "s8q9r0s05055"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "mirror_sales",
        sa.Column("code", sa.String(), nullable=False, server_default=""),
    )
    op.add_column(
        "mirror_sales",
        sa.Column("probability", sa.Float(), nullable=True),
    )
    op.create_index("ix_mirror_sales_code", "mirror_sales", ["code"])


def downgrade() -> None:
    op.drop_index("ix_mirror_sales_code", table_name="mirror_sales")
    op.drop_column("mirror_sales", "probability")
    op.drop_column("mirror_sales", "code")
