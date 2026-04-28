"""sso_works 단위 테스트 — upsert/도메인/콜백 흐름.

OIDC 토큰/JWKS 검증은 monkeypatch로 mock (RS256 키 생성을 테스트에서 회피).
DATABASE_URL/JWT_SECRET은 conftest.py가 처리.
"""
from __future__ import annotations

import asyncio

import pytest

from app.db import SessionLocal
from app.models.auth import User
from app.services import sso_works


@pytest.fixture(autouse=True)
def _works_env(monkeypatch):
    """SSO 활성 + 도메인 검증값을 매 테스트에 보장."""
    monkeypatch.setenv("WORKS_ENABLED", "true")
    monkeypatch.setenv("WORKS_CLIENT_ID", "test-client")
    monkeypatch.setenv("WORKS_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("WORKS_DOMAIN_ID", "1234567")
    monkeypatch.setenv(
        "WORKS_REDIRECT_URI", "https://api.dyce.kr/api/auth/works/callback"
    )
    monkeypatch.setenv("FRONTEND_BASE_URL", "https://task.dyce.kr")
    yield


@pytest.fixture
def db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_upsert_user_new_creates_active_member(db) -> None:
    user, created = sso_works.upsert_user(
        db, works_user_id="W-1", email="alice@dyce.kr", name="앨리스"
    )
    db.commit()
    assert created is True
    assert user.status == "active"
    assert user.role == "member"
    assert user.auth_provider == "works"
    assert user.username == "alice"
    assert user.works_user_id == "W-1"
    assert user.password


def test_upsert_user_existing_email_links_to_works(db) -> None:
    existing = User(
        username="bob",
        password="oldhash",
        email="bob@dyce.kr",
        name="밥",
        role="team_lead",
        status="active",
        auth_provider="password",
    )
    db.add(existing)
    db.commit()

    user, created = sso_works.upsert_user(
        db, works_user_id="W-2", email="bob@dyce.kr", name="밥"
    )
    db.commit()
    assert created is False
    assert user.id == existing.id
    assert user.role == "team_lead"
    assert user.works_user_id == "W-2"
    assert user.auth_provider == "both"


def test_upsert_user_rejects_outside_domain(db) -> None:
    with pytest.raises(sso_works.SSOError):
        sso_works.upsert_user(
            db, works_user_id="W-3", email="cathy@gmail.com", name="C"
        )


def test_upsert_user_username_conflict_suffix(db) -> None:
    db.add(
        User(
            username="dave",
            password="x",
            email="",
            role="member",
            status="active",
            auth_provider="password",
        )
    )
    db.commit()
    user, created = sso_works.upsert_user(
        db, works_user_id="W-4", email="dave@dyce.kr", name="데이브"
    )
    db.commit()
    assert created is True
    assert user.username == "dave2"


def test_upsert_user_re_login_no_new_row(db) -> None:
    sso_works.upsert_user(db, works_user_id="W-5", email="eve@dyce.kr", name="이브")
    db.commit()
    u2, created = sso_works.upsert_user(
        db, works_user_id="W-5", email="eve@dyce.kr", name="이브"
    )
    db.commit()
    assert created is False
    assert db.query(User).filter(User.email == "eve@dyce.kr").count() == 1
    assert u2.works_user_id == "W-5"


def test_domain_matches_variants() -> None:
    assert sso_works._domain_matches({"domainId": "1234567"}, "1234567")
    assert sso_works._domain_matches({"domain_id": "1234567"}, "1234567")
    assert sso_works._domain_matches({"domain": "1234567"}, "1234567")
    assert sso_works._domain_matches({"domainId": 1234567}, "1234567")
    assert not sso_works._domain_matches({"domainId": "9999"}, "1234567")
    assert sso_works._domain_matches({"domainId": "9999"}, "")


def test_extract_name_korean() -> None:
    assert (
        sso_works._extract_name(
            {"userName": {"lastName": "홍", "firstName": "길동"}}
        )
        == "홍길동"
    )
    assert sso_works._extract_name({"displayName": "Park"}) == "Park"
    assert sso_works._extract_name({}) == ""


def test_process_callback_happy_path(db, monkeypatch) -> None:
    async def fake_exchange(_settings, _code):
        return {"access_token": "fake-access-token"}

    async def fake_userinfo(_settings, _access_token):
        return {
            "userId": "W-100",
            "email": "frank@dyce.kr",
            "userName": {"lastName": "프", "firstName": "랭크"},
            "domainId": 1234567,
        }

    monkeypatch.setattr(sso_works, "exchange_code", fake_exchange)
    monkeypatch.setattr(sso_works, "fetch_user_info", fake_userinfo)

    user = asyncio.run(sso_works.process_callback(db, code="abc"))
    db.commit()
    assert user.email == "frank@dyce.kr"
    assert user.works_user_id == "W-100"
    assert user.status == "active"
    assert user.name == "프랭크"
    assert user.sso_login_at is not None


def test_process_callback_rejects_wrong_domain(db, monkeypatch) -> None:
    async def fake_exchange(_s, _c):
        return {"access_token": "fake"}

    async def fake_userinfo(_s, _t):
        return {
            "userId": "W-200",
            "email": "x@dyce.kr",
            "domainId": 9999,
        }

    monkeypatch.setattr(sso_works, "exchange_code", fake_exchange)
    monkeypatch.setattr(sso_works, "fetch_user_info", fake_userinfo)

    with pytest.raises(sso_works.SSOError):
        asyncio.run(sso_works.process_callback(db, code="c"))


def test_signed_state_round_trip() -> None:
    secret = "test-secret"
    state, nonce = sso_works.issue_state(secret, "/me")
    assert nonce
    assert "." in state
    data = sso_works.verify_state(secret, state)
    assert data["n"] == nonce
    assert data["x"] == "/me"


def test_signed_state_tamper_detected() -> None:
    secret = "test-secret"
    state, _ = sso_works.issue_state(secret, "/")
    payload, sig = state.rsplit(".", 1)
    # 서명을 다른 값으로 교체 → 검증 실패해야 함
    tampered = f"{payload}.{'a' * len(sig)}"
    with pytest.raises(sso_works.SSOError):
        sso_works.verify_state(secret, tampered)


def test_signed_state_wrong_secret() -> None:
    state, _ = sso_works.issue_state("secret-A", "/")
    with pytest.raises(sso_works.SSOError):
        sso_works.verify_state("secret-B", state)
