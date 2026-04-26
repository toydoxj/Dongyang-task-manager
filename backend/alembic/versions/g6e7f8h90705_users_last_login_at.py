"""users: add last_login_at

Revision ID: g6e7f8h90705
Revises: f5d6e7g80604
Create Date: 2026-04-27 00:30:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "g6e7f8h90705"
down_revision: Union[str, Sequence[str], None] = "f5d6e7g80604"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("last_login_at", sa.DateTime(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("users", "last_login_at")
