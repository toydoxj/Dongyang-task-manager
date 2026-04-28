"""SSO 전환 후 password 라우터가 완전히 사라졌는지 + /me·/users 흐름 회귀.

password 라우터(/login, /register, /request, /users POST)는 SSO 전용 정책에 따라 제거됨.
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


def test_password_endpoints_removed() -> None:
    """자체 비번 흐름 라우터는 존재하지 않아야 함 → 405 또는 404."""
    with TestClient(app) as client:
        for path in ("/api/auth/login", "/api/auth/register", "/api/auth/request"):
            r = client.post(
                path, json={"username": "x", "password": "y", "email": "x@dyce.kr"}
            )
            assert r.status_code in {404, 405}, f"{path}: {r.status_code} {r.text}"


def test_status_works_disabled() -> None:
    with TestClient(app) as client:
        r = client.get("/api/auth/status")
        assert r.status_code == 200
        body = r.json()
        assert body["works_enabled"] is False


def test_works_endpoints_503_when_disabled() -> None:
    with TestClient(app) as client:
        r = client.get("/api/auth/works/login", follow_redirects=False)
        assert r.status_code == 503
