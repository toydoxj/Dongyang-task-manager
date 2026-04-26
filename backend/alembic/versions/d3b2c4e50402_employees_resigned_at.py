"""employees: add resigned_at

Revision ID: d3b2c4e50402
Revises: c2a1b3d40301
Create Date: 2026-04-26 22:30:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d3b2c4e50402"
down_revision: Union[str, Sequence[str], None] = "c2a1b3d40301"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "employees", sa.Column("resigned_at", sa.Date(), nullable=True)
    )
    op.create_index("ix_employees_resigned_at", "employees", ["resigned_at"])


def downgrade() -> None:
    op.drop_index("ix_employees_resigned_at", table_name="employees")
    op.drop_column("employees", "resigned_at")
