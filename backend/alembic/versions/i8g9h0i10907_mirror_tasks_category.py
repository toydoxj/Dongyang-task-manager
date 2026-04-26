"""mirror_tasks: add category column (분류 select)

Revision ID: i8g9h0i10907
Revises: h7f8g9h00806
Create Date: 2026-04-27 02:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "i8g9h0i10907"
down_revision: Union[str, Sequence[str], None] = "h7f8g9h00806"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "mirror_tasks",
        sa.Column("category", sa.String(), nullable=False, server_default=""),
    )
    op.create_index(
        "ix_mirror_tasks_category", "mirror_tasks", ["category"]
    )


def downgrade() -> None:
    op.drop_index("ix_mirror_tasks_category", table_name="mirror_tasks")
    op.drop_column("mirror_tasks", "category")
