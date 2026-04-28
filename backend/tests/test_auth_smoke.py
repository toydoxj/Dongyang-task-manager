"""인증 흐름 smoke 테스트 — register → login → me. DB/JWT는 conftest.py가 처리."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_full_auth_flow() -> None:
    with TestClient(app) as client:
        _run_flow(client)


def _run_flow(client: TestClient) -> None:
    # 1. 초기 상태
    r = client.get("/api/auth/status")
    assert r.status_code == 200
    assert r.json()["initialized"] is False

    # 2. 최초 사용자 등록 → admin (회사 이메일 강제)
    r = client.post(
        "/api/auth/register",
        json={
            "username": "admin",
            "password": "secret123",
            "name": "관리자",
            "email": "admin@dyce.kr",
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["user"]["role"] == "admin"

    # 3. 로그인 (session_id 갱신 — 직전 토큰 무효화 흐름 보존)
    r = client.post(
        "/api/auth/login", json={"username": "admin", "password": "secret123"}
    )
    assert r.status_code == 200, r.text
    new_token = r.json()["access_token"]

    # 4. /me 호출 (로그인 후 토큰)
    r = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {new_token}"}
    )
    assert r.status_code == 200
    assert r.json()["username"] == "admin"

    # 5. 잘못된 패스워드
    r = client.post(
        "/api/auth/login", json={"username": "admin", "password": "wrong"}
    )
    assert r.status_code == 401

    # 6. 두 번째 사용자는 직접 register 불가 (관리자 등록 필요)
    r = client.post(
        "/api/auth/register",
        json={
            "username": "user1",
            "password": "pw",
            "name": "유저",
            "email": "user1@dyce.kr",
        },
    )
    assert r.status_code == 403

    # 7. 가입 신청은 가능
    r = client.post(
        "/api/auth/request",
        json={
            "username": "user1",
            "password": "pw",
            "name": "유저",
            "email": "user1@dyce.kr",
        },
    )
    assert r.status_code == 200
    # 직원 명부에 매칭이 없으면 pending, 있으면 active. 둘 다 허용.
    assert r.json()["status"] in {"pending", "active"}

    # 8. 가입 신청 결과에 따라 분기
    if r.json()["status"] == "pending":
        r = client.post(
            "/api/auth/login", json={"username": "user1", "password": "pw"}
        )
        assert r.status_code == 403  # 승인 대기

        users = client.get(
            "/api/auth/users", headers={"Authorization": f"Bearer {new_token}"}
        ).json()
        user1 = next(u for u in users if u["username"] == "user1")
        r = client.post(
            f"/api/auth/users/{user1['id']}/approve",
            headers={"Authorization": f"Bearer {new_token}"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "active"

    # 9. 승인된 상태로 로그인 성공
    r = client.post(
        "/api/auth/login", json={"username": "user1", "password": "pw"}
    )
    assert r.status_code == 200
