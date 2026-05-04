"""mirror_* ARRAY 컬럼에 GIN 인덱스 추가 — assignee/project_id 필터 가속

Revision ID: r7p8q9r05044
Revises: q6o7p8q90504
Create Date: 2026-05-04 07:00:00.000000

list_tasks/list_projects가 .any(value) 대신 .contains([value]) 로 바뀌어
PostgreSQL `array @> ARRAY[value]` 형태로 컴파일됨 — GIN 인덱스 활용 가능.

대상:
- mirror_tasks.assignees, mirror_tasks.project_ids
- mirror_projects.assignees, mirror_projects.teams,
  mirror_projects.client_relation_ids
- mirror_cashflow.project_ids

운영 부하 영향 없음 — IF NOT EXISTS + CONCURRENTLY 미사용 (CREATE INDEX 자체로
짧게 잠금 발생하나 mirror_*는 5분 sync 외 INSERT/UPDATE 빈도 낮아 문제 없음).
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "r7p8q9r05044"
down_revision: Union[str, Sequence[str], None] = "q6o7p8q90504"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_INDEXES = [
    ("ix_mirror_tasks_assignees_gin", "mirror_tasks", "assignees"),
    ("ix_mirror_tasks_project_ids_gin", "mirror_tasks", "project_ids"),
    ("ix_mirror_projects_assignees_gin", "mirror_projects", "assignees"),
    ("ix_mirror_projects_teams_gin", "mirror_projects", "teams"),
    (
        "ix_mirror_projects_client_relation_ids_gin",
        "mirror_projects",
        "client_relation_ids",
    ),
    ("ix_mirror_cashflow_project_ids_gin", "mirror_cashflow", "project_ids"),
]


def upgrade() -> None:
    for name, table, column in _INDEXES:
        op.execute(
            f'CREATE INDEX IF NOT EXISTS "{name}" '
            f'ON "{table}" USING GIN ("{column}")'
        )


def downgrade() -> None:
    for name, _table, _column in _INDEXES:
        op.execute(f'DROP INDEX IF EXISTS "{name}"')
