"""NAVER WORKS Drive PoC — Service Account JWT + 공유 드라이브 폴더 검증.

사용법 (backend/.venv 활성 후, 프로젝트 루트에서):
    backend/.venv/Scripts/python.exe scripts/works_drive_poc.py

필수 환경변수 (backend/.env 또는 export):
    WORKS_CLIENT_ID
    WORKS_CLIENT_SECRET
    WORKS_SERVICE_ACCOUNT_ID
    WORKS_PRIVATE_KEY              (PEM. 줄바꿈은 실제 LF 또는 \\n)

선택 환경변수 (없으면 사용자가 보낸 URL에서 추출한 값을 default로):
    WORKS_DRIVE_SHAREDRIVE_ID      (default: 24101)
    POC_TARGET_FOLDER_NAME         (default: [업무관리])

검증 단계:
    [1] access_token 발급
    [2] sharedrive 24101의 루트 컨텐츠를 여러 candidate endpoint로 시도 → raw 응답 출력
    [3] 응답에서 '[업무관리]' 이름 매칭 → folderId 출력
    [4] (선택, 환경변수 RUN_PROJECT_TEST=1) [POC-2604]테스트프로젝트 폴더 생성 시도
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

# 사용자가 보낸 URL에서 추출된 값을 default로 박음 (사용자 입력 부담 줄이기)
os.environ.setdefault("WORKS_DRIVE_SHAREDRIVE_ID", "24101")
os.environ.setdefault("WORKS_DRIVE_ROOT_FOLDER_ID", "3472612542255198729")
os.environ["WORKS_DRIVE_ENABLED"] = "true"

import httpx  # noqa: E402

from app.services import sso_drive  # noqa: E402
from app.settings import get_settings  # noqa: E402


def _short(v: str) -> str:
    return v[:6] + "..." if v else "(empty)"


async def _try_get(token: str, url: str) -> tuple[int, dict | str]:
    async with httpx.AsyncClient(timeout=15.0) as c:
        try:
            r = await c.get(
                url, headers={"Authorization": f"Bearer {token}"}
            )
        except httpx.HTTPError as e:
            return -1, f"network error: {e}"
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, r.text[:500]


def _pretty(obj: object, *, max_chars: int = 1500) -> str:
    s = json.dumps(obj, ensure_ascii=False, indent=2) if isinstance(obj, (dict, list)) else str(obj)
    return s if len(s) <= max_chars else s[:max_chars] + "... (truncated)"


async def main() -> None:
    get_settings.cache_clear()
    s = get_settings()
    print("[준비]")
    print(f"  client_id        = {_short(s.works_client_id)}")
    print(f"  service_account  = {_short(s.works_service_account_id)}")
    print(f"  sharedrive_id    = {s.works_drive_sharedrive_id}")
    print(f"  api_base         = {s.works_api_base}")

    # [1] token
    print("\n[1] access_token 발급 시도...")
    try:
        token, exp = await sso_drive._request_access_token(s)
        print(f"  ✓ access_token 발급 OK (expires_in={exp}, len={len(token)})")
    except sso_drive.DriveError as e:
        print(f"  ✗ 실패: {e}")
        return

    sd = s.works_drive_sharedrive_id
    target_name = os.environ.get("POC_TARGET_FOLDER_NAME", "[업무관리]")

    # [2] root children — 여러 endpoint candidate 시도
    print(f"\n[2] sharedrive {sd} 루트 컨텐츠 조회 (여러 path 시도)...")
    candidates = [
        f"{s.works_api_base}/sharedrives/{sd}/files",
        f"{s.works_api_base}/sharedrives/{sd}/folders/root/children",
        f"{s.works_api_base}/sharedrives/{sd}/files/root/children",
        f"{s.works_api_base}/sharedrives/{sd}/items",
        f"{s.works_api_base}/drive/sharedrives/{sd}/files",
    ]

    success_url = ""
    success_body: dict | list | str | None = None
    for url in candidates:
        code, body = await _try_get(token, url)
        ok = "✓" if 200 <= (code if isinstance(code, int) else 0) < 300 else "✗"
        print(f"  {ok} GET {url} → {code}")
        if isinstance(code, int) and 200 <= code < 300:
            success_url = url
            success_body = body
            break

    if not success_url:
        print(
            "\n  [경고] 모든 candidate가 실패. NAVER WORKS Console에서 service "
            "account에 [업무관리] 폴더 권한이 부여됐는지 확인 필요."
        )
        return

    print(f"\n  ▷ 성공 endpoint: {success_url}")
    print(f"  ▷ 응답 본문 (truncated):\n{_pretty(success_body)}")

    # [3] 자식 목록에서 target_name 매칭
    items: list[dict] = []
    if isinstance(success_body, dict):
        for key in ("files", "items", "children", "folders", "list"):
            v = success_body.get(key)
            if isinstance(v, list):
                items = v
                print(f"\n  ▷ 응답 list 키: '{key}' (n={len(items)})")
                break
    elif isinstance(success_body, list):
        items = success_body

    if not items:
        print(f"  [경고] 응답에서 list를 추출하지 못함. 위 raw 응답을 보고 키 확인 필요.")
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
            f"\n  [경고] '{target_name}' 폴더를 못 찾음. "
            f"공유 드라이브에 [업무관리] 폴더가 만들어졌는지 + service account에 "
            f"권한이 부여됐는지 확인.\n  현재 root에 보이는 항목: {all_names[:10]}"
        )
        return

    print(f"\n[3] '{target_name}' 폴더 발견:")
    print(_pretty(found))

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

    print("\n=========================================")
    print("Render 환경변수에 등록할 값:")
    print(f"  WORKS_DRIVE_SHAREDRIVE_ID    = {sd}")
    print(f"  WORKS_DRIVE_ROOT_FOLDER_ID   = {folder_id or '(추출 실패 — 위 응답에서 확인)'}")
    if folder_url:
        print(f"  (참고) 폴더 webUrl           = {folder_url}")
    print("=========================================")

    # [4] 선택적 폴더 생성 시도
    if os.environ.get("RUN_PROJECT_TEST") == "1":
        if not folder_id:
            print("\n[4] folder_id 미확정으로 폴더 생성 테스트 건너뜀")
            return
        os.environ["WORKS_DRIVE_ROOT_FOLDER_ID"] = folder_id
        get_settings.cache_clear()
        s2 = get_settings()
        print("\n[4] [POC-2604]테스트프로젝트 폴더 생성 시도...")
        try:
            fid, url = await sso_drive.ensure_project_folder(
                s2, code="POC-2604", project_name="테스트프로젝트"
            )
            print(f"  ✓ folderId={fid}")
            print(f"  ✓ webUrl={url or '(URL 키 누락 — 응답에서 키 이름 확인 필요)'}")
        except sso_drive.DriveError as e:
            print(f"  ✗ 실패: {e}")


if __name__ == "__main__":
    asyncio.run(main())
