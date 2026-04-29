"""drive_credentials 테이블 신설 (NAVER WORKS Drive admin 위임 토큰)

Revision ID: m2k3l4m50410
Revises: l1j2k3l40209
Create Date: 2026-04-29 10:00:00.000000

NAVER WORKS Drive API는 user 토큰만 받으므로 admin 동의 토큰을 보관할 곳.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "m2k3l4m50410"
down_revision: Union[str, Sequence[str], None] = "l1j2k3l40209"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "drive_credentials",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("access_token", sa.String(), nullable=False, server_default=""),
        sa.Column("refresh_token", sa.String(), nullable=False, server_default=""),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("scope", sa.String(), nullable=False, server_default=""),
        sa.Column("granted_by_user_id", sa.Integer(), nullable=True),
        sa.Column("granted_by_email", sa.String(), nullable=False, server_default=""),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )


def downgrade() -> None:
    op.drop_table("drive_credentials")
