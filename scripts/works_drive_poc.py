"""NAVER WORKS Drive PoC - admin 위임 토큰이 DB에 저장된 후 동작 검증.

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

    print(f"\n[3a] sharedrive 전체 목록...")
    code, body = await _try_get(token, f"{s.works_api_base}/sharedrives")
    if not (isinstance(code, int) and 200 <= code < 300):
        print(f"  [FAIL] {code}")
        return
    sharedrives = (body or {}).get("sharedrives") if isinstance(body, dict) else []
    if not isinstance(sharedrives, list) or not sharedrives:
        print(f"  [경고] sharedrives 비어 있음. raw: {_pretty(body, max_chars=2000)}")
        return
    print(f"  총 {len(sharedrives)}개 sharedrive 발견:")
    for sd_meta in sharedrives:
        print(
            f"    - {sd_meta.get('sharedriveId'):<24} "
            f"name='{sd_meta.get('name','')}'  "
            f"hasPerm={sd_meta.get('hasPermission')} "
            f"perm={sd_meta.get('permissionType','')}"
        )

    target_name = os.environ.get("POC_TARGET_FOLDER_NAME", "[업무관리]")

    # case 1: sharedrive 자체 이름이 target과 일치 → 그 sharedrive 사용
    self_match = next(
        (sd_meta for sd_meta in sharedrives if sd_meta.get("name") == target_name),
        None,
    )
    if self_match:
        sid = self_match.get("sharedriveId", "")
        print(
            f"\n[3b] '{target_name}' 가 sharedrive 자체로 발견: {sid}\n"
            f"     → root_folder_id로 sharedrive_id 자체를 사용 (NAVER WORKS sharedrive root 패턴)"
        )
        print("\n=========================================")
        print("Render 환경변수에 등록할 값 (확정):")
        print(f"  WORKS_DRIVE_SHAREDRIVE_ID    = {sid}")
        print(f"  WORKS_DRIVE_ROOT_FOLDER_ID   = {sid}")
        print("=========================================")
        if os.environ.get("RUN_FULL_TEST") == "1":
            os.environ["WORKS_DRIVE_SHAREDRIVE_ID"] = sid
            os.environ["WORKS_DRIVE_ROOT_FOLDER_ID"] = sid
            get_settings.cache_clear()
            s2 = get_settings()
            print(f"\n[4] ensure_project_folder 호출 (POST + PUT + list)")
            try:
                fid, url = await sso_drive.ensure_project_folder(
                    s2, code="POC-29B", project_name="테스트프로젝트B"
                )
                print(f"  [OK] folderId={fid}")
                print(f"  [OK] webUrl={url}")
            except sso_drive.DriveError as e:
                print(f"  [FAIL] {e}")
            return

        if os.environ.get("RUN_DIAGNOSTIC") == "1":
            os.environ["WORKS_DRIVE_SHAREDRIVE_ID"] = sid
            os.environ["WORKS_DRIVE_ROOT_FOLDER_ID"] = sid
            get_settings.cache_clear()
            s2 = get_settings()
            print(f"\n[4] settings 확인: sd={s2.works_drive_sharedrive_id} root={s2.works_drive_root_folder_id}")

            test_folder = "[POC-29A]테스트프로젝트A"
            print(f"\n[4-1] 직접 POST /sharedrives/{sid}/files")
            async with httpx.AsyncClient(timeout=15.0) as c:
                pr = await c.post(
                    f"{s2.works_api_base}/sharedrives/{sid}/files",
                    json={
                        "fileName": test_folder,
                        "fileSize": 0,
                        "fileType": "folder",
                    },
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                )
            print(f"    status: {pr.status_code}")
            print(f"    body: {pr.text[:400]}")

            print(f"\n[4-2] 직접 GET /sharedrives/{sid}/files (1초 대기 후)")
            await asyncio.sleep(1.0)
            async with httpx.AsyncClient(timeout=15.0) as c:
                lr = await c.get(
                    f"{s2.works_api_base}/sharedrives/{sid}/files",
                    headers={"Authorization": f"Bearer {token}"},
                )
            print(f"    status: {lr.status_code}")
            try:
                lb = lr.json()
                items = lb.get("files") or lb.get("items") or lb.get("list") or []
                names = [it.get("fileName") or it.get("name") or "?" for it in items]
                print(f"    root에 보이는 폴더 ({len(items)}개): {names}")
                match = next(
                    (it for it in items if (it.get("fileName") or it.get("name")) == test_folder),
                    None,
                )
                if match:
                    print(f"\n    *** [POC-29A]테스트프로젝트A 발견! ***")
                    print(json.dumps(match, ensure_ascii=False, indent=2))
                else:
                    print(f"    [경고] '{test_folder}' 미발견. 위 list에서 일치 키워드 확인 필요.")
            except ValueError:
                print(f"    text: {lr.text[:300]}")
            return

        if os.environ.get("RUN_PROJECT_TEST") == "1":
            print(f"\n[4] '{sid}' root에 폴더 생성 - 여러 body schema 시도...")
            test_name = "POC테스트폴더"
            create_url = f"{s.works_api_base}/sharedrives/{sid}/files"
            body_candidates: list[tuple[str, dict]] = [
                # (label, body)
                ("v1: fileName+parentFolderId+fileType", {
                    "fileName": test_name,
                    "parentFolderId": sid,
                    "fileType": "folder",
                }),
                ("v2: fileName+fileType only", {
                    "fileName": test_name,
                    "fileType": "folder",
                }),
                ("v3: name+type", {
                    "name": test_name,
                    "type": "folder",
                }),
                ("v4: fileName only", {
                    "fileName": test_name,
                }),
                ("v5: name only", {
                    "name": test_name,
                }),
                ("v6: folderName only", {
                    "folderName": test_name,
                }),
                # fileSize=0 + 다양한 조합 (응답에서 fileSize 필수 단서)
                ("v7: fileName+fileSize=0+fileType=folder", {
                    "fileName": test_name,
                    "fileSize": 0,
                    "fileType": "folder",
                }),
                ("v8: fileName+fileSize=0", {
                    "fileName": test_name,
                    "fileSize": 0,
                }),
                ("v9: fileName+fileSize=0+parentFolderId", {
                    "fileName": test_name,
                    "fileSize": 0,
                    "parentFolderId": sid,
                }),
                ("v10: fileName+fileSize=0+isFolder", {
                    "fileName": test_name,
                    "fileSize": 0,
                    "isFolder": True,
                }),
            ]
            for label, body in body_candidates:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    try:
                        resp = await client.post(
                            create_url,
                            json=body,
                            headers={
                                "Authorization": f"Bearer {token}",
                                "Content-Type": "application/json",
                            },
                        )
                    except httpx.HTTPError as e:
                        print(f"  [{label}] network error: {e}")
                        continue
                ok = "[OK]" if 200 <= resp.status_code < 300 else "[FAIL]"
                print(f"  {ok} {label} -> {resp.status_code}")
                snippet = resp.text[:300]
                print(f"        body: {snippet}")
                if 200 <= resp.status_code < 300:
                    print("\n  *** 1단계 성공 (uploadUrl 발급) ***")
                    print(f"  POST {create_url}")
                    print(f"  body: {json.dumps(body, ensure_ascii=False)}")
                    try:
                        rb = resp.json()
                    except ValueError:
                        rb = {"_text": resp.text}
                    upload_url = rb.get("uploadUrl") if isinstance(rb, dict) else ""
                    print(f"  응답 키: {list(rb.keys()) if isinstance(rb, dict) else type(rb)}")
                    if upload_url:
                        # 2-A단계: PUT with Authorization header
                        print(f"\n  [2-A] PUT 빈 body + Bearer 헤더...")
                        async with httpx.AsyncClient(timeout=15.0) as c2:
                            try:
                                put_resp = await c2.put(
                                    upload_url,
                                    content=b"",
                                    headers={
                                        "Content-Length": "0",
                                        "Authorization": f"Bearer {token}",
                                    },
                                )
                            except httpx.HTTPError as e:
                                print(f"    network: {e}")
                                put_resp = None
                        if put_resp is not None:
                            print(f"    status: {put_resp.status_code}")
                            print(f"    body: {put_resp.text[:400]}")

                        # 2-B단계: list 조회로 폴더가 만들어졌는지 확인
                        print(f"\n  [2-B] list 조회로 폴더 확인...")
                        list_url = f"{s.works_api_base}/sharedrives/{sid}/files"
                        async with httpx.AsyncClient(timeout=15.0) as c3:
                            list_resp = await c3.get(
                                list_url,
                                headers={"Authorization": f"Bearer {token}"},
                            )
                        if 200 <= list_resp.status_code < 300:
                            lb = list_resp.json()
                            items = (
                                lb.get("files")
                                or lb.get("items")
                                or lb.get("list")
                                or []
                            )
                            print(f"    root에 {len(items)}개 항목 보임:")
                            for it in items[:10]:
                                print(
                                    f"      - {it.get('fileName') or it.get('name')} "
                                    f"(id={it.get('fileId') or it.get('id') or '?'}, "
                                    f"type={it.get('fileType') or it.get('type') or '?'})"
                                )
                            # POC테스트폴더 매칭
                            match = next(
                                (
                                    it
                                    for it in items
                                    if (it.get("fileName") or it.get("name")) == test_name
                                ),
                                None,
                            )
                            if match:
                                print(f"\n    *** POC테스트폴더 발견! 메타: ***")
                                print(json.dumps(match, ensure_ascii=False, indent=2))
                    return

            # /files endpoint가 모두 fail이면 별도 /folders endpoint 시도
            print(f"\n[5] 별도 /folders endpoint 시도...")
            folder_endpoints = [
                f"{s.works_api_base}/sharedrives/{sid}/folders",
                f"{s.works_api_base}/sharedrives/{sid}/folder",
                f"{s.works_api_base}/sharedrives/{sid}/files/folder",
            ]
            folder_bodies = [
                {"fileName": test_name},
                {"fileName": test_name, "parentFolderId": sid},
                {"name": test_name},
            ]
            for fep in folder_endpoints:
                for fbody in folder_bodies:
                    async with httpx.AsyncClient(timeout=15.0) as client:
                        try:
                            resp = await client.post(
                                fep,
                                json=fbody,
                                headers={
                                    "Authorization": f"Bearer {token}",
                                    "Content-Type": "application/json",
                                },
                            )
                        except httpx.HTTPError as e:
                            print(f"  [{fep}] {fbody} network: {e}")
                            continue
                    ok = "[OK]" if 200 <= resp.status_code < 300 else "[FAIL]"
                    print(
                        f"  {ok} POST {fep} body={list(fbody.keys())} "
                        f"-> {resp.status_code} : {resp.text[:200]}"
                    )
                    if 200 <= resp.status_code < 300:
                        print("\n  *** 성공! ***")
                        print(f"  POST {fep}")
                        print(f"  body: {json.dumps(fbody, ensure_ascii=False)}")
                        return
        return

    # case 2: 다른 sharedrive 안에 sub-folder로 존재할 가능성
    print(
        f"\n[3b] 각 sharedrive의 root에서 sub-folder '{target_name}' 검색..."
    )
    found_in: list[tuple[str, dict]] = []  # (sharedriveId, folder_meta)
    for sd_meta in sharedrives:
        sid = sd_meta.get("sharedriveId", "")
        if not sid:
            continue
        # GET /sharedrives/{id}/files
        code, files_body = await _try_get(
            token, f"{s.works_api_base}/sharedrives/{sid}/files"
        )
        ok = "[OK]" if 200 <= (code if isinstance(code, int) else 0) < 300 else "[FAIL]"
        print(f"  {ok} {sid} -> {code}")
        if not (isinstance(code, int) and 200 <= code < 300):
            continue
        items = []
        if isinstance(files_body, dict):
            for key in ("files", "items", "children", "folders", "list"):
                v = files_body.get(key)
                if isinstance(v, list):
                    items = v
                    break
        for it in items:
            n = it.get("fileName") or it.get("name") or it.get("folderName") or ""
            if n == target_name:
                found_in.append((sid, it))
                print(f"        --> '{target_name}' 발견!")
                break
        if not any(s == sid for s, _ in found_in):
            names = [
                it.get("fileName") or it.get("name") or "?" for it in items[:5]
            ]
            print(f"        root에 보이는 항목 일부: {names}")

    if not found_in:
        print(
            f"\n  [경고] 어느 sharedrive에서도 '{target_name}' 미발견. 권한 또는 위치 문제."
        )
        return

    sid, folder_meta = found_in[0]
    print(f"\n[3c] '{target_name}' 폴더 메타 (sharedrive {sid}):")
    print(_pretty(folder_meta, max_chars=2000))

    folder_id = ""
    for ik in ("fileId", "id", "folderId"):
        v = folder_meta.get(ik)
        if isinstance(v, str) and v:
            folder_id = v
            break
    folder_url = ""
    for uk in ("webUrl", "url", "shareUrl", "fileUrl"):
        v = folder_meta.get(uk)
        if isinstance(v, str) and v:
            folder_url = v
            break

    print("\n=========================================")
    print("Render 환경변수에 등록할 값 (확정):")
    print(f"  WORKS_DRIVE_SHAREDRIVE_ID    = {sid}")
    print(f"  WORKS_DRIVE_ROOT_FOLDER_ID   = {folder_id or '(추출 실패)'}")
    if folder_url:
        print(f"  (참고) 폴더 webUrl           = {folder_url}")
    print("=========================================")

    if os.environ.get("RUN_PROJECT_TEST") == "1" and folder_id:
        os.environ["WORKS_DRIVE_SHAREDRIVE_ID"] = sid
        os.environ["WORKS_DRIVE_ROOT_FOLDER_ID"] = folder_id
        get_settings.cache_clear()
        s2 = get_settings()
        print("\n[4] [POC-2604]테스트프로젝트 폴더 생성 시도...")
        try:
            fid, url = await sso_drive.ensure_project_folder(
                s2, code="POC-2604", project_name="테스트프로젝트"
            )
            print(f"  [OK] folderId={fid}")
            print(f"  [OK] webUrl={url or '(URL 키 누락)'}")
        except sso_drive.DriveError as e:
            print(f"  [FAIL] {e}")
    return

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
