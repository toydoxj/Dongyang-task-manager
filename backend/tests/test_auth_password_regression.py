"""SSO 컬럼 추가 후 자체 비밀번호 흐름 회귀.

기존 password/JWT 로그인이 그대로 동작하는지 확인. DB/JWT는 conftest.py가 처리.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(autouse=True)
def _disable_works(monkeypatch):
    monkeypatch.setenv("WORKS_ENABLED", "false")
    monkeypatch.setenv("WORKS_CLIENT_ID", "")
    monkeypatch.setenv("WORKS_CLIENT_SECRET", "")
    yield


def test_password_flow_unchanged() -> None:
    with TestClient(app) as client:
        r = client.get("/api/auth/status")
        assert r.status_code == 200
        body = r.json()
        assert body["initialized"] is False
        assert body["works_enabled"] is False

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
        assert data["user"]["auth_provider"] == "password"

        # 로그인 (session_id 갱신 — 마지막 토큰만 유효)
        r = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "secret123"},
        )
        assert r.status_code == 200, r.text
        token = r.json()["access_token"]

        r = client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
        )
        assert r.status_code == 200
        me = r.json()
        assert me["username"] == "admin"
        assert me["auth_provider"] == "password"


def test_works_endpoints_503_when_disabled() -> None:
    with TestClient(app) as client:
        r = client.get("/api/auth/works/login", follow_redirects=False)
        assert r.status_code == 503
