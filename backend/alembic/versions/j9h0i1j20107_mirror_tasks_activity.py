"""mirror_tasks: add activity column (활동 select: 사무실/외근/출장)

Revision ID: j9h0i1j20107
Revises: i8g9h0i10907
Create Date: 2026-04-27 03:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "j9h0i1j20107"
down_revision: Union[str, Sequence[str], None] = "i8g9h0i10907"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "mirror_tasks",
        sa.Column("activity", sa.String(), nullable=False, server_default=""),
    )
    op.create_index(
        "ix_mirror_tasks_activity", "mirror_tasks", ["activity"]
    )


def downgrade() -> None:
    op.drop_index("ix_mirror_tasks_activity", table_name="mirror_tasks")
    op.drop_column("mirror_tasks", "activity")
