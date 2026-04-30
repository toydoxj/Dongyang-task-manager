"""NAVER WORKS Calendar API wrapper.

drive_credentials의 admin OAuth 토큰을 재사용 (scope에 'calendar' 포함).
Drive와 별도 토큰 테이블을 두지 않고, 한 토큰이 두 권한을 가짐.

PoC로 검증된 동작:
- POST /users/{userId}/calendar/events    (기본 캘린더에 일정 생성, 201)
- GET  /users/{userId}/calendar/events/{id} (200)
- DELETE /users/{userId}/calendar/events/{id} (204)
- 응답 형태: {"eventComponents": [{"eventId": "...", ...}], "organizerCalendarId": "..."}
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

from app.services import sso_drive
from app.settings import Settings

logger = logging.getLogger("sso.calendar")

_HTTP_TIMEOUT = 15.0
KST = timezone(timedelta(hours=9))


class CalendarError(Exception):
    """Calendar 흐름에서 사용자에게 노출 가능한 에러."""


# ── HTTP wrapper ──


async def _api(
    settings: Settings,
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """drive_credentials 토큰으로 NAVER WORKS API 호출 + 401 retry."""
    url = f"{settings.works_api_base.rstrip('/')}{path}"
    try:
        token = await sso_drive._get_valid_access_token(settings)
    except sso_drive.DriveError as e:
        raise CalendarError(str(e)) from e

    async def _call(t: str) -> httpx.Response:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            return await client.request(
                method,
                url,
                params=params,
                json=json,
                headers={
                    "Authorization": f"Bearer {t}",
                    "Content-Type": "application/json",
                },
            )

    resp = await _call(token)
    if resp.status_code == 401:
        try:
            token = await sso_drive._get_valid_access_token(settings)
        except sso_drive.DriveError as e:
            raise CalendarError(str(e)) from e
        resp = await _call(token)
    if resp.status_code >= 400:
        logger.warning(
            "Calendar API 오류 %s %s: %s %s",
            method,
            path,
            resp.status_code,
            resp.text,
        )
        raise CalendarError(
            f"Calendar API 오류 ({resp.status_code}) {path} — "
            f"{resp.text[:300]}"
        )
    if not resp.content:
        return {}
    try:
        return resp.json()
    except ValueError:
        return {}


# ── 이벤트 ──


def _event_path(target_user_id: str, calendar_id: str = "") -> str:
    """calendar_id 비면 기본 캘린더 endpoint, 값 있으면 특정 캘린더."""
    if calendar_id:
        return f"/users/{target_user_id}/calendars/{calendar_id}/events"
    return f"/users/{target_user_id}/calendar/events"


def _fmt_dt(dt: datetime) -> str:
    return dt.astimezone(KST).strftime("%Y-%m-%dT%H:%M:%S")


def _build_event_component(
    *,
    summary: str,
    start: datetime | date,
    end: datetime | date,
    description: str = "",
    transparency: str = "OPAQUE",
    event_id: str = "",
    all_day: bool = False,
) -> dict[str, Any]:
    """eventComponents의 단일 event 객체를 빌드.

    all_day=True 또는 start가 date(시간 없음)이면 종일 일정.
    """
    if all_day or not isinstance(start, datetime):
        s_iso = (start if isinstance(start, date) else start.date()).isoformat()
        e_iso = (end if isinstance(end, date) else end.date()).isoformat()
        comp: dict[str, Any] = {
            "summary": summary,
            "start": {"date": s_iso, "timeZone": "Asia/Seoul"},
            "end": {"date": e_iso, "timeZone": "Asia/Seoul"},
            "description": description,
            "transparency": transparency,
        }
    else:
        comp = {
            "summary": summary,
            "start": {"dateTime": _fmt_dt(start), "timeZone": "Asia/Seoul"},
            "end": {"dateTime": _fmt_dt(end), "timeZone": "Asia/Seoul"},
            "description": description,
            "transparency": transparency,
        }
    if event_id:
        comp["eventId"] = event_id
    return comp


async def create_event(
    settings: Settings,
    *,
    target_user_id: str,
    calendar_id: str = "",
    summary: str,
    start: datetime | date,
    end: datetime | date,
    description: str = "",
    transparency: str = "OPAQUE",
    all_day: bool = False,
) -> dict[str, Any]:
    """일정 생성 — 응답에서 eventId 자동 발급. all_day는 종일 일정."""
    body = {
        "eventComponents": [
            _build_event_component(
                summary=summary,
                start=start,
                end=end,
                description=description,
                transparency=transparency,
                all_day=all_day,
            )
        ]
    }
    return await _api(
        settings, "POST", _event_path(target_user_id, calendar_id), json=body
    )


def extract_event_id(response: dict[str, Any]) -> str:
    """create_event 응답에서 eventId 추출."""
    comps = response.get("eventComponents") or []
    if comps and isinstance(comps, list):
        return str(comps[0].get("eventId", ""))
    return str(response.get("eventId", ""))


async def update_event(
    settings: Settings,
    *,
    target_user_id: str,
    calendar_id: str = "",
    event_id: str,
    summary: str,
    start: datetime | date,
    end: datetime | date,
    description: str = "",
    transparency: str = "OPAQUE",
    all_day: bool = False,
) -> dict[str, Any]:
    body = {
        "eventComponents": [
            _build_event_component(
                summary=summary,
                start=start,
                end=end,
                description=description,
                transparency=transparency,
                event_id=event_id,
                all_day=all_day,
            )
        ]
    }
    path = f"{_event_path(target_user_id, calendar_id)}/{event_id}"
    return await _api(settings, "PUT", path, json=body)


async def delete_event(
    settings: Settings,
    *,
    target_user_id: str,
    calendar_id: str = "",
    event_id: str,
) -> None:
    path = f"{_event_path(target_user_id, calendar_id)}/{event_id}"
    await _api(settings, "DELETE", path)


# ── 캘린더 관리 ──


async def create_calendar(
    settings: Settings,
    *,
    name: str,
    description: str = "",
    is_public: bool = True,
    members: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """공유 캘린더 생성. 응답의 calendarId를 환경변수에 저장.

    POST /calendars body:
      calendarName  (str, required, max 50)
      description   (str, max 1000)
      isPublic      (bool, default false) — true면 회사 도메인 전체 조회 가능
      members       (list, optional) — id/type/role 지정. isPublic=true면 비워둬도 OK
    """
    body: dict[str, Any] = {
        "calendarName": name[:50],
        "isPublic": bool(is_public),
    }
    if description:
        body["description"] = description[:1000]
    if members:
        body["members"] = members
    return await _api(settings, "POST", "/calendars", json=body)


# ── 회사 디렉터리 ──


async def list_users(
    settings: Settings,
    *,
    count: int = 100,
    cursor: str | None = None,
) -> dict[str, Any]:
    """회사 도메인 user list — Employee 매핑용.

    응답 예: {"users":[{"userId":"...","email":"...","userName":{...}}], "responseMetaData":{"nextCursor":"..."}}
    """
    params: dict[str, Any] = {"count": count}
    if cursor:
        params["cursor"] = cursor
    return await _api(settings, "GET", "/users", params=params)


async def list_all_users(settings: Settings) -> list[dict[str, Any]]:
    """페이징 자동. 회사 전체 user 평면 list 반환."""
    out: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        body = await list_users(settings, cursor=cursor)
        users = body.get("users") or []
        out.extend(users)
        meta = body.get("responseMetaData") or {}
        cursor = meta.get("nextCursor")
        if not cursor:
            break
    return out
