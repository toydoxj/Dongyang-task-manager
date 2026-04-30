"""노션 → Postgres 미러 동기화 서비스.

read-path는 mirror 테이블만 사용. 노션 변경 후 5분 내 반영 (incremental sync).
앱 내 쓰기는 write-through로 즉시 mirror upsert (라우터에서 직접 호출).
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import mirror as M
from app.models.cashflow import CashflowEntry
from app.models.project import Project
from app.models.task import Task
from app.services import notion_props as P
from app.services.notion import NotionService
from app.settings import Settings, get_settings

logger = logging.getLogger("notion.sync")

SyncKind = Literal[
    "projects", "tasks", "clients", "master", "cashflow", "expense"
]
ALL_KINDS: tuple[SyncKind, ...] = (
    "projects",
    "tasks",
    "clients",
    "master",
    "cashflow",
    "expense",
)

# incremental query lookback. since를 sync 시작 시각으로 박아도 노션 인덱싱
# 지연·clock skew로 boundary 페이지가 빠질 수 있어 60초 overlap. upsert가
# idempotent라 중복 수집은 안전.
_INCREMENTAL_OVERLAP = timedelta(seconds=60)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        # 노션은 'Z' 또는 '+00:00' 둘 다 사용
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_date(s: str | None):
    if not s:
        return None
    try:
        # 'YYYY-MM-DD' 또는 ISO datetime → date
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return datetime.strptime(s, "%Y-%m-%d").date()
        except ValueError:
            return None


class NotionSyncService:
    def __init__(
        self,
        notion: NotionService,
        session_factory: Callable[[], Session],
        settings: Settings | None = None,
    ) -> None:
        self.notion = notion
        self.session_factory = session_factory
        self.settings = settings or get_settings()
        # per-kind lock — 수동 /api/cron/sync 와 5분 scheduler가 같은 kind를
        # 동시 실행해 cursor 충돌하는 일 방지. 직렬화는 kind별로만.
        self._kind_locks: dict[str, asyncio.Lock] = {}

    def _kind_lock(self, kind: str) -> asyncio.Lock:
        # __new__로 생성된 인스턴스(테스트)에서 _kind_locks가 없을 수 있어 lazy init.
        locks = getattr(self, "_kind_locks", None)
        if locks is None:
            locks = {}
            self._kind_locks = locks
        lock = locks.get(kind)
        if lock is None:
            lock = asyncio.Lock()
            locks[kind] = lock
        return lock

    # ── 진입점 ──

    async def sync_all(self, *, full: bool = False) -> dict[str, int]:
        """모든 kind sync. 반환: kind → 동기화된 페이지 수."""
        result: dict[str, int] = {}
        for kind in ALL_KINDS:
            try:
                count = await self.sync_kind(kind, full=full)
                result[kind] = count
            except Exception as exc:  # noqa: BLE001
                logger.exception("sync %s 실패", kind)
                result[kind] = -1
                self._record_error(kind, str(exc))
        return result

    async def sync_kind(self, kind: SyncKind, *, full: bool = False) -> int:
        db_id = self._db_id_for(kind)
        if not db_id:
            logger.warning("sync %s: DB ID 미설정", kind)
            return 0

        async with self._kind_lock(kind):
            # since는 sync 시작 시각으로 갱신해야 진행 도중(start~end) 노션에 추가된
            # 페이지가 다음 incremental에서 누락되지 않음. 여기서 시작 시각 capture.
            start_time = _utcnow()
            since = None if full else self._get_since(kind)
            filt: dict[str, Any] | None = None
            if since:
                filt = {
                    "timestamp": "last_edited_time",
                    "last_edited_time": {
                        "after": (since - _INCREMENTAL_OVERLAP).isoformat()
                    },
                }
            # 가장 오래된 것부터 처리하면 부분 실패 시 since 진행 안전
            sorts = [{"timestamp": "last_edited_time", "direction": "ascending"}]
            pages = await self.notion.query_all(db_id, filter=filt, sorts=sorts)

            # 100건 단위로 commit — 단일 transaction이 row lock을 오래 잡으면
            # /api/projects 같은 동시 read 요청이 hang됨. 작은 배치로 잘라
            # lock 점유 시간을 줄임.
            BATCH = 100
            with self.session_factory() as db:
                for i, page in enumerate(pages, start=1):
                    self._upsert_one(db, kind, page)
                    if i % BATCH == 0:
                        db.commit()
                db.commit()

            # full이면 노션에 없는 미러 row를 archive (삭제 감지)
            if full:
                with self.session_factory() as db:
                    self._mark_missing_archived(
                        db, kind, present_ids={p.get("id", "") for p in pages}
                    )
                    db.commit()

            self._record_success(
                kind, count=len(pages), full=full, next_since=start_time
            )
            return len(pages)

    # ── 단건 write-through (라우터에서 호출) ──

    def upsert_page(self, kind: SyncKind, page: dict) -> None:
        """라우터의 write 핸들러가 update/create 후 즉시 호출."""
        with self.session_factory() as db:
            self._upsert_one(db, kind, page)
            db.commit()

    def archive_page(self, kind: SyncKind, page_id: str) -> None:
        with self.session_factory() as db:
            self._archive_one(db, kind, page_id)
            db.commit()

    # ── 마스터 페이지 본문(이미지 등) ──

    async def sync_master_blocks(self, page_id: str) -> int:
        children = await self.notion.list_block_children(page_id)
        with self.session_factory() as db:
            # 기존 블록 모두 지우고 다시 채움 (단순/안전)
            db.query(M.MirrorBlock).filter(
                M.MirrorBlock.parent_page_id == page_id
            ).delete(synchronize_session=False)
            for idx, blk in enumerate(children):
                db.add(
                    M.MirrorBlock(
                        block_id=blk.get("id", ""),
                        parent_page_id=page_id,
                        type=blk.get("type", ""),
                        content=blk.get(blk.get("type", ""), {}) or {},
                        position=idx,
                        last_edited_time=_parse_iso(blk.get("last_edited_time")),
                    )
                )
            db.commit()
        return len(children)

    def upsert_block(self, parent_page_id: str, block: dict, *, position: int) -> None:
        with self.session_factory() as db:
            t = block.get("type", "")
            stmt = pg_insert(M.MirrorBlock).values(
                block_id=block.get("id", ""),
                parent_page_id=parent_page_id,
                type=t,
                content=block.get(t, {}) or {},
                position=position,
                last_edited_time=_parse_iso(block.get("last_edited_time")),
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["block_id"],
                set_=dict(
                    type=stmt.excluded.type,
                    content=stmt.excluded.content,
                    position=stmt.excluded.position,
                    last_edited_time=stmt.excluded.last_edited_time,
                    synced_at=_utcnow(),
                ),
            )
            db.execute(stmt)
            db.commit()

    def delete_block(self, block_id: str) -> None:
        with self.session_factory() as db:
            db.query(M.MirrorBlock).filter(
                M.MirrorBlock.block_id == block_id
            ).delete(synchronize_session=False)
            db.commit()

    # ── 내부 ──

    def _db_id_for(self, kind: SyncKind) -> str:
        s = self.settings
        return {
            "projects": s.notion_db_projects,
            "tasks": s.notion_db_tasks,
            "clients": s.notion_db_clients,
            "master": s.notion_db_master,
            "cashflow": s.notion_db_cashflow,
            "expense": s.notion_db_expense,
        }[kind]

    def _upsert_one(self, db: Session, kind: SyncKind, page: dict) -> None:
        if kind == "projects":
            self._upsert_project(db, page)
        elif kind == "tasks":
            self._upsert_task(db, page)
        elif kind == "clients":
            self._upsert_client(db, page)
        elif kind == "master":
            self._upsert_master(db, page)
        elif kind == "cashflow":
            self._upsert_cashflow(db, page, kind="income")
        elif kind == "expense":
            self._upsert_cashflow(db, page, kind="expense")

    def _archive_one(self, db: Session, kind: SyncKind, page_id: str) -> None:
        table = self._table_for(kind)
        if table is None:
            return
        db.query(table).filter(table.page_id == page_id).update(
            {"archived": True, "synced_at": _utcnow()}, synchronize_session=False
        )

    def _table_for(self, kind: SyncKind):
        return {
            "projects": M.MirrorProject,
            "tasks": M.MirrorTask,
            "clients": M.MirrorClient,
            "master": M.MirrorMaster,
            "cashflow": M.MirrorCashflow,
            "expense": M.MirrorCashflow,
        }.get(kind)

    def _mark_missing_archived(
        self, db: Session, kind: SyncKind, *, present_ids: set[str]
    ) -> None:
        table = self._table_for(kind)
        if table is None or not present_ids:
            return
        # cashflow와 expense는 같은 테이블이지만 kind 컬럼으로 분리
        q = db.query(table).filter(table.archived.is_(False))
        if kind == "cashflow":
            q = q.filter(table.kind == "income")
        elif kind == "expense":
            q = q.filter(table.kind == "expense")
        all_ids = {row.page_id for row in q.all()}
        missing = all_ids - present_ids
        if not missing:
            return
        q2 = db.query(table).filter(table.page_id.in_(missing))
        if kind == "cashflow":
            q2 = q2.filter(table.kind == "income")
        elif kind == "expense":
            q2 = q2.filter(table.kind == "expense")
        q2.update(
            {"archived": True, "synced_at": _utcnow()}, synchronize_session=False
        )

    # ── 도메인별 upsert ──

    def _upsert_project(self, db: Session, page: dict) -> None:
        p = Project.from_notion_page(page)
        stmt = pg_insert(M.MirrorProject).values(
            page_id=p.id,
            code=p.code or "",
            master_code=p.master_code or "",
            master_project_id=p.master_project_id or "",
            name=p.name or "",
            stage=p.stage or "",
            completed=bool(p.completed),
            assignees=list(p.assignees),
            teams=list(p.teams),
            client_relation_ids=list(p.client_relation_ids),
            properties=page.get("properties", {}),
            url=page.get("url") or "",
            last_edited_time=_parse_iso(p.last_edited_time),
            synced_at=_utcnow(),
            archived=bool(page.get("archived", False)),
        )
        db.execute(
            stmt.on_conflict_do_update(
                index_elements=["page_id"],
                set_=dict(
                    code=stmt.excluded.code,
                    master_code=stmt.excluded.master_code,
                    master_project_id=stmt.excluded.master_project_id,
                    name=stmt.excluded.name,
                    stage=stmt.excluded.stage,
                    completed=stmt.excluded.completed,
                    assignees=stmt.excluded.assignees,
                    teams=stmt.excluded.teams,
                    client_relation_ids=stmt.excluded.client_relation_ids,
                    properties=stmt.excluded.properties,
                    url=stmt.excluded.url,
                    last_edited_time=stmt.excluded.last_edited_time,
                    synced_at=stmt.excluded.synced_at,
                    archived=stmt.excluded.archived,
                ),
            )
        )

    def _upsert_task(self, db: Session, page: dict) -> None:
        t = Task.from_notion_page(page)
        stmt = pg_insert(M.MirrorTask).values(
            page_id=t.id,
            title=t.title or "",
            code=t.code or "",
            project_ids=list(t.project_ids),
            status=t.status or "",
            priority=t.priority or "",
            difficulty=t.difficulty or "",
            category=t.category or "",
            activity=t.activity or "",
            progress=t.progress,
            start_date=_parse_date(t.start_date),
            end_date=_parse_date(t.end_date),
            actual_end_date=_parse_date(t.actual_end_date),
            assignees=list(t.assignees),
            teams=list(t.teams),
            properties=page.get("properties", {}),
            url=page.get("url") or "",
            created_time=_parse_iso(t.created_time),
            last_edited_time=_parse_iso(t.last_edited_time),
            synced_at=_utcnow(),
            archived=bool(page.get("archived", False)),
        )
        db.execute(
            stmt.on_conflict_do_update(
                index_elements=["page_id"],
                set_=dict(
                    title=stmt.excluded.title,
                    code=stmt.excluded.code,
                    project_ids=stmt.excluded.project_ids,
                    status=stmt.excluded.status,
                    priority=stmt.excluded.priority,
                    difficulty=stmt.excluded.difficulty,
                    category=stmt.excluded.category,
                    activity=stmt.excluded.activity,
                    progress=stmt.excluded.progress,
                    start_date=stmt.excluded.start_date,
                    end_date=stmt.excluded.end_date,
                    actual_end_date=stmt.excluded.actual_end_date,
                    assignees=stmt.excluded.assignees,
                    teams=stmt.excluded.teams,
                    properties=stmt.excluded.properties,
                    url=stmt.excluded.url,
                    created_time=stmt.excluded.created_time,
                    last_edited_time=stmt.excluded.last_edited_time,
                    synced_at=stmt.excluded.synced_at,
                    archived=stmt.excluded.archived,
                ),
            )
        )

    def _upsert_client(self, db: Session, page: dict) -> None:
        props = page.get("properties", {})
        # title 자동 탐지
        name = ""
        for prop in props.values():
            if prop.get("type") == "title":
                arr = prop.get("title") or []
                name = arr[0].get("plain_text", "") if arr else ""
                break
        category = P.select_name(props, "구분")
        stmt = pg_insert(M.MirrorClient).values(
            page_id=page.get("id", ""),
            name=name,
            category=category or "",
            properties=props,
            last_edited_time=_parse_iso(page.get("last_edited_time")),
            synced_at=_utcnow(),
            archived=bool(page.get("archived", False)),
        )
        db.execute(
            stmt.on_conflict_do_update(
                index_elements=["page_id"],
                set_=dict(
                    name=stmt.excluded.name,
                    category=stmt.excluded.category,
                    properties=stmt.excluded.properties,
                    last_edited_time=stmt.excluded.last_edited_time,
                    synced_at=stmt.excluded.synced_at,
                    archived=stmt.excluded.archived,
                ),
            )
        )

    def _upsert_master(self, db: Session, page: dict) -> None:
        props = page.get("properties", {})
        stmt = pg_insert(M.MirrorMaster).values(
            page_id=page.get("id", ""),
            code=P.rich_text(props, "MASTER_CODE") or "",
            name=P.title(props, "용역명") or "",
            sub_project_ids=P.relation_ids(props, "Sub-Project"),
            properties=props,
            url=page.get("url") or "",
            last_edited_time=_parse_iso(page.get("last_edited_time")),
            synced_at=_utcnow(),
            archived=bool(page.get("archived", False)),
        )
        db.execute(
            stmt.on_conflict_do_update(
                index_elements=["page_id"],
                set_=dict(
                    code=stmt.excluded.code,
                    name=stmt.excluded.name,
                    sub_project_ids=stmt.excluded.sub_project_ids,
                    properties=stmt.excluded.properties,
                    url=stmt.excluded.url,
                    last_edited_time=stmt.excluded.last_edited_time,
                    synced_at=stmt.excluded.synced_at,
                    archived=stmt.excluded.archived,
                ),
            )
        )

    def _upsert_cashflow(
        self, db: Session, page: dict, *, kind: Literal["income", "expense"]
    ) -> None:
        if kind == "income":
            ent = CashflowEntry.from_income_page(page)
        else:
            ent = CashflowEntry.from_expense_page(page)
        stmt = pg_insert(M.MirrorCashflow).values(
            page_id=ent.id,
            kind=kind,
            project_ids=list(ent.project_ids),
            date=_parse_date(ent.date),
            amount=float(ent.amount or 0),
            category=ent.category or "",
            note=ent.note or "",
            properties=page.get("properties", {}),
            last_edited_time=_parse_iso(page.get("last_edited_time")),
            synced_at=_utcnow(),
            archived=bool(page.get("archived", False)),
        )
        db.execute(
            stmt.on_conflict_do_update(
                index_elements=["page_id"],
                set_=dict(
                    kind=stmt.excluded.kind,
                    project_ids=stmt.excluded.project_ids,
                    date=stmt.excluded.date,
                    amount=stmt.excluded.amount,
                    category=stmt.excluded.category,
                    note=stmt.excluded.note,
                    properties=stmt.excluded.properties,
                    last_edited_time=stmt.excluded.last_edited_time,
                    synced_at=stmt.excluded.synced_at,
                    archived=stmt.excluded.archived,
                ),
            )
        )

    # ── sync_state ──

    def _get_since(self, kind: SyncKind) -> datetime | None:
        with self.session_factory() as db:
            row = db.execute(
                select(M.NotionSyncState).where(M.NotionSyncState.db_kind == kind)
            ).scalar_one_or_none()
            return row.last_incremental_synced_at if row else None

    def _record_success(
        self,
        kind: SyncKind,
        *,
        count: int,
        full: bool,
        next_since: datetime | None = None,
    ) -> None:
        # next_since: 다음 incremental의 since로 박을 시각. 호출자가 sync 시작
        # 시각을 넘겨야 진행 도중 추가된 페이지가 누락되지 않음. None이면 fallback
        # 으로 현재 시각 (호환성).
        now = _utcnow()
        cursor = next_since or now
        with self.session_factory() as db:
            stmt = pg_insert(M.NotionSyncState).values(
                db_kind=kind,
                last_incremental_synced_at=cursor,
                last_full_synced_at=now if full else None,
                last_error="",
                last_run_count=count,
            )
            updates: dict[str, Any] = dict(
                last_incremental_synced_at=stmt.excluded.last_incremental_synced_at,
                last_error="",
                last_run_count=stmt.excluded.last_run_count,
            )
            if full:
                updates["last_full_synced_at"] = stmt.excluded.last_full_synced_at
            db.execute(
                stmt.on_conflict_do_update(index_elements=["db_kind"], set_=updates)
            )
            db.commit()

    def _record_error(self, kind: SyncKind, message: str) -> None:
        with self.session_factory() as db:
            stmt = pg_insert(M.NotionSyncState).values(
                db_kind=kind,
                last_error=message[:1000],
                last_run_count=0,
            )
            db.execute(
                stmt.on_conflict_do_update(
                    index_elements=["db_kind"],
                    set_=dict(last_error=stmt.excluded.last_error),
                )
            )
            db.commit()


# ── 싱글턴 ──

_instance: NotionSyncService | None = None


def get_sync() -> NotionSyncService:
    global _instance
    if _instance is None:
        from app.db import SessionLocal
        from app.services.notion import get_notion

        _instance = NotionSyncService(get_notion(), SessionLocal)
    return _instance
