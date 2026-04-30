"""employees.sort_order 컬럼 추가 (admin이 드래그로 순서 지정용)

Revision ID: o4m5n6o70612
Revises: n3l4m5n60511
Create Date: 2026-04-30 19:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "o4m5n6o70612"
down_revision: Union[str, Sequence[str], None] = "n3l4m5n60511"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "employees",
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_employees_sort_order", "employees", ["sort_order"])


def downgrade() -> None:
    op.drop_index("ix_employees_sort_order", table_name="employees")
    op.drop_column("employees", "sort_order")
