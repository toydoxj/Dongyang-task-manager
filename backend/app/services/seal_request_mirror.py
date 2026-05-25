"""seal_requests mirror-first helper — PR-FP Phase 1.3.2.

write endpoint이 mirror direct update + outbox enqueue로 노션 호출을 사용자 응답
path에서 제거하기 위한 공통 helper. update_props(노션 raw format) 받아 mirror.properties
병합 + 정규화 필드(title/status/seal_type/requester/project_ids) 동기화.

`sync.py._upsert_seal_request`의 추출 로직과 동일 — DRY 목적 helper로 추출.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.models import mirror as M
from app.services import notion_props as P
from app.services import seal_logic as SL


def normalize_mirror_fields(props: dict[str, Any]) -> dict[str, Any]:
    """props dict(노션 raw format)에서 mirror.title/status/seal_type/requester/project_ids 추출.

    sync.py._upsert_seal_request와 동일 로직. write endpoint이 mirror direct update 시
    이 helper를 사용해 정규화 필드 동기화.
    """
    title_text = ""
    for prop in props.values():
        if isinstance(prop, dict) and prop.get("type") == "title":
            title_text = "".join(
                seg.get("plain_text", "") or seg.get("text", {}).get("content", "")
                for seg in (prop.get("title") or [])
            ).strip()
            break

    return {
        "title": title_text,
        "seal_type": SL.normalize_type(P.select_name(props, "날인유형")) or "",
        "status": SL.normalize_status(P.select_name(props, "상태")) or "",
        "requester": P.rich_text(props, "요청자"),
        "project_ids": list(P.relation_ids(props, "프로젝트")),
    }


def merge_props(existing: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    """노션 raw props dict 병합. updates 키가 있으면 덮어쓰기.

    노션 raw format(`{"date": None}` 등)을 그대로 사용 — drain worker가 노션에 push할 때
    `notion.update_page(page_id, payload)`로 그대로 전달.
    """
    out = dict(existing or {})
    out.update(updates)
    return out


def apply_update_to_mirror(
    row: M.MirrorSealRequest,
    update_props: dict[str, Any],
) -> M.MirrorSealRequest:
    """mirror row에 update_props 적용 — properties 병합 + 정규화 필드 동기화 +
    last_edited_time 갱신.

    `db.commit()`은 호출자 책임 (outbox enqueue와 같은 transaction에서 묶기 위함).
    """
    merged = merge_props(row.properties or {}, update_props)
    row.properties = merged

    norm = normalize_mirror_fields(merged)
    # 정규화 필드는 최신값 (update에 포함됐든 기존값이든)
    row.title = norm["title"]
    row.seal_type = norm["seal_type"]
    row.status = norm["status"]
    row.requester = norm["requester"]
    row.project_ids = norm["project_ids"]
    row.last_edited_time = datetime.now(timezone.utc)
    return row
