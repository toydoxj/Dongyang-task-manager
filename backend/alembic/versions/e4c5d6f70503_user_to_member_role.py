"""rename role 'user' -> 'member' (introduce team_lead)

Revision ID: e4c5d6f70503
Revises: d3b2c4e50402
Create Date: 2026-04-26 23:30:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "e4c5d6f70503"
down_revision: Union[str, Sequence[str], None] = "d3b2c4e50402"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE users SET role='member' WHERE role='user'")


def downgrade() -> None:
    op.execute("UPDATE users SET role='user' WHERE role='member'")
