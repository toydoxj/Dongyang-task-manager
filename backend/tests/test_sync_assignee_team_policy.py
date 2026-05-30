"""담당자 기준 담당팀 산출/보존 정책 회귀 테스트."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.sync import NotionSyncService


class _Rows:
    def __init__(self, rows: list[tuple[str, str]]) -> None:
        self.rows = rows

    def all(self) -> list[tuple[str, str]]:
        return self.rows


def _service_with_employee_rows(
    rows: list[tuple[str, str]],
) -> tuple[NotionSyncService, MagicMock]:
    sync = NotionSyncService.__new__(NotionSyncService)
    db = MagicMock()
    db.execute.return_value = _Rows(rows)
    return sync, db


def test_assignee_team_policy_derives_teams_from_employee_table() -> None:
    """담당자가 있으면 직원 명부의 team으로 담당팀을 산출한다."""
    sync, db = _service_with_employee_rows(
        [
            ("김구조", "구조1팀"),
            ("박진단", "진단팀"),
        ]
    )
    props = {
        "담당자": {
            "multi_select": [
                {"name": "김구조"},
                {"name": "박진단"},
                {"name": "김구조"},
            ]
        },
        "담당팀": {"multi_select": []},
    }

    teams, next_props = sync._apply_assignee_team_policy(
        db,
        object,
        "proj-1",
        props,
        assignees=["김구조", "박진단", "김구조"],
        teams=[],
        preserve_without_assignees=True,
    )

    assert teams == ["구조1팀", "진단팀"]
    assert next_props["담당팀"] == {
        "multi_select": [{"name": "구조1팀"}, {"name": "진단팀"}]
    }
    db.get.assert_not_called()


def test_assignee_team_policy_preserves_teams_when_unassigned_sync_pull() -> None:
    """담당자가 없는 sync pull에서는 기존 담당팀을 지우지 않는다."""
    sync, db = _service_with_employee_rows([])
    old_team_prop = {
        "type": "multi_select",
        "multi_select": [{"name": "구조2팀"}],
    }
    db.get.return_value = SimpleNamespace(
        archived=False,
        teams=["구조2팀"],
        properties={"담당팀": old_team_prop},
    )
    props = {
        "담당자": {"multi_select": []},
        "담당팀": {"multi_select": []},
    }

    teams, next_props = sync._apply_assignee_team_policy(
        db,
        object,
        "proj-1",
        props,
        assignees=[],
        teams=[],
        preserve_without_assignees=True,
    )

    assert teams == ["구조2팀"]
    assert next_props["담당팀"] == old_team_prop


def test_assignee_team_policy_allows_explicit_team_clear() -> None:
    """명시 편집 경로는 담당팀 비우기를 막지 않는다."""
    sync, db = _service_with_employee_rows([])
    props = {
        "담당자": {"multi_select": []},
        "담당팀": {"multi_select": []},
    }

    teams, next_props = sync._apply_assignee_team_policy(
        db,
        object,
        "proj-1",
        props,
        assignees=[],
        teams=[],
        preserve_without_assignees=False,
    )

    assert teams == []
    assert next_props is props
    db.get.assert_not_called()
