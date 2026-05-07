"""mirror_sales에 quote_type 컬럼 추가 (PR-Q1)

Revision ID: v1t2u3v05308
Revises: u0s1t2u05207
Create Date: 2026-05-07 00:00:00.000000

PR-Q1 — 견적서 8종 분류 dispatch 키.
빈 문자열은 '구조설계' fallback. 기존 22건 영업은 모두 빈 값으로 들어가
fallback 처리되므로 데이터 손실/회귀 없음.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v1t2u3v05308"
down_revision: Union[str, Sequence[str], None] = "u0s1t2u05207"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "mirror_sales",
        sa.Column(
            "quote_type", sa.String(), nullable=False, server_default=""
        ),
    )
    op.create_index(
        "ix_mirror_sales_quote_type",
        "mirror_sales",
        ["quote_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_mirror_sales_quote_type", table_name="mirror_sales")
    op.drop_column("mirror_sales", "quote_type")
