"""users: add SSO fields (works_user_id, auth_provider, sso_login_at)

Revision ID: k0i1j2k30208
Revises: j9h0i1j20107
Create Date: 2026-04-28 00:00:00.000000

NAVER WORKS OIDC SSO Phase 1.
- works_user_id: OIDC sub 클레임 (UNIQUE INDEX, nullable — password-only 사용자 호환)
- auth_provider: 'password' | 'works' | 'both' (기존 사용자는 'password')
- sso_login_at: 마지막 SSO 로그인 시각
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "k0i1j2k30208"
down_revision: Union[str, Sequence[str], None] = "j9h0i1j20107"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("works_user_id", sa.String(), nullable=True)
    )
    op.add_column(
        "users",
        sa.Column(
            "auth_provider",
            sa.String(),
            nullable=False,
            server_default="password",
        ),
    )
    op.add_column(
        "users", sa.Column("sso_login_at", sa.DateTime(), nullable=True)
    )
    op.create_index(
        "ix_users_works_user_id",
        "users",
        ["works_user_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_users_works_user_id", table_name="users")
    op.drop_column("users", "sso_login_at")
    op.drop_column("users", "auth_provider")
    op.drop_column("users", "works_user_id")
