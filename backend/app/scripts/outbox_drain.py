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
from datetime import datetime, timedelta, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("outbox_drain")


_BATCH_SIZE_DEFAULT = 10
_MAX_ATTEMPTS = 8
_RETRY_BASE_S = 30  # 1차 retry 30s 후
_RETRY_MAX_S = 3600  # 최대 1시간 cap
_LOCK_OWNER = f"{socket.gethostname()}:{os.getpid()}"


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
        ):
            v = getattr(s, k, None)
            if v and k.upper() not in os.environ:
                os.environ[k.upper()] = str(v)
    except Exception:  # noqa: BLE001
        pass


def _next_attempt_delay(attempts: int) -> int:
    """exponential backoff seconds — 30s, 60s, 120s, ..., cap 3600s."""
    return min(_RETRY_BASE_S * (2 ** max(0, attempts - 1)), _RETRY_MAX_S)


async def _push_notion_op(notion, row) -> str | None:
    """outbox row를 노션에 push. 성공 시 노션 page_id 반환 (create 시).

    update/delete: 기존 page_id에 작업. None 반환 (page_id 변화 없음).
    create: 새 page 생성, page_id 반환.
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
        }
        db_id = db_id_map.get(row.aggregate_type)
        if not db_id:
            raise ValueError(
                f"create outbox row {row.id} aggregate_type={row.aggregate_type} → "
                f"notion db_id 매핑 없음"
            )
        page = await notion.create_page(db_id, row.payload)
        return str(page.get("id", "")) or None
    raise ValueError(f"unknown op: {row.op}")


async def drain_once(batch_size: int = _BATCH_SIZE_DEFAULT) -> dict:
    """1회 drain — pending/retry row를 batch 만큼 처리.

    Returns:
        {"picked": N, "sent": N, "failed": N, "dead": N}
    """
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models.notion_outbox import (
        STATUS_DEAD,
        STATUS_PROCESSING,
        STATUS_RETRY,
        STATUS_SENT,
        NotionOutbox,
        _ACTIVE_STATUSES,
    )
    from app.services.notion import get_notion

    now = datetime.now(timezone.utc)
    stats = {"picked": 0, "sent": 0, "failed": 0, "dead": 0}

    with SessionLocal() as db:
        # 1. 배치 픽업 — FOR UPDATE SKIP LOCKED로 다중 worker 안전
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

    # 2. 락 해제 후 노션 호출 (각 row 별도 transaction)
    notion = get_notion()
    for r_id in row_ids:
        with SessionLocal() as db:
            r = db.get(NotionOutbox, r_id)
            if r is None:
                continue
            try:
                new_page_id = await _push_notion_op(notion, r)
                r.status = STATUS_SENT
                r.sent_at = datetime.now(timezone.utc)
                r.locked_at = None
                r.lock_owner = None
                r.last_error = ""
                if new_page_id:
                    r.notion_page_id = new_page_id
                stats["sent"] += 1
                logger.info(
                    "outbox sent — id=%d type=%s op=%s aggregate=%s",
                    r.id, r.aggregate_type, r.op, r.aggregate_id,
                )
            except Exception as e:  # noqa: BLE001
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
                    r.next_attempt_at = datetime.now(timezone.utc) + timedelta(
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
