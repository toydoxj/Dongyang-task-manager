"""users: add midas_url / midas_key / work_dir (MIDAS Electron 사용자 설정)

Revision ID: h7f8g9h00806
Revises: g6e7f8h90705
Create Date: 2026-04-27 01:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "h7f8g9h00806"
down_revision: Union[str, Sequence[str], None] = "g6e7f8h90705"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("midas_url", sa.String(), nullable=False, server_default="")
    )
    op.add_column(
        "users", sa.Column("midas_key", sa.String(), nullable=False, server_default="")
    )
    op.add_column(
        "users", sa.Column("work_dir", sa.String(), nullable=False, server_default="")
    )


def downgrade() -> None:
    op.drop_column("users", "work_dir")
    op.drop_column("users", "midas_key")
    op.drop_column("users", "midas_url")
