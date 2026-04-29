"""NAVER WORKS Drive PoC — admin 위임 토큰이 DB에 저장된 후 동작 검증.

전제: /api/admin/drive/connect 흐름으로 admin이 한 번 동의 완료
      (drive_credentials 테이블에 row 1개 존재).

사용법 (backend/.venv 활성 후, 프로젝트 루트에서):
    backend/.venv/Scripts/python.exe scripts/works_drive_poc.py

검증:
    [1] drive_credentials 행 존재 + 만료까지 남은 시간
    [2] sharedrive 24101의 root 컨텐츠 list (5개 endpoint candidate fallback)
    [3] '[업무관리]' 폴더 자동 발견 → folderId 출력
    [4] (선택, RUN_PROJECT_TEST=1) [POC-2604]테스트프로젝트 폴더 생성 시도
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / "backend" / ".env")
except ImportError:
    pass

os.environ.setdefault("WORKS_DRIVE_SHAREDRIVE_ID", "24101")
os.environ.setdefault("WORKS_DRIVE_ROOT_FOLDER_ID", "3472612542255198729")
os.environ["WORKS_DRIVE_ENABLED"] = "true"

import httpx  # noqa: E402

from app.db import SessionLocal, init_db  # noqa: E402
from app.models.drive_creds import DriveCredential  # noqa: E402
from app.services import sso_drive  # noqa: E402
from app.settings import get_settings  # noqa: E402


async def _try_get(token: str, url: str) -> tuple[int, dict | str]:
    async with httpx.AsyncClient(timeout=15.0) as c:
        try:
            r = await c.get(url, headers={"Authorization": f"Bearer {token}"})
        except httpx.HTTPError as e:
            return -1, f"network error: {e}"
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, r.text[:500]


def _pretty(obj: object, *, max_chars: int = 1500) -> str:
    s = (
        json.dumps(obj, ensure_ascii=False, indent=2)
        if isinstance(obj, (dict, list))
        else str(obj)
    )
    return s if len(s) <= max_chars else s[:max_chars] + "... (truncated)"


async def main() -> None:
    get_settings.cache_clear()
    s = get_settings()
    print("[준비]")
    print(f"  client_id        = {s.works_client_id[:6]}...")
    print(f"  sharedrive_id    = {s.works_drive_sharedrive_id}")
    print(f"  api_base         = {s.works_api_base}")

    init_db()  # drive_credentials 보장
    db = SessionLocal()
    try:
        row = db.get(DriveCredential, 1)
    finally:
        db.close()

    print("\n[1] drive_credentials 상태")
    if row is None or not row.access_token:
        print(
            "  [FAIL] DB에 토큰 없음.\n"
            "  → 먼저 https://task.dyce.kr/admin/drive 에서 'WORKS Drive 연결' 클릭\n"
            "    또는 admin 계정으로 GET https://api.dyce.kr/api/admin/drive/connect"
        )
        return
    print(f"  [OK] 연결됨. scope={row.scope}, expires_at={row.expires_at}")

    print("\n[2] access_token 자동 로드 (만료 60초 전이면 refresh)...")
    try:
        token = await sso_drive._get_valid_access_token(s)
    except sso_drive.DriveError as e:
        print(f"  [FAIL] {e}")
        return
    print(f"  [OK] access_token len={len(token)}")

    sd = s.works_drive_sharedrive_id
    target_name = os.environ.get("POC_TARGET_FOLDER_NAME", "[업무관리]")

    print(f"\n[3a] sharedrive 목록 + 다양한 list endpoint 진단...")
    # 24101은 sharedrive ID가 아닐 가능성 (resourceLocation일 뿐) →
    # 우선 ID 없는 list 호출로 진짜 sharedrive ID들 확인
    diag_endpoints = [
        # sharedrive 자체 list (ID 없음)
        f"{s.works_api_base}/sharedrives",
        # 공유 폴더(team folder) list — sharedrive와 다른 개념일 수도
        f"{s.works_api_base}/sharedfolders",
        # my drive root (개인 드라이브)
        f"{s.works_api_base}/drive/files",
    ]
    for url in diag_endpoints:
        code, body = await _try_get(token, url)
        ok = "[OK]" if 200 <= (code if isinstance(code, int) else 0) < 300 else "[FAIL]"
        print(f"  {ok} GET {url} -> {code}")
        if isinstance(code, int) and 200 <= code < 300:
            print(f"        본문 발췌: {_pretty(body, max_chars=800)}")
        elif isinstance(code, int) and 400 <= code < 500:
            snippet = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)
            print(f"        body: {snippet[:200]}")

    # 위 결과에서 sharedrive 또는 folder ID를 사용자에게 안내
    print(f"\n[3b] 기존 sharedrive_id={sd} + root_id로 candidate 시도 (참고용)...")
    root_id = os.environ.get(
        "WORKS_DRIVE_ROOT_FOLDER_ID", "3472612542255198729"
    )
    candidates = [
        f"{s.works_api_base}/sharedrives/{sd}",
        f"{s.works_api_base}/sharedrives/{sd}/files",
        f"{s.works_api_base}/sharedrives/{sd}/files/{root_id}/children",
        # resourceKey 첫 segment(2001000000536760)도 ID 후보로 시도
        f"{s.works_api_base}/sharedrives/2001000000536760",
        f"{s.works_api_base}/sharedrives/2001000000536760/files",
        # files endpoint 자체 (sharedrive 명시 없이)
        f"{s.works_api_base}/files/{root_id}",
        f"{s.works_api_base}/drive/files/{root_id}",
        f"{s.works_api_base}/drive/files/{root_id}/children",
    ]

    success_url = ""
    success_body: dict | list | str | None = None
    for url in candidates:
        code, body = await _try_get(token, url)
        ok = "[OK]" if 200 <= (code if isinstance(code, int) else 0) < 300 else "[FAIL]"
        print(f"  {ok} GET {url} -> {code}")
        if isinstance(code, int) and 400 <= code < 500:
            snippet = (
                body
                if isinstance(body, str)
                else json.dumps(body, ensure_ascii=False)
            )
            print(f"        body: {snippet[:300]}")
        if isinstance(code, int) and 200 <= code < 300:
            success_url = url
            success_body = body
            break

    if not success_url:
        print(
            "\n  [경고] 모든 candidate 실패. service account가 아닌 user 토큰임에도 "
            "차단됨 → 그 admin user에게 [업무관리] 폴더 권한이 없는 것으로 추정."
        )
        return

    print(f"\n  --> 성공 endpoint: {success_url}")
    print(f"  --> 응답 본문 (truncated):\n{_pretty(success_body)}")

    items: list[dict] = []
    if isinstance(success_body, dict):
        for key in ("files", "items", "children", "folders", "list"):
            v = success_body.get(key)
            if isinstance(v, list):
                items = v
                print(f"\n  --> 응답 list 키: '{key}' (n={len(items)})")
                break
    elif isinstance(success_body, list):
        items = success_body

    if not items:
        print("  [경고] 응답에서 list를 추출 못함. 위 raw 응답 확인.")
        return

    found = None
    for it in items:
        for nk in ("fileName", "name", "folderName", "displayName"):
            n = it.get(nk)
            if isinstance(n, str) and n == target_name:
                found = it
                break
        if found:
            break

    if not found:
        all_names = [
            it.get("fileName") or it.get("name") or it.get("folderName") or "?"
            for it in items
        ]
        print(
            f"\n  [경고] '{target_name}' 미발견. 현재 root: {all_names[:10]}"
        )
        return

    folder_id = ""
    for ik in ("fileId", "id", "folderId"):
        v = found.get(ik)
        if isinstance(v, str) and v:
            folder_id = v
            break
    folder_url = ""
    for uk in ("webUrl", "url", "shareUrl", "fileUrl"):
        v = found.get(uk)
        if isinstance(v, str) and v:
            folder_url = v
            break

    print(f"\n[4] '{target_name}' 폴더 발견:\n{_pretty(found)}")
    print("\n=========================================")
    print("Render 환경변수에 등록할 값:")
    print(f"  WORKS_DRIVE_SHAREDRIVE_ID    = {sd}")
    print(f"  WORKS_DRIVE_ROOT_FOLDER_ID   = {folder_id or '(추출 실패)'}")
    if folder_url:
        print(f"  (참고) 폴더 webUrl           = {folder_url}")
    print("=========================================")

    if os.environ.get("RUN_PROJECT_TEST") == "1" and folder_id:
        os.environ["WORKS_DRIVE_ROOT_FOLDER_ID"] = folder_id
        get_settings.cache_clear()
        s2 = get_settings()
        print("\n[5] [POC-2604]테스트프로젝트 폴더 생성 시도...")
        try:
            fid, url = await sso_drive.ensure_project_folder(
                s2, code="POC-2604", project_name="테스트프로젝트"
            )
            print(f"  [OK] folderId={fid}")
            print(f"  [OK] webUrl={url or '(URL 키 누락)'}")
        except sso_drive.DriveError as e:
            print(f"  [FAIL] {e}")


if __name__ == "__main__":
    asyncio.run(main())
