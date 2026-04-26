"""mirror_tasks: add difficulty

Revision ID: f5d6e7g80604
Revises: e4c5d6f70503
Create Date: 2026-04-26 23:50:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f5d6e7g80604"
down_revision: Union[str, Sequence[str], None] = "e4c5d6f70503"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "mirror_tasks",
        sa.Column("difficulty", sa.String(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("mirror_tasks", "difficulty")
