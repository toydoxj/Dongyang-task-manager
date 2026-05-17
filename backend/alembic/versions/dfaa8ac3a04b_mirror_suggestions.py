"""mirror_suggestions — 건의사항 미러 테이블 (PR-EX/1, 2026-05-17)

Revision ID: dfaa8ac3a04b
Revises: f1d2e3f05015
Create Date: 2026-05-17 09:40:36.849689

routers/suggestions.py:list_suggestions가 매번 notion.query_all 전량 fetch
하던 PR-CR 진단 2순위 해소. SuggestionItem 전체 schema 미러링.

후속 PR-EX/2: services/sync.py에 "suggestions" SyncKind + _upsert_suggestion
후속 PR-EX/3: list_suggestions mirror 조회 전환 + write-through upsert
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "dfaa8ac3a04b"
down_revision: Union[str, Sequence[str], None] = "f1d2e3f05015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mirror_suggestions",
        sa.Column("page_id", sa.String(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False, server_default=""),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("author", sa.String(), nullable=False, server_default=""),
        sa.Column(
            "categories",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("status", sa.String(), nullable=False, server_default=""),
        sa.Column("resolution", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_edited_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "archived",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.PrimaryKeyConstraint("page_id"),
    )
    op.create_index(
        "ix_mirror_suggestions_author", "mirror_suggestions", ["author"]
    )
    op.create_index(
        "ix_mirror_suggestions_status", "mirror_suggestions", ["status"]
    )
    op.create_index(
        "ix_mirror_suggestions_last_edited_time",
        "mirror_suggestions",
        ["last_edited_time"],
    )
    op.create_index(
        "ix_mirror_suggestions_archived", "mirror_suggestions", ["archived"]
    )


def downgrade() -> None:
    op.drop_index("ix_mirror_suggestions_archived", table_name="mirror_suggestions")
    op.drop_index(
        "ix_mirror_suggestions_last_edited_time", table_name="mirror_suggestions"
    )
    op.drop_index("ix_mirror_suggestions_status", table_name="mirror_suggestions")
    op.drop_index("ix_mirror_suggestions_author", table_name="mirror_suggestions")
    op.drop_table("mirror_suggestions")
