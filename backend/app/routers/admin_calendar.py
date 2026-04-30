"""/api/admin/calendar — admin이 NAVER WORKS Calendar 연동을 운영하는 엔드포인트.

drive_credentials의 토큰(scope에 'calendar' 포함)을 재사용하므로 별도 토큰 발급 X.
PoC 검증 완료 후 P1 본격 작업의 인프라.

엔드포인트:
- POST /api/admin/calendar/create-shared-calendar  # 회사 공유 캘린더 1회 생성
- POST /api/admin/calendar/sync-employees           # /users API 호출 → Employee.works_user_id 매핑
- POST /api/admin/calendar/test-event               # admin 본인 캘린더에 테스트 이벤트 (검증용)
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db import SessionLocal, get_db
from app.models import mirror as M
from app.models.auth import User
from app.models.employee import Employee
from app.security import require_admin
from app.services import sso_calendar, task_calendar_sync
from app.services.mirror_dto import task_from_mirror
from app.settings import get_settings

logger = logging.getLogger("admin.calendar")
router = APIRouter(prefix="/admin/calendar", tags=["admin-calendar"])

# fire-and-forget background task GC 방어 (asyncio.create_task가 GC되면 mid-execution 끊김)
_bg_tasks: set[asyncio.Task[None]] = set()
_running_backfill = False


class CreateSharedRequest(BaseModel):
    name: str = "(주)동양구조 공용 일정"
    description: str = "외근·출장·휴가 등 직원 일정 자동 동기화"


class CreateSharedResponse(BaseModel):
    calendar_id: str
    summary: str
    raw: dict[str, Any]
    note: str


@router.post("/create-shared-calendar", response_model=CreateSharedResponse)
async def create_shared_calendar(
    body: CreateSharedRequest = Body(default_factory=CreateSharedRequest),
    _admin: User = Depends(require_admin),
) -> CreateSharedResponse:
    """공유 캘린더 1회 생성. 응답의 calendar_id를 환경변수
    WORKS_SHARED_CALENDAR_ID로 저장해야 함 (admin이 수동).
    """
    s = get_settings()
    try:
        resp = await sso_calendar.create_calendar(
            s, name=body.name, description=body.description
        )
    except sso_calendar.CalendarError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    cal_id = ""
    for key in ("calendarId", "id"):
        v = resp.get(key)
        if isinstance(v, str) and v:
            cal_id = v
            break
    return CreateSharedResponse(
        calendar_id=cal_id,
        summary=str(resp.get("summary", body.name)),
        raw=resp,
        note=(
            "Render 환경변수 WORKS_SHARED_CALENDAR_ID 에 calendar_id 값을 "
            "저장하세요. 이후 task 동기화에서 사용됩니다."
        ),
    )


class SyncEmployeesResponse(BaseModel):
    works_user_count: int  # /users API에서 받은 총 user 수
    matched: int  # Employee.email과 매칭되어 works_user_id 채워진 수
    unmatched_works_users: list[str]  # works user 중 Employee 매칭 실패 (email)
    unmatched_employees: list[str]  # Employee 중 works_user_id 못 채운 (name)


@router.post("/sync-employees", response_model=SyncEmployeesResponse)
async def sync_employees(
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> SyncEmployeesResponse:
    """NAVER WORKS /users → Employee.works_user_id 매핑.

    Employee.email ↔ works.email 으로 매칭. email 미일치 직원은 admin이 수동 보강.
    """
    s = get_settings()
    try:
        users = await sso_calendar.list_all_users(s)
    except sso_calendar.CalendarError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    # email → userId 매핑
    by_email: dict[str, str] = {}
    for u in users:
        email = str(u.get("email") or "").strip().lower()
        uid = str(u.get("userId") or "")
        if email and uid:
            by_email[email] = uid

    employees = db.execute(select(Employee)).scalars().all()
    matched = 0
    unmatched_emp: list[str] = []
    matched_emails: set[str] = set()
    for emp in employees:
        email = (emp.email or "").strip().lower()
        if not email:
            unmatched_emp.append(emp.name)
            continue
        wid = by_email.get(email)
        if not wid:
            unmatched_emp.append(emp.name)
            continue
        if emp.works_user_id != wid:
            emp.works_user_id = wid
        matched += 1
        matched_emails.add(email)
    db.commit()

    unmatched_works = [
        e for e in by_email.keys() if e not in matched_emails
    ]
    return SyncEmployeesResponse(
        works_user_count=len(users),
        matched=matched,
        unmatched_works_users=sorted(unmatched_works),
        unmatched_employees=sorted(unmatched_emp),
    )


class TestEventRequest(BaseModel):
    target_email: str = ""  # 비면 admin 본인 캘린더에 시도
    calendar_id: str = ""  # 비면 기본 캘린더


class TestEventResponse(BaseModel):
    target_user_id: str
    event_id: str
    raw: dict[str, Any]


@router.post("/test-event", response_model=TestEventResponse)
async def test_event(
    body: TestEventRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> TestEventResponse:
    """admin 토큰으로 특정 직원 캘린더에 test event 생성·즉시 삭제.

    target_email이 admin과 다르면 P1.4 검증 — 다른 사용자 캘린더에 admin 토큰 위임이
    실제 작동하는지 확인. NAVER WORKS 권한 정책에 따라 403 가능성 있음.
    """
    s = get_settings()

    # target user id 결정
    if body.target_email:
        # email로 Employee.works_user_id 조회
        emp = (
            db.query(Employee)
            .filter(Employee.email == body.target_email.lower())
            .first()
        )
        if emp is None or not emp.works_user_id:
            raise HTTPException(
                status_code=400,
                detail=f"{body.target_email} 의 works_user_id 미매핑. "
                "/api/admin/calendar/sync-employees 먼저 호출.",
            )
        target_user_id = emp.works_user_id
    else:
        if not admin.works_user_id:
            raise HTTPException(
                status_code=400, detail="admin works_user_id 없음 (SSO 미로그인)"
            )
        target_user_id = admin.works_user_id

    kst = timezone(timedelta(hours=9))
    start = (datetime.now(kst) + timedelta(days=1)).replace(
        hour=10, minute=0, second=0, microsecond=0
    )
    end = start + timedelta(minutes=30)
    try:
        resp = await sso_calendar.create_event(
            s,
            target_user_id=target_user_id,
            calendar_id=body.calendar_id,
            summary="[Task_DY 위임 테스트]",
            start=start,
            end=end,
            description="P1.4 검증용 — 자동 삭제됨",
        )
    except sso_calendar.CalendarError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    event_id = sso_calendar.extract_event_id(resp)
    if not event_id:
        raise HTTPException(
            status_code=502, detail=f"eventId 추출 실패. 응답: {resp}"
        )

    # 즉시 삭제 (테스트라 정리)
    try:
        await sso_calendar.delete_event(
            s,
            target_user_id=target_user_id,
            calendar_id=body.calendar_id,
            event_id=event_id,
        )
    except sso_calendar.CalendarError as e:
        # 삭제 실패는 경고만 — 생성 성공이 핵심
        logger.warning("test-event 삭제 실패: %s", e)

    return TestEventResponse(
        target_user_id=target_user_id, event_id=event_id, raw=resp
    )


# ── 기존 task 일괄 동기화 (P2 backfill) ──


class BackfillResponse(BaseModel):
    status: str  # started / already_running
    candidate_count: int  # backfill 대상 task 수


def _list_schedule_tasks_from_mirror() -> list[Any]:
    """mirror_tasks에서 schedule(외근/출장/휴가) task만 골라 Task DTO로 반환."""
    with SessionLocal() as db:
        rows = (
            db.execute(
                select(M.MirrorTask)
                .where(M.MirrorTask.archived.is_(False))
                .where(
                    or_(
                        M.MirrorTask.category.in_(["외근", "출장", "휴가"]),
                        M.MirrorTask.activity.in_(["외근", "출장"]),
                    )
                )
            )
            .scalars()
            .all()
        )
        return [task_from_mirror(r) for r in rows]


async def _run_backfill_in_bg() -> None:
    global _running_backfill
    bf_logger = logging.getLogger("admin.calendar.backfill")
    success = 0
    failed = 0
    try:
        tasks = _list_schedule_tasks_from_mirror()
        bf_logger.info("backfill 시작: %d 건", len(tasks))
        for task in tasks:
            try:
                await task_calendar_sync.sync_task(task)
                success += 1
            except Exception:  # noqa: BLE001
                bf_logger.exception("backfill 실패 task=%s", task.id)
                failed += 1
        bf_logger.info(
            "backfill done: success=%d, failed=%d, total=%d",
            success,
            failed,
            len(tasks),
        )
    finally:
        _running_backfill = False


@router.post("/backfill", response_model=BackfillResponse, status_code=202)
async def backfill(
    _admin: User = Depends(require_admin),
) -> BackfillResponse:
    """기존 노션 schedule task들을 일괄 calendar 동기화.

    fire-and-forget — 응답 즉시 202, 진행은 background. 결과는 Render Logs(`admin.calendar.backfill`)에서 확인.
    중복 호출 방지: 진행 중이면 already_running.
    """
    global _running_backfill
    candidates = _list_schedule_tasks_from_mirror()
    if _running_backfill:
        return BackfillResponse(
            status="already_running", candidate_count=len(candidates)
        )
    _running_backfill = True
    task = asyncio.create_task(_run_backfill_in_bg())
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)
    return BackfillResponse(status="started", candidate_count=len(candidates))
