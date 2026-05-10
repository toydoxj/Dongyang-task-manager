"""weekly_report_publish_log 신설 (PR-W 발행 로그)

Revision ID: d9b0c1d05011
Revises: c8a9b0c05915
Create Date: 2026-05-11 09:00:00.000000

발행 = WORKS Drive 업로드 + 전직원 알림. 다음 주간일지 작성 시
"저번주 시작일"의 default를 마지막 발행된 week_end + 1로 자동 셋팅하기 위한 기록.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d9b0c1d05011"
down_revision: Union[str, Sequence[str], None] = "c8a9b0c05915"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "weekly_report_publish_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("week_end", sa.Date(), nullable=False),
        sa.Column("last_week_start", sa.Date(), nullable=True),
        sa.Column("last_week_end", sa.Date(), nullable=True),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("published_by", sa.String(), nullable=False, server_default=""),
        sa.Column("file_id", sa.String(), nullable=False, server_default=""),
        sa.Column("file_url", sa.String(), nullable=False, server_default=""),
        sa.Column("file_name", sa.String(), nullable=False, server_default=""),
        sa.Column(
            "recipient_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "notify_failed_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("error", sa.String(), nullable=True),
    )
    op.create_index(
        "ix_weekly_report_publish_log_published_at",
        "weekly_report_publish_log",
        ["published_at"],
    )
    op.create_index(
        "ix_weekly_report_publish_log_week_start",
        "weekly_report_publish_log",
        ["week_start"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_weekly_report_publish_log_week_start",
        table_name="weekly_report_publish_log",
    )
    op.drop_index(
        "ix_weekly_report_publish_log_published_at",
        table_name="weekly_report_publish_log",
    )
    op.drop_table("weekly_report_publish_log")
