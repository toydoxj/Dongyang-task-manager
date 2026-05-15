"""mirror_seal_requests 신설 (PR-CL: dashboard slow 근본 fix)

Revision ID: e0c1d2e05015
Revises: d9b0c1d05011
Create Date: 2026-05-15 09:00:00.000000

날인요청을 mirror DB에 sync. pending-count + 추후 dashboard endpoint들이 노션
직접 호출 대신 mirror count 사용 → request path에서 노션 의존 제거.
당장은 status 카운트에 필요한 최소 컬럼만.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "e0c1d2e05015"
down_revision: Union[str, Sequence[str], None] = "d9b0c1d05011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mirror_seal_requests",
        sa.Column("page_id", sa.String(), primary_key=True),
        sa.Column("title", sa.String(), nullable=False, server_default=""),
        sa.Column("seal_type", sa.String(), nullable=False, server_default=""),
        sa.Column("status", sa.String(), nullable=False, server_default=""),
        sa.Column("requester", sa.String(), nullable=False, server_default=""),
        sa.Column(
            "project_ids",
            pg.ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("created_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_edited_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "archived",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_index(
        "ix_mirror_seal_requests_seal_type",
        "mirror_seal_requests",
        ["seal_type"],
    )
    op.create_index(
        "ix_mirror_seal_requests_status",
        "mirror_seal_requests",
        ["status"],
    )
    op.create_index(
        "ix_mirror_seal_requests_requester",
        "mirror_seal_requests",
        ["requester"],
    )
    op.create_index(
        "ix_mirror_seal_requests_last_edited_time",
        "mirror_seal_requests",
        ["last_edited_time"],
    )
    op.create_index(
        "ix_mirror_seal_requests_archived",
        "mirror_seal_requests",
        ["archived"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_mirror_seal_requests_archived", table_name="mirror_seal_requests"
    )
    op.drop_index(
        "ix_mirror_seal_requests_last_edited_time",
        table_name="mirror_seal_requests",
    )
    op.drop_index(
        "ix_mirror_seal_requests_requester",
        table_name="mirror_seal_requests",
    )
    op.drop_index(
        "ix_mirror_seal_requests_status",
        table_name="mirror_seal_requests",
    )
    op.drop_index(
        "ix_mirror_seal_requests_seal_type",
        table_name="mirror_seal_requests",
    )
    op.drop_table("mirror_seal_requests")
