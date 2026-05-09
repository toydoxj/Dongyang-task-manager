"""notices 테이블 추가 (PR-W Phase 2.4)

Revision ID: a6y7z8a05913
Revises: z5x6y7z05912
Create Date: 2026-05-09 19:30:00.000000

사내 공지 / 교육 일정 — 주간 업무일지 1페이지 source. admin이 직접 관리하는
자체 테이블 (노션 미러 X). PLAN_WEEKLY_REPORT 권장.

게시기간(start_date~end_date)이 보고서 주차와 겹치는 row만 PDF에 표시.
end_date NULL = 무기한.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a6y7z8a05913"
down_revision: Union[str, Sequence[str], None] = "z5x6y7z05912"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notices",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("author_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["author_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notices_kind", "notices", ["kind"])
    op.create_index("ix_notices_start_date", "notices", ["start_date"])
    op.create_index("ix_notices_end_date", "notices", ["end_date"])
    op.create_index("ix_notices_author_user_id", "notices", ["author_user_id"])


def downgrade() -> None:
    op.drop_index("ix_notices_author_user_id", table_name="notices")
    op.drop_index("ix_notices_end_date", table_name="notices")
    op.drop_index("ix_notices_start_date", table_name="notices")
    op.drop_index("ix_notices_kind", table_name="notices")
    op.drop_table("notices")
