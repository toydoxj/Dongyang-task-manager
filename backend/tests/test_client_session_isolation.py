"""(user_id, client) 단위 활성 세션 분리 검증.

- 같은 user 가 'task' 와 'dy-midas' 에서 동시 활성 세션을 보유.
- 같은 client 내 재로그인은 직전 sid 무효화 (single-session per client).
- 레거시 토큰(cli claim 없음)은 users.session_id fallback 으로 검증.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import inspect as sa_inspect

from app.db import SessionLocal
from app.models.auth import User, UserSession
from app.routers.auth import update_me
from app.security import create_token, get_auth_channel_stats, get_current_user
from app.services import sso_works


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _bearer(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def _make_user(db, *, username: str = "alice", email: str = "alice@dyce.kr") -> User:
    user = User(
        username=username,
        password="x",
        email=email,
        name=username,
        role="member",
        status="active",
        auth_provider="works",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _set_session(db, user_id: int, client: str, sid: str) -> None:
    from datetime import datetime, timezone

    sess = (
        db.query(UserSession)
        .filter(UserSession.user_id == user_id, UserSession.client == client)
        .first()
    )
    now = datetime.now(timezone.utc)
    if sess is None:
        db.add(
            UserSession(
                user_id=user_id, client=client, session_id=sid, created_at=now
            )
        )
    else:
        sess.session_id = sid
        sess.created_at = now
    db.commit()


# ── issue_state / verify_state ─────────────────────────────────────────────


def test_issue_state_default_client_task() -> None:
    state, _ = sso_works.issue_state("secret", "/")
    data = sso_works.verify_state("secret", state)
    assert data["c"] == "task"


def test_issue_state_explicit_client_dy_midas() -> None:
    state, _ = sso_works.issue_state("secret", "/", client="dy-midas")
    data = sso_works.verify_state("secret", state)
    assert data["c"] == "dy-midas"


# ── create_token ───────────────────────────────────────────────────────────


def test_create_token_includes_cli_claim() -> None:
    from app.security import decode_token

    token = create_token("alice", "member", "sid-1", client="dy-midas")
    payload = decode_token(token)
    assert payload["cli"] == "dy-midas"
    assert payload["sid"] == "sid-1"


def test_create_token_default_client_task() -> None:
    from app.security import decode_token

    token = create_token("alice", "member", "sid-1")
    payload = decode_token(token)
    assert payload["cli"] == "task"


# ── get_current_user 검증 ───────────────────────────────────────────────────


def test_two_clients_can_have_active_sessions_simultaneously(db) -> None:
    """task 에서 로그인 후 dy-midas 에서 또 로그인해도 task 세션이 유효."""
    user = _make_user(db)
    _set_session(db, user.id, "task", "sid-task-1")
    _set_session(db, user.id, "dy-midas", "sid-midas-1")

    token_task = create_token(user.username, user.role, "sid-task-1", client="task")
    token_midas = create_token(
        user.username, user.role, "sid-midas-1", client="dy-midas"
    )

    u_task = get_current_user(_bearer(token_task), db)
    u_midas = get_current_user(_bearer(token_midas), db)
    assert u_task.id == user.id
    assert u_midas.id == user.id


def test_re_login_in_same_client_invalidates_previous_session(db) -> None:
    """dy-midas 에서 두 번 로그인하면 첫 번째 sid 는 무효."""
    user = _make_user(db)
    _set_session(db, user.id, "dy-midas", "sid-old")
    token_old = create_token(
        user.username, user.role, "sid-old", client="dy-midas"
    )
    # 동일 client 에서 새 로그인 → 직전 sid 덮어쓰기
    _set_session(db, user.id, "dy-midas", "sid-new")

    with pytest.raises(HTTPException) as exc:
        get_current_user(_bearer(token_old), db)
    assert exc.value.status_code == 401

    token_new = create_token(
        user.username, user.role, "sid-new", client="dy-midas"
    )
    u = get_current_user(_bearer(token_new), db)
    assert u.id == user.id


def test_dy_midas_login_does_not_invalidate_task_session(db) -> None:
    """dy-midas 신규 로그인이 task sid 를 침범하지 않음."""
    user = _make_user(db)
    _set_session(db, user.id, "task", "sid-task")
    token_task = create_token(
        user.username, user.role, "sid-task", client="task"
    )
    # dy-midas 에서 새로 로그인 (task 는 건드리지 않아야 함)
    _set_session(db, user.id, "dy-midas", "sid-midas")

    u = get_current_user(_bearer(token_task), db)
    assert u.id == user.id


def test_get_current_user_releases_read_transaction(db) -> None:
    """인증 조회 후 응답 처리 동안 DB connection을 잡고 있지 않도록 분리한다."""
    user = _make_user(db)
    _set_session(db, user.id, "task", "sid-task")
    token = create_token(user.username, user.role, "sid-task", client="task")

    u = get_current_user(_bearer(token), db)

    assert u.id == user.id
    assert u.role == "member"
    assert sa_inspect(u).detached
    assert not db.in_transaction()


def test_update_me_persists_with_detached_current_user(db) -> None:
    """get_current_user가 detached User를 반환해도 /me 수정은 route db에서 저장된다."""
    from app.models.auth import UserUpdateRequest

    user = _make_user(db)
    _set_session(db, user.id, "task", "sid-task")
    token = create_token(user.username, user.role, "sid-task", client="task")
    current_user = get_current_user(_bearer(token), db)

    info = update_me(UserUpdateRequest(name="alice-updated"), current_user, db)

    db.expire_all()
    saved = db.get(User, user.id)
    assert info.name == "alice-updated"
    assert saved is not None
    assert saved.name == "alice-updated"


def test_legacy_token_without_cli_uses_users_session_id(db) -> None:
    """cli claim 없는 레거시 토큰은 users.session_id 와 비교."""
    from datetime import datetime, timedelta, timezone

    from jose import jwt

    from app.settings import get_settings

    user = _make_user(db, username="bob", email="bob@dyce.kr")
    user.session_id = "legacy-sid"
    db.commit()

    s = get_settings()
    payload = {
        "sub": user.username,
        "role": user.role,
        "sid": "legacy-sid",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=60),
    }
    token = jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)

    u = get_current_user(_bearer(token), db)
    assert u.id == user.id


def test_legacy_token_with_stale_sid_rejected(db) -> None:
    """레거시 토큰의 sid 와 users.session_id 가 다르면 401."""
    from datetime import datetime, timedelta, timezone

    from jose import jwt

    from app.settings import get_settings

    user = _make_user(db, username="carol", email="carol@dyce.kr")
    user.session_id = "current-sid"
    db.commit()

    s = get_settings()
    payload = {
        "sub": user.username,
        "role": user.role,
        "sid": "stale-sid",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=60),
    }
    token = jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)

    with pytest.raises(HTTPException) as exc:
        get_current_user(_bearer(token), db)
    assert exc.value.status_code == 401


def test_token_with_cli_but_no_session_row_rejected(db) -> None:
    """cli 토큰인데 user_sessions 행이 없으면 401 (재로그인 필요)."""
    user = _make_user(db, username="dave", email="dave@dyce.kr")
    token = create_token(user.username, user.role, "sid-x", client="dy-midas")
    with pytest.raises(HTTPException) as exc:
        get_current_user(_bearer(token), db)
    assert exc.value.status_code == 401


# ── auth channel shadow telemetry ───────────────────────────────────────────


def test_header_auth_records_valid_cookie_shadow(db) -> None:
    """헤더 인증이어도 같은 사용자 cookie가 유효하면 전환 가능으로 집계."""
    user = _make_user(db, username="erin", email="erin@dyce.kr")
    _set_session(db, user.id, "task", "sid-task")
    token = create_token(user.username, user.role, "sid-task", client="task")
    before = get_auth_channel_stats()

    u = get_current_user(_bearer(token), db, dy_jwt=token)
    after = get_auth_channel_stats()

    assert u.id == user.id
    assert after["header_with_valid_cookie"] == (
        before["header_with_valid_cookie"] + 1
    )
    assert after["cookie_ready"] == before["cookie_ready"] + 1


def test_header_auth_records_missing_cookie_shadow(db) -> None:
    """헤더 인증에 cookie가 없으면 header 제거 시 위험으로 집계."""
    user = _make_user(db, username="frank", email="frank@dyce.kr")
    _set_session(db, user.id, "task", "sid-task")
    token = create_token(user.username, user.role, "sid-task", client="task")
    before = get_auth_channel_stats()

    u = get_current_user(_bearer(token), db)
    after = get_auth_channel_stats()

    assert u.id == user.id
    assert after["header_without_cookie"] == before["header_without_cookie"] + 1
    assert after["cookie_blocked"] == before["cookie_blocked"] + 1


def test_header_auth_records_invalid_cookie_shadow(db) -> None:
    """cookie가 있어도 sid가 낡았으면 header 제거 시 위험으로 집계."""
    user = _make_user(db, username="grace", email="grace@dyce.kr")
    _set_session(db, user.id, "task", "sid-current")
    header_token = create_token(
        user.username, user.role, "sid-current", client="task"
    )
    cookie_token = create_token(user.username, user.role, "sid-old", client="task")
    before = get_auth_channel_stats()

    u = get_current_user(_bearer(header_token), db, dy_jwt=cookie_token)
    after = get_auth_channel_stats()

    assert u.id == user.id
    assert after["header_with_invalid_cookie"] == (
        before["header_with_invalid_cookie"] + 1
    )
    assert after["cookie_blocked"] == before["cookie_blocked"] + 1


def test_header_auth_records_mismatched_cookie_shadow(db) -> None:
    """다른 사용자 cookie는 유효하더라도 안전한 cookie-only 전환으로 보지 않음."""
    header_user = _make_user(db, username="heidi", email="heidi@dyce.kr")
    cookie_user = _make_user(db, username="ivan", email="ivan@dyce.kr")
    _set_session(db, header_user.id, "task", "sid-header")
    _set_session(db, cookie_user.id, "task", "sid-cookie")
    header_token = create_token(
        header_user.username, header_user.role, "sid-header", client="task"
    )
    cookie_token = create_token(
        cookie_user.username, cookie_user.role, "sid-cookie", client="task"
    )
    before = get_auth_channel_stats()

    u = get_current_user(_bearer(header_token), db, dy_jwt=cookie_token)
    after = get_auth_channel_stats()

    assert u.id == header_user.id
    assert after["header_with_mismatched_cookie"] == (
        before["header_with_mismatched_cookie"] + 1
    )
    assert after["cookie_blocked"] == before["cookie_blocked"] + 1
