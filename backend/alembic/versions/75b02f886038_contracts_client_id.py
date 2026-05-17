"""contracts_client_id — PR-FI/4 (계약서 자체 발주처 필드 추가).

Contract.client_id 컬럼 (nullable). 옛 row는 NULL — 프로젝트의 발주처를 그대로 따름.
공동수급 등 계약서별로 다른 발주처가 필요한 경우에 사용.

production DB의 false-positive index 변경은 모두 제거하고 contracts.client_id 추가만 남김.

Revision ID: 75b02f886038
Revises: 13ec7a9cd151
Create Date: 2026-05-17 20:28:56.366316
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "75b02f886038"
down_revision: Union[str, Sequence[str], None] = "13ec7a9cd151"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "contracts", sa.Column("client_id", sa.String(), nullable=True)
    )
    op.create_index(
        op.f("ix_contracts_client_id"), "contracts", ["client_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_contracts_client_id"), table_name="contracts")
    op.drop_column("contracts", "client_id")
