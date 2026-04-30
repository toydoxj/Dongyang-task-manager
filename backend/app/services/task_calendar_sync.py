"""Notion task ↔ NAVER WORKS Calendar 단방향 동기화.

정책 (P1.5):
- source of truth: 노션 task DB. WORKS Calendar는 read-only mirror
- 동기화 대상: category in (외근,출장,휴가) OR activity in (외근,출장)
- admin 토큰의 calendar scope로 회사 공유 캘린더(WORKS_SHARED_CALENDAR_ID)에만 등록
  (admin OAuth로 다른 user 캘린더 쓰기는 NAVER WORKS가 차단 — 공유 캘린더는 OK)
- task 생성/수정 시 → upsert event, 삭제·범위 이탈(분류 변경 등) 시 → delete event
- task ↔ event 매핑은 calendar_event_links 테이블에 보관 (중복 생성 방지 + 갱신/삭제 추적)

호출 시점:
- POST /api/tasks → background task로 sync_task() 호출
- PATCH /api/tasks/{id} → 동일
- DELETE /api/tasks/{id} → unsync_task()로 mirror event 삭제
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.calendar_event import CalendarEventLink
from app.models.task import Task
from app.services import sso_calendar
from app.settings import Settings, get_settings

logger = logging.getLogger("task.calendar")

KST = timezone(timedelta(hours=9))

_SCHEDULE_CATEGORIES = {"외근", "출장", "휴가", "휴가(연차)"}
_SCHEDULE_ACTIVITIES = {"외근", "출장"}


def is_schedule_task(task: Task) -> bool:
    """task가 calendar 동기화 대상인지 — 분류/활동 기반."""
    return task.category in _SCHEDULE_CATEGORIES or task.activity in _SCHEDULE_ACTIVITIES


def _schedule_label(task: Task) -> str:
    """event title의 prefix — 분류 우선, 없으면 활동."""
    return task.category or task.activity or "일정"


def _build_summary(task: Task) -> str:
    """event title.

    예: "[외근] 김철수 — 회의 참석"
    assignees 여러 명: "[외근] 김철수, 이영희 — 회의 참석"
    """
    label = _schedule_label(task)
    names = ", ".join(a for a in task.assignees if a) if task.assignees else ""
    title = (task.title or "").strip() or "(제목 없음)"
    if names:
        return f"[{label}] {names} — {title}"[:200]
    return f"[{label}] {title}"[:200]


def _build_description(task: Task, settings: Settings) -> str:
    parts: list[str] = []
    if task.assignees:
        parts.append(f"담당자: {', '.join(task.assignees)}")
    if task.teams:
        parts.append(f"담당팀: {', '.join(task.teams)}")
    if task.note:
        parts.append(f"메모: {task.note[:300]}")
    if task.url:
        parts.append(f"노션: {task.url}")
    return "\n".join(parts)[:1000]


def _parse_dt(s: str | None) -> tuple[datetime | date | None, bool]:
    """노션 date string → (datetime|date, all_day).

    'YYYY-MM-DD' → date, all_day=True
    'YYYY-MM-DDTHH:MM:SS+09:00' → datetime, all_day=False
    timezone 없는 ISO는 KST로 가정.
    """
    if not s:
        return None, False
    if "T" not in s:
        # date only
        try:
            return date.fromisoformat(s[:10]), True
        except ValueError:
            return None, False
    # datetime
    iso = s
    if iso.endswith("Z"):
        iso = iso[:-1] + "+00:00"
    elif "+" not in iso[10:] and "-" not in iso[10:]:
        # naive → KST 가정
        iso = iso + "+09:00"
    try:
        return datetime.fromisoformat(iso), False
    except ValueError:
        return None, False


def _resolve_period(task: Task) -> tuple[datetime | date, datetime | date, bool] | None:
    """task의 기간 → (start, end, all_day). 부족하면 None.

    노션 'end' 의미: all-day 일정의 경우 노션 응답은 end가 last day 다음 날(exclusive).
    여기선 그대로 calendar API에 전달 — NAVER WORKS도 동일 규칙(end exclusive).
    end 미지정 시 start와 같게 두면 단일 day 일정.
    """
    s, s_all = _parse_dt(task.start_date)
    if s is None:
        return None
    e, e_all = _parse_dt(task.end_date) if task.end_date else (None, s_all)
    if e is None:
        # end 미지정 — start 와 동일하게
        if s_all:
            # all-day 단일일: end = start + 1d (exclusive)
            assert isinstance(s, date)
            return s, s + timedelta(days=1), True
        else:
            assert isinstance(s, datetime)
            # 시간 일정 — 1시간 default
            return s, s + timedelta(hours=1), False
    all_day = s_all and e_all
    return s, e, all_day


# ── 동기화 함수 ──


def _delete_existing_links(db: Session, task_id: str) -> list[CalendarEventLink]:
    """그 task의 모든 매핑 row 가져오기. 호출자가 NAVER에서도 삭제 후 row 삭제."""
    return (
        db.execute(
            select(CalendarEventLink).where(
                CalendarEventLink.notion_task_id == task_id
            )
        )
        .scalars()
        .all()
    )


async def _delete_link_remote(
    settings: Settings, link: CalendarEventLink
) -> None:
    """NAVER WORKS에서 event 삭제. 실패 시 경고만."""
    try:
        await sso_calendar.delete_event(
            settings,
            target_user_id=link.target_user_id,
            calendar_id=link.calendar_id,
            event_id=link.event_id,
        )
    except sso_calendar.CalendarError as e:
        logger.warning(
            "calendar event 삭제 실패 (task=%s, event=%s): %s",
            link.notion_task_id,
            link.event_id,
            e,
        )


async def sync_task(task: Task) -> None:
    """task 1개를 공유 캘린더에 upsert.

    - is_schedule_task가 False면 기존 event를 삭제 (range 이탈 처리)
    - True면 기존 event 있으면 update, 없으면 create
    - 시작일/종료일이 없으면 sync 안 함 (event 만들 수 없음)

    실패해도 raise 안 함 — 노션이 source of truth라 calendar는 best-effort.
    """
    settings = get_settings()
    if not settings.works_calendar_enabled:
        return
    if not settings.works_shared_calendar_id:
        logger.warning("WORKS_SHARED_CALENDAR_ID 미설정 — sync skip")
        return

    db = SessionLocal()
    try:
        existing = _delete_existing_links(db, task.id)

        # 범위 이탈: 기존 event 모두 삭제
        if not is_schedule_task(task):
            for link in existing:
                await _delete_link_remote(settings, link)
            for link in existing:
                db.delete(link)
            db.commit()
            return

        period = _resolve_period(task)
        if period is None:
            # 시작일 없음 → sync 못 함. 기존 event 있으면 정리
            for link in existing:
                await _delete_link_remote(settings, link)
            for link in existing:
                db.delete(link)
            db.commit()
            return

        start, end, all_day = period
        summary = _build_summary(task)
        description = _build_description(task, settings)
        cal_id = settings.works_shared_calendar_id

        # admin 본인을 organizer로 — Calendar API path는 owner의 user_id 필요
        admin_user_id = await _get_admin_works_user_id(db)
        if not admin_user_id:
            logger.warning(
                "admin works_user_id 못 찾음 — task=%s sync skip", task.id
            )
            return

        # 기존 매핑이 있으면 update, 없으면 create
        match = next(
            (
                lk
                for lk in existing
                if lk.calendar_id == cal_id
                and lk.target_user_id == admin_user_id
                and lk.is_shared
            ),
            None,
        )

        try:
            if match:
                await sso_calendar.update_event(
                    settings,
                    target_user_id=admin_user_id,
                    calendar_id=cal_id,
                    event_id=match.event_id,
                    summary=summary,
                    start=start,
                    end=end,
                    description=description,
                    all_day=all_day,
                )
            else:
                resp = await sso_calendar.create_event(
                    settings,
                    target_user_id=admin_user_id,
                    calendar_id=cal_id,
                    summary=summary,
                    start=start,
                    end=end,
                    description=description,
                    all_day=all_day,
                )
                event_id = sso_calendar.extract_event_id(resp)
                if not event_id:
                    logger.warning(
                        "create_event eventId 추출 실패 task=%s resp=%s",
                        task.id,
                        resp,
                    )
                    return
                db.add(
                    CalendarEventLink(
                        notion_task_id=task.id,
                        target_user_id=admin_user_id,
                        calendar_id=cal_id,
                        event_id=event_id,
                        is_shared=True,
                    )
                )
                db.commit()
        except sso_calendar.CalendarError as e:
            logger.warning("calendar sync 실패 task=%s: %s", task.id, e)
    finally:
        db.close()


async def unsync_task(task_id: str) -> None:
    """task 삭제·archive 시 해당 calendar event 모두 삭제."""
    settings = get_settings()
    if not settings.works_calendar_enabled:
        return
    db = SessionLocal()
    try:
        existing = _delete_existing_links(db, task_id)
        for link in existing:
            await _delete_link_remote(settings, link)
        for link in existing:
            db.delete(link)
        db.commit()
    finally:
        db.close()


# ── 헬퍼 ──


async def _get_admin_works_user_id(db: Session) -> str:
    """공유 캘린더 owner — admin user의 works_user_id 조회.

    drive_credentials에 동의한 admin이 그 사람. granted_by_user_id로 User 테이블 조회.
    """
    from app.models.auth import User
    from app.models.drive_creds import DriveCredential

    creds = db.get(DriveCredential, 1)
    if creds is None or not creds.granted_by_user_id:
        return ""
    admin = db.get(User, creds.granted_by_user_id)
    if admin is None:
        return ""
    return admin.works_user_id or ""
