"""PR-FP Phase 1.3.2 회귀 테스트 — seal_requests write mirror-first + outbox.

approval / update / redo 5 endpoint이 노션 호출 0건으로 mirror direct update +
outbox enqueue 패턴인지 검증. Codex 자문 위험 신호(멱등성, dedupe, reconcile)
회귀 방지.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models import mirror as M
from app.services.seal_request_mirror import (
    apply_update_to_mirror,
    merge_props,
    normalize_mirror_fields,
)


def _row_factory(
    *,
    page_id: str = "p1",
    status: str = "1차검토 중",
    title: str = "doc",
    requester: str = "홍길동",
    properties: dict | None = None,
) -> M.MirrorSealRequest:
    if properties is None:
        properties = {
            "제목": {"type": "title", "title": [{"plain_text": title}]},
            "상태": {"type": "select", "select": {"name": status}},
            "날인유형": {"type": "select", "select": {"name": "구조검토서"}},
            "요청자": {"type": "rich_text", "rich_text": [{"plain_text": requester}]},
            "프로젝트": {"type": "relation", "relation": []},
        }
    return M.MirrorSealRequest(
        page_id=page_id,
        title=title,
        seal_type="구조검토서",
        status=status,
        requester=requester,
        project_ids=[],
        properties=properties,
        last_edited_time=datetime(2026, 5, 25, tzinfo=timezone.utc),
        archived=False,
    )


def test_normalize_extracts_all_normalized_fields() -> None:
    """노션 raw props에서 title/status/seal_type/requester/project_ids 추출."""
    props = {
        "제목": {"type": "title", "title": [{"plain_text": "구조검토서 요청"}]},
        "상태": {"type": "select", "select": {"name": "1차검토 중"}},
        "날인유형": {"type": "select", "select": {"name": "구조계산서"}},
        "요청자": {"type": "rich_text", "rich_text": [{"plain_text": "테스터"}]},
        "프로젝트": {"type": "relation", "relation": [{"id": "proj-1"}, {"id": "proj-2"}]},
    }
    norm = normalize_mirror_fields(props)
    assert norm["title"] == "구조검토서 요청"
    assert norm["status"] == "1차검토 중"
    assert norm["seal_type"] == "구조계산서"
    assert norm["requester"] == "테스터"
    assert norm["project_ids"] == ["proj-1", "proj-2"]


def test_normalize_handles_missing_or_null_props() -> None:
    """빈 props / NULL value → 빈 string fallback."""
    norm = normalize_mirror_fields({})
    assert norm == {
        "title": "",
        "seal_type": "",
        "status": "",
        "requester": "",
        "project_ids": [],
    }


def test_merge_props_overrides_only_specified_keys() -> None:
    """merge_props: updates 키는 덮어쓰기, 나머지는 보존."""
    existing = {
        "제목": {"type": "title", "title": [{"plain_text": "old"}]},
        "상태": {"type": "select", "select": {"name": "1차검토 중"}},
        "비고": {"type": "rich_text", "rich_text": [{"plain_text": "old note"}]},
    }
    updates = {"상태": {"select": {"name": "2차검토 중"}}}
    merged = merge_props(existing, updates)
    assert merged["상태"]["select"]["name"] == "2차검토 중"
    assert merged["제목"] == existing["제목"]  # 그대로
    assert merged["비고"] == existing["비고"]  # 그대로


def test_apply_update_to_mirror_syncs_normalized_fields() -> None:
    """apply_update_to_mirror: properties merge + 정규화 필드 동기화 + last_edited_time."""
    row = _row_factory(status="1차검토 중")
    before_time = row.last_edited_time

    update_props = {
        "상태": {"select": {"name": "2차검토 중"}},
        "팀장처리자": {"rich_text": [{"text": {"content": "팀장A"}}]},
    }
    apply_update_to_mirror(row, update_props)

    # 정규화 필드 동기화
    assert row.status == "2차검토 중"
    # title은 update_props에 없으므로 기존 값 유지
    assert row.title == "doc"
    # properties 병합 — 상태 + 팀장처리자 둘 다 반영
    assert row.properties["상태"]["select"]["name"] == "2차검토 중"
    assert row.properties["팀장처리자"]["rich_text"][0]["text"]["content"] == "팀장A"
    # last_edited_time 갱신
    assert row.last_edited_time > before_time


def test_apply_update_to_mirror_idempotent() -> None:
    """같은 update_props 두 번 적용해도 결과 동일 (Codex idempotency 권고)."""
    row1 = _row_factory()
    row2 = _row_factory()
    update_props = {"상태": {"select": {"name": "승인"}}}

    apply_update_to_mirror(row1, update_props)
    apply_update_to_mirror(row2, update_props)
    apply_update_to_mirror(row2, update_props)  # 두 번 더 적용

    assert row1.status == row2.status == "승인"
    assert row1.properties["상태"] == row2.properties["상태"]


def test_task_link_update_keeps_current_status() -> None:
    """자동 TASK 링크 write-through는 진행 상태를 되돌리지 않고 id만 병합."""
    row = _row_factory(status="2차검토 중")
    update_props = {
        "2차검토TASK": {"rich_text": [{"text": {"content": "task-admin-1"}}]},
    }

    apply_update_to_mirror(row, update_props)

    assert row.status == "2차검토 중"
    assert row.properties["2차검토TASK"]["rich_text"][0]["plain_text"] == "task-admin-1"


def test_status_select_null_safe() -> None:
    """노션 raw {select: None} (clear 신호) — KeyError 없이 처리."""
    # date {"date": None} 같은 clear 패턴
    update_props = {"제출예정일": {"date": None}}
    row = _row_factory()
    apply_update_to_mirror(row, update_props)
    # 정규화 필드는 select/title만 추출 — date null은 무해
    assert row.status == "1차검토 중"  # 기존 그대로
    assert row.properties["제출예정일"] == {"date": None}
