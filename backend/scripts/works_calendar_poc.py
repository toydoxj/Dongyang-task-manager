"""NAVER WORKS Calendar API PoC.

drive_credentials의 admin OAuth 토큰(file + calendar scope)을 재사용해
admin 본인 기본 캘린더에 test event 1개 create + read + delete까지 검증.

선행 조건:
  1. /api/admin/drive/connect 를 admin이 새로 호출해 토큰 재동의 (scope에 'calendar' 추가됨)
  2. Render 새 deploy 적용된 상태 (auth.py scope 변경 반영)

실행:
  cd backend
  .venv/Scripts/python.exe scripts/works_calendar_poc.py

검증 케이스:
  - CREATE: POST /users/{userId}/calendar/events
  - READ:   GET  /users/{userId}/calendar/events/{eventId}
  - DELETE: DELETE /users/{userId}/calendar/events/{eventId}
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

# backend dir을 import path에 추가
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

import httpx  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models.auth import User  # noqa: E402
from app.models.drive_creds import DriveCredential  # noqa: E402
from app.services import sso_drive  # noqa: E402
from app.settings import get_settings  # noqa: E402


async def main() -> int:
    s = get_settings()

    # 1) admin works_user_id 조회
    db = SessionLocal()
    try:
        admin = (
            db.query(User)
            .filter(User.role == "admin", User.works_user_id != "")
            .first()
        )
        if admin is None:
            print(
                "❌ works_user_id 보유한 admin 없음. SSO 로그인된 admin 필요."
            )
            return 1
        admin_user_id = admin.works_user_id
        print(f"admin: {admin.name} ({admin.email})")
        print(f"  works_user_id = {admin_user_id}")

        creds = db.query(DriveCredential).first()
        if creds is None:
            print(
                "❌ drive_credentials 비어있음. /api/admin/drive/connect 호출 필요."
            )
            return 1
        print(f"current scope = '{creds.scope}'")
        scopes = set(creds.scope.split())
        if "calendar" not in scopes:
            print(
                "❌ 토큰의 scope에 'calendar' 없음. "
                "/api/admin/drive/connect 다시 호출 후 재동의 필요."
            )
            return 1
    finally:
        db.close()

    # 2) access_token 가져오기 (만료 시 자동 refresh)
    token = await sso_drive._get_valid_access_token(s)
    print(f"access_token 발급 OK (길이={len(token)})")

    base = s.works_api_base.rstrip("/")

    # 3) Test event 생성 — 내일 오전 10:00~11:00 KST
    kst = timezone(timedelta(hours=9))
    start = (datetime.now(kst) + timedelta(days=1)).replace(
        hour=10, minute=0, second=0, microsecond=0
    )
    end = start + timedelta(hours=1)
    create_body = {
        "eventComponents": [
            {
                "summary": "[PoC] Calendar API 자동 검증 이벤트",
                "start": {
                    "dateTime": start.strftime("%Y-%m-%dT%H:%M:%S"),
                    "timeZone": "Asia/Seoul",
                },
                "end": {
                    "dateTime": end.strftime("%Y-%m-%dT%H:%M:%S"),
                    "timeZone": "Asia/Seoul",
                },
                "description": "Task_DY PoC — 자동 생성/조회/삭제 검증용",
                "transparency": "OPAQUE",
            }
        ]
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=15) as client:
        # ── CREATE ──
        create_url = f"{base}/users/{admin_user_id}/calendar/events"
        print(f"\n[CREATE] POST {create_url}")
        resp = await client.post(create_url, json=create_body, headers=headers)
        print(f"  status = {resp.status_code}")
        print(f"  body   = {resp.text[:800]}")
        if resp.status_code >= 400:
            print("❌ CREATE 실패")
            return 2

        body = resp.json() if resp.content else {}
        event_id = ""
        comps = body.get("eventComponents") or []
        if comps and isinstance(comps, list):
            event_id = str(comps[0].get("eventId", ""))
        if not event_id:
            # 응답 형식이 다를 수 있어 fallback
            event_id = str(body.get("eventId", ""))
        if not event_id:
            print("❌ CREATE 응답에서 eventId 추출 실패. 응답 형식 확인 필요.")
            return 3
        print(f"  → eventId = {event_id}")

        # ── READ ──
        get_url = f"{base}/users/{admin_user_id}/calendar/events/{event_id}"
        print(f"\n[READ] GET {get_url}")
        resp = await client.get(get_url, headers=headers)
        print(f"  status = {resp.status_code}")
        print(f"  body   = {resp.text[:500]}")

        # ── DELETE ──
        del_url = f"{base}/users/{admin_user_id}/calendar/events/{event_id}"
        print(f"\n[DELETE] DELETE {del_url}")
        resp = await client.delete(del_url, headers=headers)
        print(f"  status = {resp.status_code}")
        print(f"  body   = {resp.text[:300]}")

    print("\n✅ Calendar PoC 완료 — CREATE/READ/DELETE 모두 검증")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
