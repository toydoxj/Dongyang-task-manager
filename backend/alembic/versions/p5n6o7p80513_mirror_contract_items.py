"""mirror_contract_items 테이블 추가 (공동수급/추가용역 — 발주처별 분담)

Revision ID: p5n6o7p80513
Revises: o4m5n6o70612
Create Date: 2026-05-13 10:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB  # noqa: F401

revision: str = "p5n6o7p80513"
down_revision: Union[str, Sequence[str], None] = "o4m5n6o70612"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mirror_contract_items",
        sa.Column("page_id", sa.String(), primary_key=True),
        sa.Column(
            "project_id", sa.String(), nullable=False, server_default=""
        ),
        sa.Column(
            "client_id", sa.String(), nullable=False, server_default=""
        ),
        sa.Column("label", sa.String(), nullable=False, server_default=""),
        sa.Column(
            "amount", sa.Float(), nullable=False, server_default="0"
        ),
        sa.Column("vat", sa.Float(), nullable=False, server_default="0"),
        sa.Column(
            "sort_order", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "properties",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "last_edited_time",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
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
    )
    op.create_index(
        "ix_mirror_contract_items_project_id",
        "mirror_contract_items",
        ["project_id"],
    )
    op.create_index(
        "ix_mirror_contract_items_client_id",
        "mirror_contract_items",
        ["client_id"],
    )
    op.create_index(
        "ix_mirror_contract_items_archived",
        "mirror_contract_items",
        ["archived"],
    )
    op.create_index(
        "ix_mirror_contract_items_last_edited_time",
        "mirror_contract_items",
        ["last_edited_time"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_mirror_contract_items_last_edited_time",
        table_name="mirror_contract_items",
    )
    op.drop_index(
        "ix_mirror_contract_items_archived",
        table_name="mirror_contract_items",
    )
    op.drop_index(
        "ix_mirror_contract_items_client_id",
        table_name="mirror_contract_items",
    )
    op.drop_index(
        "ix_mirror_contract_items_project_id",
        table_name="mirror_contract_items",
    )
    op.drop_table("mirror_contract_items")
