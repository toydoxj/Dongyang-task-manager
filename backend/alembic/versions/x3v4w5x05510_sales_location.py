"""mirror_sales.location 컬럼 추가 (영업 row 단위 위치)

Revision ID: x3v4w5x05510
Revises: w2u3v4w05409
Create Date: 2026-05-08 12:00:00.000000

영업 위치를 영업 row 단위로 저장하기 위한 컬럼 추가. 사용자 명시: 영업 정보
탭에서 입력해 영업 row에 저장, 견적서 탭에서 echo로 자동 채움.
빈 문자열 default — 기존 영업 22건 회귀 X.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "x3v4w5x05510"
down_revision: Union[str, Sequence[str], None] = "w2u3v4w05409"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "mirror_sales",
        sa.Column("location", sa.String(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("mirror_sales", "location")
