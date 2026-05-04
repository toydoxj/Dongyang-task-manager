"""user_sessions 테이블 추가 — client별 활성 세션 분리

Revision ID: q6o7p8q90504
Revises: p5n6o7p80513
Create Date: 2026-05-04 00:00:00.000000

기존: users.session_id 단일 컬럼 → 한 사용자당 활성 세션 1개
    → task.dyce.kr 와 외부 클라이언트(예: dy-midas Electron 앱)가 SSO를 공유하면
      나중 로그인이 직전 sid를 무효화 → 401 "다른 기기에서 로그인되었습니다"

변경: user_sessions 테이블 PK(user_id, client) 도입.
    각 (사용자, 클라이언트) 조합이 독립 sid 보유. 같은 client 내 재로그인은 여전히
    직전 세션 무효화(single-session per client).

users.session_id 컬럼은 레거시 토큰(JWT cli claim 없음) 호환을 위해 유지.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "q6o7p8q90504"
down_revision: Union[str, Sequence[str], None] = "p5n6o7p80513"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_sessions",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("client", sa.String(length=32), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "client", name="pk_user_sessions"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_user_sessions_user_id",
        ),
    )


def downgrade() -> None:
    op.drop_table("user_sessions")
