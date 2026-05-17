"""계약서 라우터 테스트 — PR-FH/1.

CRUD + 권한 (member 403) + 파일 업로드 mock + 파일 삭제 + 잘못된 입력 검증.
SQLite 테스트 DB라 mirror_projects도 임시 row 직접 insert.
"""
from __future__ import annotations

import io

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient

from datetime import datetime, timezone

from app.db import SessionLocal, init_db
from app.main import app
from app.models.auth import User, UserSession
from app.models.contract import ContractOut
from app.security import create_token


# 테스트 격리용 — 프로젝트 정보 stub (SQLite에서 mirror_* 미지원 회피).
_PROJECT_REGISTRY: dict[str, dict[str, str]] = {}
# PR-FI/1: contract sync helper 호출 횟수 추적.
_SYNC_CALL_LOG: list[str] = []


@pytest.fixture(autouse=True)
def _disable_works(monkeypatch):
    monkeypatch.setenv("WORKS_ENABLED", "false")
    monkeypatch.setenv("WORKS_BOT_ENABLED", "false")
    monkeypatch.setenv("WORKS_DRIVE_ENABLED", "false")
    yield


@pytest.fixture(autouse=True)
def _stub_mirror_projects(monkeypatch):
    """contracts router의 mirror_projects 의존 helper 3종을 in-memory dict로 대체.

    SQLite test 환경엔 mirror_* 테이블이 없으므로 routers/contracts.py의
    `_ensure_project_exists` / `_get_project_code` / `_enrich_with_project` /
    `_list_project_ids_by_client`를 stub.
    """
    _PROJECT_REGISTRY.clear()

    def stub_ensure(db, project_id):
        if project_id not in _PROJECT_REGISTRY:
            from fastapi import HTTPException

            raise HTTPException(status_code=400, detail="존재하지 않는 프로젝트입니다")

    def stub_get_code(db, project_id):
        return _PROJECT_REGISTRY.get(project_id, {}).get("code", "")

    async def stub_resolve_folder(db, project_id):
        # 테스트에서는 Drive helper 자체를 monkeypatch하므로 호출되지 않음.
        # 그래도 fallback으로 stub 등록.
        return f"sub-folder-{project_id}"

    async def stub_sync_project(db, notion, project_id):
        # 노션 sync는 별 fixture에서 호출 횟수만 추적 — 여기서는 no-op.
        _SYNC_CALL_LOG.append(project_id)

    def stub_enrich(db, rows):
        out = []
        for r in rows:
            item = ContractOut.model_validate(r)
            meta = _PROJECT_REGISTRY.get(r.project_id, {})
            item.project_code = meta.get("code") or None
            item.project_name = meta.get("name") or None
            item.client_id = meta.get("client_id") or None
            item.client_name = meta.get("client_name") or None
            out.append(item)
        return out

    def stub_list_by_client(db, client_id):
        return [
            pid
            for pid, meta in _PROJECT_REGISTRY.items()
            if meta.get("client_id") == client_id
        ]

    monkeypatch.setattr("app.routers.contracts._ensure_project_exists", stub_ensure)
    monkeypatch.setattr("app.routers.contracts._get_project_code", stub_get_code)
    monkeypatch.setattr("app.routers.contracts._enrich_with_project", stub_enrich)
    monkeypatch.setattr(
        "app.routers.contracts._list_project_ids_by_client", stub_list_by_client
    )
    monkeypatch.setattr(
        "app.routers.contracts._resolve_project_contract_folder",
        stub_resolve_folder,
    )
    monkeypatch.setattr(
        "app.routers.contracts._sync_project_contract_fields",
        stub_sync_project,
    )
    _SYNC_CALL_LOG.clear()
    yield


@pytest.fixture
def db():
    init_db()
    s = SessionLocal()
    try:
        from sqlalchemy import inspect, text

        insp = inspect(s.bind)
        for tbl in ("contracts", "user_sessions"):
            if insp.has_table(tbl):
                s.execute(text(f"DELETE FROM {tbl}"))
        s.commit()
        yield s
    finally:
        s.close()


def _mk_user(db, *, role: str, name: str = "Tester") -> tuple[User, str]:
    u = User(
        username=f"{name.lower()}_{role}",
        password="x",
        email=f"{name.lower()}_{role}@dyce.kr",
        name=name,
        role=role,
        status="active",
        auth_provider="works",
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    sid = f"sid-{u.id}"
    # client 단위 활성 세션 등록 (security.get_current_user 검증 통과용).
    db.add(
        UserSession(
            user_id=u.id,
            client="task",
            session_id=sid,
            created_at=datetime.now(timezone.utc),
        )
    )
    db.commit()
    token = create_token(u.username, u.role, sid, client="task")
    return u, token


def _mk_project(
    db,
    *,
    page_id: str,
    code: str = "P-001",
    name: str = "프로젝트",
    client_id: str = "",
    client_name: str = "",
) -> None:
    """mirror_projects 대신 in-memory registry에 등록 (stub 사용)."""
    _PROJECT_REGISTRY[page_id] = {
        "code": code,
        "name": name,
        "client_id": client_id,
        "client_name": client_name,
    }


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── CRUD / 권한 ──────────────────────────────────────────────────────────


def test_admin_create_list_get_patch_delete(db) -> None:
    _, admin_token = _mk_user(db, role="admin", name="Admin")
    _mk_project(db, page_id="proj-001", code="P-001", name="A 빌딩 구조보강")

    with TestClient(app) as client:
        # create
        r = client.post(
            "/api/contracts",
            json={
                "project_id": "proj-001",
                "title": "원계약서",
                "signed_date": "2026-01-15",
                "start_date": "2026-02-01",
                "end_date": "2026-12-31",
                "amount": 50_000_000,
                "vat_included": False,
                "note": "초기 계약",
            },
            headers=_auth(admin_token),
        )
        assert r.status_code == 201, r.text
        body = r.json()
        contract_id = body["id"]
        assert body["title"] == "원계약서"
        assert body["amount"] == 50_000_000
        assert body["project_code"] == "P-001"
        assert body["project_name"] == "A 빌딩 구조보강"
        assert body["drive_file_id"] is None

        # list
        r = client.get("/api/contracts", headers=_auth(admin_token))
        assert r.status_code == 200
        assert r.json()["count"] == 1

        # get
        r = client.get(f"/api/contracts/{contract_id}", headers=_auth(admin_token))
        assert r.status_code == 200
        assert r.json()["title"] == "원계약서"

        # patch
        r = client.patch(
            f"/api/contracts/{contract_id}",
            json={"amount": 55_000_000, "note": "변경"},
            headers=_auth(admin_token),
        )
        assert r.status_code == 200
        assert r.json()["amount"] == 55_000_000

        # delete
        r = client.delete(
            f"/api/contracts/{contract_id}", headers=_auth(admin_token)
        )
        assert r.status_code == 204

        # 재조회 → 404
        r = client.get(f"/api/contracts/{contract_id}", headers=_auth(admin_token))
        assert r.status_code == 404


def test_member_get_allowed_but_cud_403(db) -> None:
    _, admin_token = _mk_user(db, role="admin", name="Admin")
    _, member_token = _mk_user(db, role="member", name="Member")
    _mk_project(db, page_id="proj-002")

    with TestClient(app) as client:
        # admin이 row 1건 미리 생성
        r = client.post(
            "/api/contracts",
            json={"project_id": "proj-002", "title": "원계약서"},
            headers=_auth(admin_token),
        )
        assert r.status_code == 201
        cid = r.json()["id"]

        # member GET 허용
        r = client.get("/api/contracts", headers=_auth(member_token))
        assert r.status_code == 200
        r = client.get(f"/api/contracts/{cid}", headers=_auth(member_token))
        assert r.status_code == 200

        # member POST/PATCH/DELETE → 403
        r = client.post(
            "/api/contracts",
            json={"project_id": "proj-002", "title": "x"},
            headers=_auth(member_token),
        )
        assert r.status_code == 403
        r = client.patch(
            f"/api/contracts/{cid}", json={"title": "x"}, headers=_auth(member_token)
        )
        assert r.status_code == 403
        r = client.delete(
            f"/api/contracts/{cid}", headers=_auth(member_token)
        )
        assert r.status_code == 403


def test_team_lead_and_manager_can_cud(db) -> None:
    _, lead_token = _mk_user(db, role="team_lead", name="Lead")
    _, mgr_token = _mk_user(db, role="manager", name="Mgr")
    _mk_project(db, page_id="proj-003")

    with TestClient(app) as client:
        r = client.post(
            "/api/contracts",
            json={"project_id": "proj-003", "title": "팀장 생성"},
            headers=_auth(lead_token),
        )
        assert r.status_code == 201
        r = client.post(
            "/api/contracts",
            json={"project_id": "proj-003", "title": "관리팀 생성"},
            headers=_auth(mgr_token),
        )
        assert r.status_code == 201


def test_create_unknown_project_400(db) -> None:
    _, admin_token = _mk_user(db, role="admin")
    with TestClient(app) as client:
        r = client.post(
            "/api/contracts",
            json={"project_id": "nope", "title": "x"},
            headers=_auth(admin_token),
        )
        assert r.status_code == 400


def test_create_end_before_start_400(db) -> None:
    _, admin_token = _mk_user(db, role="admin")
    _mk_project(db, page_id="proj-004")
    with TestClient(app) as client:
        r = client.post(
            "/api/contracts",
            json={
                "project_id": "proj-004",
                "title": "x",
                "start_date": "2026-12-01",
                "end_date": "2026-01-01",
            },
            headers=_auth(admin_token),
        )
        assert r.status_code == 400


def test_patch_nonexistent_404(db) -> None:
    _, admin_token = _mk_user(db, role="admin")
    with TestClient(app) as client:
        r = client.patch(
            "/api/contracts/9999",
            json={"title": "x"},
            headers=_auth(admin_token),
        )
        assert r.status_code == 404


# ── 파일 업로드 / 삭제 (Drive helper mock) ──────────────────────────────


def test_upload_file_and_delete_file_with_mock(db, monkeypatch) -> None:
    """sso_drive helper를 monkeypatch — 실제 NAVER WORKS 호출 없이 흐름 검증."""
    _, admin_token = _mk_user(db, role="admin")
    _mk_project(db, page_id="proj-005", code="P-005")

    fake_calls: list[str] = []

    async def fake_upload_file(parent_id, file_name, content, *, content_type=None, settings=None):
        fake_calls.append(f"upload:{parent_id}:{file_name}:{len(content)}")
        return {"fileId": "drive-file-1", "fileUrl": "https://drive/file/1"}

    async def fake_delete_file(file_id, *, settings=None):
        fake_calls.append(f"delete:{file_id}")

    # PR-FI/1: _resolve_project_contract_folder는 autouse fixture가 이미 stub.
    # 여기서는 sso_drive 직접 호출(upload/delete)만 mock.
    monkeypatch.setattr("app.routers.contracts.sso_drive.upload_file", fake_upload_file)
    monkeypatch.setattr("app.routers.contracts.sso_drive.delete_file", fake_delete_file)

    with TestClient(app) as client:
        # 메타만 생성
        r = client.post(
            "/api/contracts",
            json={"project_id": "proj-005", "title": "원계약서"},
            headers=_auth(admin_token),
        )
        assert r.status_code == 201
        cid = r.json()["id"]

        # 파일 업로드
        r = client.post(
            f"/api/contracts/{cid}/file",
            files={"file": ("계약서.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")},
            headers=_auth(admin_token),
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["drive_file_id"] == "drive-file-1"
        assert body["file_name"] == "계약서.pdf"
        assert body["uploaded_at"] is not None
        # PR-FI/1: resolve_folder는 stub_resolve_folder가 가짜 id 반환 → upload 1회만.
        upload_calls = [c for c in fake_calls if c.startswith("upload")]
        assert len(upload_calls) == 1
        assert "proj-005" in upload_calls[0]
        assert "계약서.pdf" in upload_calls[0]

        # 파일 삭제
        r = client.delete(
            f"/api/contracts/{cid}/file", headers=_auth(admin_token)
        )
        assert r.status_code == 200
        body = r.json()
        assert body["drive_file_id"] is None
        assert body["file_name"] is None
        assert "delete:drive-file-1" in fake_calls


def test_upload_rejects_unknown_extension(db, monkeypatch) -> None:
    _, admin_token = _mk_user(db, role="admin")
    _mk_project(db, page_id="proj-006")
    with TestClient(app) as client:
        r = client.post(
            "/api/contracts",
            json={"project_id": "proj-006", "title": "x"},
            headers=_auth(admin_token),
        )
        cid = r.json()["id"]
        r = client.post(
            f"/api/contracts/{cid}/file",
            files={"file": ("evil.exe", io.BytesIO(b"MZ"), "application/octet-stream")},
            headers=_auth(admin_token),
        )
        assert r.status_code == 400
        assert "허용되지 않은" in r.json()["detail"]
