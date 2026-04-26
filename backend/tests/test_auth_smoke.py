"""인증 흐름 smoke 테스트 — register → login → me."""
from __future__ import annotations

import os
import tempfile

# 테스트는 격리된 SQLite 파일을 사용
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"
os.environ["JWT_SECRET"] = "test-secret"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def test_full_auth_flow() -> None:
    with TestClient(app) as client:
        _run_flow(client)


def _run_flow(client: TestClient) -> None:
    # 1. 초기 상태
    r = client.get("/api/auth/status")
    assert r.status_code == 200
    assert r.json()["initialized"] is False

    # 2. 최초 사용자 등록 → admin
    r = client.post(
        "/api/auth/register",
        json={"username": "admin", "password": "secret123", "name": "관리자"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["user"]["role"] == "admin"
    token = data["access_token"]
    assert token

    # 3. /me 호출
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["username"] == "admin"

    # 4. 로그인
    r = client.post(
        "/api/auth/login", json={"username": "admin", "password": "secret123"}
    )
    assert r.status_code == 200, r.text
    new_token = r.json()["access_token"]

    # 5. 잘못된 패스워드
    r = client.post(
        "/api/auth/login", json={"username": "admin", "password": "wrong"}
    )
    assert r.status_code == 401

    # 6. 두 번째 사용자는 직접 register 불가 (관리자 등록 필요)
    r = client.post(
        "/api/auth/register",
        json={"username": "user1", "password": "pw", "name": "유저"},
    )
    assert r.status_code == 403

    # 7. 가입 신청은 가능
    r = client.post(
        "/api/auth/request",
        json={"username": "user1", "password": "pw", "name": "유저"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "pending"

    # 8. pending 상태로 로그인 시 403
    r = client.post(
        "/api/auth/login", json={"username": "user1", "password": "pw"}
    )
    assert r.status_code == 403

    # 9. 관리자가 승인
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

    # 10. 승인 후 로그인 성공
    r = client.post(
        "/api/auth/login", json={"username": "user1", "password": "pw"}
    )
    assert r.status_code == 200
