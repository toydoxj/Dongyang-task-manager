"""create mirror tables (notion → postgres)

Revision ID: b1f3a2c0e201
Revises: 44f200af0b00
Create Date: 2026-04-26 11:00:00.000000

PostgreSQL 전용 (JSONB / ARRAY / GIN). SQLite 환경에서는 적용 불가.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

# revision identifiers, used by Alembic.
revision: str = "b1f3a2c0e201"
down_revision: Union[str, Sequence[str], None] = "44f200af0b00"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _str_array() -> ARRAY:
    return ARRAY(sa.String())


def upgrade() -> None:
    op.create_table(
        "mirror_projects",
        sa.Column("page_id", sa.String(), primary_key=True),
        sa.Column("code", sa.String(), nullable=False, server_default=""),
        sa.Column("master_code", sa.String(), nullable=False, server_default=""),
        sa.Column("master_project_id", sa.String(), nullable=False, server_default=""),
        sa.Column("name", sa.String(), nullable=False, server_default=""),
        sa.Column("stage", sa.String(), nullable=False, server_default=""),
        sa.Column("completed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("assignees", _str_array(), nullable=False, server_default="{}"),
        sa.Column("teams", _str_array(), nullable=False, server_default="{}"),
        sa.Column("client_relation_ids", _str_array(), nullable=False, server_default="{}"),
        sa.Column("properties", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("url", sa.String(), nullable=False, server_default=""),
        sa.Column("last_edited_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_index("ix_mirror_projects_code", "mirror_projects", ["code"])
    op.create_index(
        "ix_mirror_projects_master_id", "mirror_projects", ["master_project_id"]
    )
    op.create_index("ix_mirror_projects_stage", "mirror_projects", ["stage"])
    op.create_index("ix_mirror_projects_completed", "mirror_projects", ["completed"])
    op.create_index("ix_mirror_projects_archived", "mirror_projects", ["archived"])
    op.create_index(
        "ix_mirror_projects_last_edited", "mirror_projects", ["last_edited_time"]
    )
    op.create_index(
        "ix_mirror_projects_assignees",
        "mirror_projects",
        ["assignees"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_mirror_projects_teams",
        "mirror_projects",
        ["teams"],
        postgresql_using="gin",
    )

    op.create_table(
        "mirror_tasks",
        sa.Column("page_id", sa.String(), primary_key=True),
        sa.Column("title", sa.String(), nullable=False, server_default=""),
        sa.Column("code", sa.String(), nullable=False, server_default=""),
        sa.Column("project_ids", _str_array(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(), nullable=False, server_default=""),
        sa.Column("priority", sa.String(), nullable=False, server_default=""),
        sa.Column("progress", sa.Float(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("actual_end_date", sa.Date(), nullable=True),
        sa.Column("assignees", _str_array(), nullable=False, server_default="{}"),
        sa.Column("teams", _str_array(), nullable=False, server_default="{}"),
        sa.Column("properties", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("url", sa.String(), nullable=False, server_default=""),
        sa.Column("created_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_edited_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_index("ix_mirror_tasks_status", "mirror_tasks", ["status"])
    op.create_index("ix_mirror_tasks_end_date", "mirror_tasks", ["end_date"])
    op.create_index(
        "ix_mirror_tasks_last_edited", "mirror_tasks", ["last_edited_time"]
    )
    op.create_index("ix_mirror_tasks_archived", "mirror_tasks", ["archived"])
    op.create_index(
        "ix_mirror_tasks_project_ids",
        "mirror_tasks",
        ["project_ids"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_mirror_tasks_assignees",
        "mirror_tasks",
        ["assignees"],
        postgresql_using="gin",
    )

    op.create_table(
        "mirror_clients",
        sa.Column("page_id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False, server_default=""),
        sa.Column("category", sa.String(), nullable=False, server_default=""),
        sa.Column("properties", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("last_edited_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_index("ix_mirror_clients_name", "mirror_clients", ["name"])
    op.create_index("ix_mirror_clients_archived", "mirror_clients", ["archived"])
    op.create_index(
        "ix_mirror_clients_last_edited", "mirror_clients", ["last_edited_time"]
    )

    op.create_table(
        "mirror_master_projects",
        sa.Column("page_id", sa.String(), primary_key=True),
        sa.Column("code", sa.String(), nullable=False, server_default=""),
        sa.Column("name", sa.String(), nullable=False, server_default=""),
        sa.Column("sub_project_ids", _str_array(), nullable=False, server_default="{}"),
        sa.Column("properties", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("url", sa.String(), nullable=False, server_default=""),
        sa.Column("last_edited_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_index("ix_mirror_master_code", "mirror_master_projects", ["code"])
    op.create_index(
        "ix_mirror_master_archived", "mirror_master_projects", ["archived"]
    )
    op.create_index(
        "ix_mirror_master_last_edited",
        "mirror_master_projects",
        ["last_edited_time"],
    )
    op.create_index(
        "ix_mirror_master_subs",
        "mirror_master_projects",
        ["sub_project_ids"],
        postgresql_using="gin",
    )

    op.create_table(
        "mirror_cashflow",
        sa.Column("page_id", sa.String(), primary_key=True),
        sa.Column("kind", sa.String(), nullable=False, server_default="income"),
        sa.Column("project_ids", _str_array(), nullable=False, server_default="{}"),
        sa.Column("date", sa.Date(), nullable=True),
        sa.Column("amount", sa.Float(), nullable=False, server_default="0"),
        sa.Column("category", sa.String(), nullable=False, server_default=""),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("properties", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("last_edited_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_index("ix_mirror_cashflow_kind", "mirror_cashflow", ["kind"])
    op.create_index("ix_mirror_cashflow_date", "mirror_cashflow", ["date"])
    op.create_index("ix_mirror_cashflow_archived", "mirror_cashflow", ["archived"])
    op.create_index(
        "ix_mirror_cashflow_last_edited", "mirror_cashflow", ["last_edited_time"]
    )
    op.create_index(
        "ix_mirror_cashflow_project_ids",
        "mirror_cashflow",
        ["project_ids"],
        postgresql_using="gin",
    )

    op.create_table(
        "mirror_blocks",
        sa.Column("block_id", sa.String(), primary_key=True),
        sa.Column("parent_page_id", sa.String(), nullable=False, server_default=""),
        sa.Column("type", sa.String(), nullable=False, server_default=""),
        sa.Column("content", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_edited_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_mirror_blocks_parent", "mirror_blocks", ["parent_page_id"])
    op.create_index("ix_mirror_blocks_type", "mirror_blocks", ["type"])

    op.create_table(
        "notion_sync_state",
        sa.Column("db_kind", sa.String(), primary_key=True),
        sa.Column("last_incremental_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_full_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=False, server_default=""),
        sa.Column("last_run_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_table("notion_sync_state")
    op.drop_index("ix_mirror_blocks_type", table_name="mirror_blocks")
    op.drop_index("ix_mirror_blocks_parent", table_name="mirror_blocks")
    op.drop_table("mirror_blocks")
    op.drop_index("ix_mirror_cashflow_project_ids", table_name="mirror_cashflow")
    op.drop_index("ix_mirror_cashflow_last_edited", table_name="mirror_cashflow")
    op.drop_index("ix_mirror_cashflow_archived", table_name="mirror_cashflow")
    op.drop_index("ix_mirror_cashflow_date", table_name="mirror_cashflow")
    op.drop_index("ix_mirror_cashflow_kind", table_name="mirror_cashflow")
    op.drop_table("mirror_cashflow")
    op.drop_index("ix_mirror_master_subs", table_name="mirror_master_projects")
    op.drop_index("ix_mirror_master_last_edited", table_name="mirror_master_projects")
    op.drop_index("ix_mirror_master_archived", table_name="mirror_master_projects")
    op.drop_index("ix_mirror_master_code", table_name="mirror_master_projects")
    op.drop_table("mirror_master_projects")
    op.drop_index("ix_mirror_clients_last_edited", table_name="mirror_clients")
    op.drop_index("ix_mirror_clients_archived", table_name="mirror_clients")
    op.drop_index("ix_mirror_clients_name", table_name="mirror_clients")
    op.drop_table("mirror_clients")
    op.drop_index("ix_mirror_tasks_assignees", table_name="mirror_tasks")
    op.drop_index("ix_mirror_tasks_project_ids", table_name="mirror_tasks")
    op.drop_index("ix_mirror_tasks_archived", table_name="mirror_tasks")
    op.drop_index("ix_mirror_tasks_last_edited", table_name="mirror_tasks")
    op.drop_index("ix_mirror_tasks_end_date", table_name="mirror_tasks")
    op.drop_index("ix_mirror_tasks_status", table_name="mirror_tasks")
    op.drop_table("mirror_tasks")
    op.drop_index("ix_mirror_projects_teams", table_name="mirror_projects")
    op.drop_index("ix_mirror_projects_assignees", table_name="mirror_projects")
    op.drop_index("ix_mirror_projects_last_edited", table_name="mirror_projects")
    op.drop_index("ix_mirror_projects_archived", table_name="mirror_projects")
    op.drop_index("ix_mirror_projects_completed", table_name="mirror_projects")
    op.drop_index("ix_mirror_projects_stage", table_name="mirror_projects")
    op.drop_index("ix_mirror_projects_master_id", table_name="mirror_projects")
    op.drop_index("ix_mirror_projects_code", table_name="mirror_projects")
    op.drop_table("mirror_projects")
