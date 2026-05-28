"""Outbox drain worker — PR-FO Phase 1.3.1.

`notion_outbox` 테이블의 pending/retry row를 배치 픽업해 노션 API push.
FOR UPDATE SKIP LOCKED 패턴으로 multi-worker 안전. 실패 시 exponential backoff.

호출 예:
  python -m app.scripts.outbox_drain           # 1회 drain
  python -m app.scripts.outbox_drain --batch 20

Render cron으로 1분 주기 호출. write endpoint enqueue 활성화는 PR-FO+1.
인프라만 깔린 상태에선 outbox에 row가 없어 즉시 종료.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import socket
import sys
from datetime import UTC, datetime, timedelta

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("outbox_drain")


_BATCH_SIZE_DEFAULT = 10
_MAX_ATTEMPTS = 8
_RETRY_BASE_S = 30  # 1차 retry 30s 후
_RETRY_MAX_S = 3600  # 최대 1시간 cap
_PROCESSING_STALE_AFTER = timedelta(minutes=15)
_LOCK_OWNER = f"{socket.gethostname()}:{os.getpid()}"
_ARCHIVED_TARGET_ERROR = "Can't edit block that is archived"
_LOCAL_RELATION_PREFIXES = (
    ("local_client_", "clients"),
    ("local_contract_item_", "contract_items"),
)


def _bootstrap_env_from_settings() -> None:
    """pydantic-settings가 .env에서 로드한 값을 os.environ에 inject."""
    try:
        from app.settings import get_settings

        s = get_settings()
        for k in (
            "database_url",
            "notion_api_key",
            "notion_db_seal_requests",
            "notion_db_tasks",
            "notion_db_projects",
            "notion_db_clients",
            "notion_db_sales",
            "notion_db_master",
            "notion_db_cashflow",
            "notion_db_expense",
            "notion_db_contract_items",
            "notion_db_suggestions",
        ):
            v = getattr(s, k, None)
            if v and k.upper() not in os.environ:
                os.environ[k.upper()] = str(v)
    except Exception:  # noqa: BLE001
        pass


def _next_attempt_delay(attempts: int) -> int:
    """exponential backoff seconds — 30s, 60s, 120s, ..., cap 3600s."""
    return min(_RETRY_BASE_S * (2 ** max(0, attempts - 1)), _RETRY_MAX_S)


def _mark_stale_processing_rows_retry(rows, now: datetime) -> int:
    """worker 재시작 등으로 고착된 processing row를 회수."""
    from app.models.notion_outbox import STATUS_RETRY

    count = 0
    for row in rows:
        row.status = STATUS_RETRY
        row.locked_at = None
        row.lock_owner = None
        row.next_attempt_at = now
        row.last_error = "stale processing lock recovered"
        count += 1
    return count


def _is_archived_target_error(exc: Exception) -> bool:
    """Notion의 archived page/block 수정 거부 오류인지 판별."""
    return _ARCHIVED_TARGET_ERROR in str(exc)


def _mirror_table_for_archive_check(aggregate_type: str):
    """outbox aggregate_type에 대응하는 mirror ORM 모델."""
    from app.models.mirror import (
        MirrorCashflow,
        MirrorClient,
        MirrorContractItem,
        MirrorMaster,
        MirrorProject,
        MirrorSales,
        MirrorSealRequest,
        MirrorSuggestion,
        MirrorTask,
    )

    return {
        "projects": MirrorProject,
        "tasks": MirrorTask,
        "clients": MirrorClient,
        "master": MirrorMaster,
        "cashflow": MirrorCashflow,
        "expense": MirrorCashflow,
        "contract_items": MirrorContractItem,
        "sales": MirrorSales,
        "seal_requests": MirrorSealRequest,
        "suggestions": MirrorSuggestion,
    }.get(aggregate_type)


def _mirror_row_is_archived(db, row) -> bool:
    """mirror row가 이미 archived면 Notion archived target 오류를 성공 상태로 본다."""
    table = _mirror_table_for_archive_check(row.aggregate_type)
    if table is None:
        return False
    page_id = row.aggregate_id or row.notion_page_id
    if not page_id:
        return False
    mirror_row = db.get(table, page_id)
    return bool(mirror_row is not None and mirror_row.archived)


def _should_skip_archived_target(db, row, exc: Exception) -> bool:
    """목표 상태가 이미 mirror에 반영된 archived target 오류인지 판별."""
    from app.models.notion_outbox import OP_DELETE, OP_UPDATE

    return (
        row.op in (OP_UPDATE, OP_DELETE)
        and _is_archived_target_error(exc)
        and _mirror_row_is_archived(db, row)
    )


def _aggregate_type_for_local_relation_id(relation_id: str) -> str | None:
    """relation payload 안의 local id가 어느 aggregate create인지 판별."""
    for prefix, aggregate_type in _LOCAL_RELATION_PREFIXES:
        if relation_id.startswith(prefix):
            return aggregate_type
    return None


def _collect_local_relation_ids(payload: object) -> set[str]:
    """Notion properties payload에서 아직 확정되지 않은 local relation id 수집."""
    ids: set[str] = set()
    if isinstance(payload, dict):
        relation = payload.get("relation")
        if isinstance(relation, list):
            for item in relation:
                if not isinstance(item, dict):
                    continue
                relation_id = item.get("id")
                if (
                    isinstance(relation_id, str)
                    and _aggregate_type_for_local_relation_id(relation_id)
                ):
                    ids.add(relation_id)
        for value in payload.values():
            ids.update(_collect_local_relation_ids(value))
    elif isinstance(payload, list):
        for item in payload:
            ids.update(_collect_local_relation_ids(item))
    return ids


def _replace_relation_id(
    payload: object, old_id: str, new_id: str
) -> tuple[object, bool]:
    """Notion relation 배열 안의 id만 치환하고 새 payload 객체를 반환."""
    if isinstance(payload, dict):
        changed = False
        next_payload = dict(payload)
        relation = payload.get("relation")
        if isinstance(relation, list):
            next_relation: list[object] = []
            relation_changed = False
            for item in relation:
                if isinstance(item, dict) and item.get("id") == old_id:
                    next_item = dict(item)
                    next_item["id"] = new_id
                    next_relation.append(next_item)
                    relation_changed = True
                else:
                    next_relation.append(item)
            if relation_changed:
                next_payload["relation"] = next_relation
                changed = True

        for key, value in payload.items():
            if key == "relation" and isinstance(relation, list):
                continue
            next_value, value_changed = _replace_relation_id(
                value, old_id, new_id
            )
            if value_changed:
                next_payload[key] = next_value
                changed = True
        return (next_payload, True) if changed else (payload, False)

    if isinstance(payload, list):
        changed = False
        next_payload: list[object] = []
        for item in payload:
            next_item, item_changed = _replace_relation_id(item, old_id, new_id)
            next_payload.append(next_item)
            changed = changed or item_changed
        return (next_payload, True) if changed else (payload, False)

    return payload, False


def _scalar_rows(result) -> list[object]:
    """SQLAlchemy Result 또는 테스트 fake result에서 scalar row 목록 추출."""
    scalars = getattr(result, "scalars", None)
    if callable(scalars):
        return list(scalars().all())
    all_rows = getattr(result, "all", None)
    if callable(all_rows):
        return list(all_rows())
    return []


def _sent_page_id_for_local_id(
    db, aggregate_type: str, local_id: str
) -> str | None:
    """local create outbox가 성공하며 확보한 실제 Notion page_id 조회."""
    from sqlalchemy import select

    from app.models.notion_outbox import OP_CREATE, STATUS_SENT, NotionOutbox

    return db.execute(
        select(NotionOutbox.notion_page_id)
        .where(
            NotionOutbox.aggregate_type == aggregate_type,
            NotionOutbox.aggregate_id == local_id,
            NotionOutbox.op == OP_CREATE,
            NotionOutbox.status == STATUS_SENT,
            NotionOutbox.notion_page_id.is_not(None),
        )
        .order_by(NotionOutbox.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def _resolve_local_relation_payloads(db, row) -> None:
    """push 직전 payload의 local relation id를 실제 page id로 해소."""
    from app.models.notion_outbox import OP_CREATE, OP_UPDATE

    if row.op not in (OP_CREATE, OP_UPDATE):
        return
    payload = row.payload or {}
    local_ids = _collect_local_relation_ids(payload)
    for local_id in sorted(local_ids):
        aggregate_type = _aggregate_type_for_local_relation_id(local_id)
        if aggregate_type is None:
            continue
        real_id = _sent_page_id_for_local_id(db, aggregate_type, local_id)
        if not real_id:
            raise ValueError(f"relation local id not resolved: {local_id}")
        _rewrite_local_relation_references(db, aggregate_type, local_id, real_id)
        payload, changed = _replace_relation_id(payload, local_id, real_id)
        if changed and isinstance(payload, dict):
            row.payload = payload


def _rewrite_active_outbox_relation_refs(db, old_id: str, new_id: str) -> None:
    """아직 push 전인 outbox payload의 local relation id를 실제 id로 치환."""
    from sqlalchemy import select

    from app.models.notion_outbox import _ACTIVE_STATUSES, NotionOutbox

    rows = _scalar_rows(
        db.execute(
            select(NotionOutbox).where(NotionOutbox.status.in_(_ACTIVE_STATUSES))
        )
    )
    for outbox_row in rows:
        payload = getattr(outbox_row, "payload", None) or {}
        next_payload, changed = _replace_relation_id(payload, old_id, new_id)
        if changed and isinstance(next_payload, dict):
            outbox_row.payload = next_payload


def _rewrite_cashflow_contract_item_refs(
    db, old_id: str, new_id: str, now: datetime
) -> None:
    """수금 mirror의 계약항목 relation을 local id에서 실제 id로 보정."""
    from sqlalchemy import select

    from app.models.mirror import MirrorCashflow

    rows = _scalar_rows(
        db.execute(
            select(MirrorCashflow).where(MirrorCashflow.archived.is_(False))
        )
    )
    for cashflow_row in rows:
        props = getattr(cashflow_row, "properties", None) or {}
        next_props, changed = _replace_relation_id(props, old_id, new_id)
        if changed and isinstance(next_props, dict):
            cashflow_row.properties = next_props
            cashflow_row.synced_at = now


def _rewrite_contract_item_client_refs(
    db, old_id: str, new_id: str, now: datetime
) -> None:
    """계약항목 mirror의 발주처 relation을 local id에서 실제 id로 보정."""
    from sqlalchemy import select

    from app.models.mirror import MirrorContractItem

    rows = _scalar_rows(
        db.execute(
            select(MirrorContractItem).where(
                MirrorContractItem.archived.is_(False)
            )
        )
    )
    for contract_item_row in rows:
        changed = False
        if getattr(contract_item_row, "client_id", "") == old_id:
            contract_item_row.client_id = new_id
            changed = True
        props = getattr(contract_item_row, "properties", None) or {}
        next_props, props_changed = _replace_relation_id(props, old_id, new_id)
        if props_changed and isinstance(next_props, dict):
            contract_item_row.properties = next_props
            changed = True
        if changed:
            contract_item_row.synced_at = now


def _rewrite_local_relation_references(
    db, aggregate_type: str, old_id: str, new_id: str
) -> None:
    """local create 완료 시 이미 저장된 하위 참조를 실제 Notion id로 동기화."""
    if old_id == new_id:
        return
    now = datetime.now(UTC)
    if aggregate_type == "contract_items":
        _rewrite_cashflow_contract_item_refs(db, old_id, new_id, now)
    elif aggregate_type == "clients":
        _rewrite_contract_item_client_refs(db, old_id, new_id, now)
    _rewrite_active_outbox_relation_refs(db, old_id, new_id)


def _finalize_create_mirror(db, row, page: dict) -> None:
    """create 성공 후 local mirror row를 실제 Notion page row로 reconcile."""
    from app.models.notion_outbox import OP_CREATE

    if row.op != OP_CREATE:
        return
    finalize_targets = {
        "cashflow": ("MirrorCashflow", "cashflow"),
        "clients": ("MirrorClient", "clients"),
        "contract_items": ("MirrorContractItem", "contract_items"),
        "suggestions": ("MirrorSuggestion", "suggestions"),
    }
    target = finalize_targets.get(row.aggregate_type)
    if target is None:
        return
    new_page_id = str(page.get("id", "") or "")
    if not new_page_id:
        return
    from app.models import mirror as M
    from app.services.sync import get_sync

    table = getattr(M, target[0])
    local_row = db.get(table, row.aggregate_id)
    if local_row is not None and local_row.page_id != new_page_id:
        local_row.archived = True
        local_row.synced_at = datetime.now(UTC)
    _rewrite_local_relation_references(
        db, row.aggregate_type, row.aggregate_id, new_page_id
    )
    get_sync().upsert_in_session(db, target[1], page)


async def _push_notion_op(notion, row) -> dict | None:
    """outbox row를 노션에 push. 성공 시 create page dict 반환.

    update/delete: 기존 page_id에 작업. None 반환 (page_id 변화 없음).
    create: 새 page 생성, page dict 반환.
    """
    from app.models.notion_outbox import OP_CREATE, OP_DELETE, OP_UPDATE

    if row.op == OP_UPDATE:
        if not row.notion_page_id:
            raise ValueError(f"update outbox row {row.id}에 notion_page_id 없음")
        await notion.update_page(row.notion_page_id, row.payload)
        return None
    if row.op == OP_DELETE:
        if not row.notion_page_id:
            raise ValueError(f"delete outbox row {row.id}에 notion_page_id 없음")
        # archive — notion SDK pages.update의 archived=True 호출은 NotionService에 없으므로
        # 직접 client 사용. user_facing=False default (background path).
        await asyncio.to_thread(
            notion._client.pages.update,
            page_id=row.notion_page_id,
            archived=True,
        )
        return None
    if row.op == OP_CREATE:
        # aggregate_type → notion db_id 매핑. PR-FO+1에서 enqueue 활성화 시 사용.
        from app.settings import get_settings

        s = get_settings()
        db_id_map = {
            "seal_requests": s.notion_db_seal_requests,
            "tasks": s.notion_db_tasks,
            "projects": s.notion_db_projects,
            "clients": s.notion_db_clients,
            "sales": s.notion_db_sales,
            "master": s.notion_db_master,
            "cashflow": s.notion_db_cashflow,
            "expense": s.notion_db_expense,
            "contract_items": s.notion_db_contract_items,
            "suggestions": s.notion_db_suggestions,
        }
        db_id = db_id_map.get(row.aggregate_type)
        if not db_id:
            raise ValueError(
                f"create outbox row {row.id} aggregate_type={row.aggregate_type} → "
                f"notion db_id 매핑 없음"
            )
        page = await notion.create_page(db_id, row.payload)
        return page
    raise ValueError(f"unknown op: {row.op}")


async def drain_once(batch_size: int = _BATCH_SIZE_DEFAULT) -> dict:
    """1회 drain — pending/retry row를 batch 만큼 처리.

    Returns:
        {"picked": N, "sent": N, "failed": N, "dead": N, "recovered": N}
    """
    from sqlalchemy import or_, select

    from app.db import SessionLocal
    from app.models.notion_outbox import (
        _ACTIVE_STATUSES,
        STATUS_DEAD,
        STATUS_PROCESSING,
        STATUS_RETRY,
        STATUS_SENT,
        NotionOutbox,
    )
    from app.services.notion import get_notion

    now = datetime.now(UTC)
    stats = {"picked": 0, "sent": 0, "failed": 0, "dead": 0, "recovered": 0}

    with SessionLocal() as db:
        # 1. stale processing 회수 — 이전 worker가 죽은 뒤 남은 lock 안전망.
        stale_before = now - _PROCESSING_STALE_AFTER
        stale_stmt = (
            select(NotionOutbox)
            .where(NotionOutbox.status == STATUS_PROCESSING)
            .where(
                or_(
                    NotionOutbox.locked_at.is_(None),
                    NotionOutbox.locked_at <= stale_before,
                )
            )
            .order_by(NotionOutbox.locked_at)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        stale_rows = list(db.execute(stale_stmt).scalars().all())
        stats["recovered"] = _mark_stale_processing_rows_retry(
            stale_rows, now
        )
        if stats["recovered"]:
            logger.warning(
                "outbox stale processing recovered — count=%d",
                stats["recovered"],
            )

        # 2. 배치 픽업 — FOR UPDATE SKIP LOCKED로 다중 worker 안전
        stmt = (
            select(NotionOutbox)
            .where(NotionOutbox.status.in_([
                # pending + retry만 (processing은 다른 worker 진행 중)
                _ACTIVE_STATUSES[0],  # pending
                _ACTIVE_STATUSES[2],  # retry
            ]))
            .where(NotionOutbox.next_attempt_at <= now)
            .order_by(NotionOutbox.next_attempt_at)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        rows = list(db.execute(stmt).scalars().all())
        if not rows:
            if stats["recovered"]:
                db.commit()
            return stats

        stats["picked"] = len(rows)
        # PR-FP/2: commit 후 row 객체가 detached됨. r.id 등 attribute access가
        # expire load를 트리거해 DetachedInstanceError 발생. ids는 commit 전에
        # 미리 추출 (PK라 이미 set돼 있음). 이후 루프는 detached row를 사용 안 함.
        row_ids = [r.id for r in rows]
        # status='processing' + lock 표시
        for r in rows:
            r.status = STATUS_PROCESSING
            r.locked_at = now
            r.lock_owner = _LOCK_OWNER
        db.commit()

    # 3. 락 해제 후 노션 호출 (각 row 별도 transaction)
    notion = get_notion()
    for r_id in row_ids:
        with SessionLocal() as db:
            r = db.get(NotionOutbox, r_id)
            if r is None:
                continue
            try:
                _resolve_local_relation_payloads(db, r)
                new_page = await _push_notion_op(notion, r)
                r.status = STATUS_SENT
                r.sent_at = datetime.now(UTC)
                r.locked_at = None
                r.lock_owner = None
                r.last_error = ""
                if new_page:
                    new_page_id = str(new_page.get("id", "") or "")
                    r.notion_page_id = new_page_id
                    _finalize_create_mirror(db, r, new_page)
                stats["sent"] += 1
                logger.info(
                    "outbox sent — id=%d type=%s op=%s aggregate=%s",
                    r.id, r.aggregate_type, r.op, r.aggregate_id,
                )
            except Exception as e:  # noqa: BLE001
                if _should_skip_archived_target(db, r, e):
                    r.status = STATUS_SENT
                    r.sent_at = datetime.now(UTC)
                    r.locked_at = None
                    r.lock_owner = None
                    r.last_error = "skipped: archived target already reflected in mirror"
                    stats["sent"] += 1
                    logger.info(
                        "outbox skipped archived target — id=%d type=%s op=%s aggregate=%s",
                        r.id, r.aggregate_type, r.op, r.aggregate_id,
                    )
                else:
                    r.attempts += 1
                    r.last_error = repr(e)[:1000]
                    r.locked_at = None
                    r.lock_owner = None
                    if r.attempts >= _MAX_ATTEMPTS:
                        r.status = STATUS_DEAD
                        stats["dead"] += 1
                        logger.error(
                            "outbox DEAD — id=%d attempts=%d type=%s op=%s aggregate=%s last=%s",
                            r.id, r.attempts, r.aggregate_type, r.op,
                            r.aggregate_id, repr(e)[:200],
                        )
                    else:
                        r.status = STATUS_RETRY
                        delay = _next_attempt_delay(r.attempts)
                        r.next_attempt_at = datetime.now(UTC) + timedelta(
                            seconds=delay
                        )
                        stats["failed"] += 1
                        logger.warning(
                            "outbox retry — id=%d attempts=%d delay=%ds last=%s",
                            r.id, r.attempts, delay, repr(e)[:200],
                        )
            db.commit()

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Notion outbox drain worker")
    parser.add_argument(
        "--batch", type=int, default=_BATCH_SIZE_DEFAULT,
        help=f"한 번에 처리할 row 수 (default {_BATCH_SIZE_DEFAULT})",
    )
    args = parser.parse_args()

    _bootstrap_env_from_settings()
    stats = asyncio.run(drain_once(batch_size=args.batch))
    logger.info("drain done — %s", stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
