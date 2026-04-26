"""create employees table

Revision ID: c2a1b3d40301
Revises: b1f3a2c0e201
Create Date: 2026-04-26 21:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c2a1b3d40301"
down_revision: Union[str, Sequence[str], None] = "b1f3a2c0e201"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "employees",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("position", sa.String(), nullable=False, server_default=""),
        sa.Column("team", sa.String(), nullable=False, server_default=""),
        sa.Column("degree", sa.String(), nullable=False, server_default=""),
        sa.Column("license", sa.String(), nullable=False, server_default=""),
        sa.Column("grade", sa.String(), nullable=False, server_default=""),
        sa.Column("email", sa.String(), nullable=False, server_default=""),
        sa.Column(
            "linked_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_employees_name", "employees", ["name"])
    op.create_index("ix_employees_email", "employees", ["email"])
    op.create_index("ix_employees_linked_user", "employees", ["linked_user_id"])


def downgrade() -> None:
    op.drop_index("ix_employees_linked_user", table_name="employees")
    op.drop_index("ix_employees_email", table_name="employees")
    op.drop_index("ix_employees_name", table_name="employees")
    op.drop_table("employees")
