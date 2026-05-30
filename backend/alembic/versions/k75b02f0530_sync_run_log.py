"""sync 실행 이력 테이블 추가.

Revision ID: k75b02f0530
Revises: j75b02f0526
Create Date: 2026-05-30
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "k75b02f0530"
down_revision: Union[str, Sequence[str], None] = "j75b02f0526"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notion_sync_run_log",
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("full", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("result", sa.Text(), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_index(
        "ix_notion_sync_run_log_started_at",
        "notion_sync_run_log",
        ["started_at"],
    )
    op.create_index(
        "ix_notion_sync_run_log_status",
        "notion_sync_run_log",
        ["status"],
    )
    op.create_index(
        "ix_notion_sync_run_log_source",
        "notion_sync_run_log",
        ["source"],
    )
    op.create_index(
        "ix_notion_sync_run_log_kind",
        "notion_sync_run_log",
        ["kind"],
    )
    op.create_index(
        "ix_notion_sync_run_log_full",
        "notion_sync_run_log",
        ["full"],
    )


def downgrade() -> None:
    op.drop_index("ix_notion_sync_run_log_full", table_name="notion_sync_run_log")
    op.drop_index("ix_notion_sync_run_log_kind", table_name="notion_sync_run_log")
    op.drop_index("ix_notion_sync_run_log_source", table_name="notion_sync_run_log")
    op.drop_index("ix_notion_sync_run_log_status", table_name="notion_sync_run_log")
    op.drop_index(
        "ix_notion_sync_run_log_started_at",
        table_name="notion_sync_run_log",
    )
    op.drop_table("notion_sync_run_log")
