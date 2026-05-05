"""mirror_sales에 quote_doc_number + quote_form_data 컬럼 추가 (견적서 작성 툴)

Revision ID: u0s1t2u05207
Revises: t9r0s1t05106
Create Date: 2026-05-07 00:00:00.000000

PR5 — 견적서 작성 툴.
- quote_doc_number: {YY}-{MM}-{NNN} 형식 (월별 sequence). 영업코드와 별개.
- quote_form_data: 견적서 입력값(input) + 산출 결과(result) JSONB dump.
  추후 변경 이력 추적·재계산·xlsx 재출력 모두 가능하게 보존.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "u0s1t2u05207"
down_revision: Union[str, Sequence[str], None] = "t9r0s1t05106"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "mirror_sales",
        sa.Column(
            "quote_doc_number", sa.String(), nullable=False, server_default=""
        ),
    )
    op.add_column(
        "mirror_sales",
        sa.Column(
            "quote_form_data",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_index(
        "ix_mirror_sales_quote_doc_number",
        "mirror_sales",
        ["quote_doc_number"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_mirror_sales_quote_doc_number", table_name="mirror_sales"
    )
    op.drop_column("mirror_sales", "quote_form_data")
    op.drop_column("mirror_sales", "quote_doc_number")
