"""NAVER WORKS Drive PoC — Service Account JWT + 공유 드라이브 폴더 생성 스모크 테스트.

사용법 (backend/.venv 활성 후, 프로젝트 루트에서):
    backend/.venv/Scripts/python.exe scripts/works_drive_poc.py

필수 환경변수 (backend/.env 또는 export):
    WORKS_CLIENT_ID
    WORKS_CLIENT_SECRET
    WORKS_SERVICE_ACCOUNT_ID
    WORKS_PRIVATE_KEY              (PEM. 줄바꿈은 실제 LF 또는 \\n)
    WORKS_DRIVE_SHAREDRIVE_ID
    WORKS_DRIVE_ROOT_FOLDER_ID     ([업무관리] 폴더의 fileId)

검증 단계:
    [1] access_token 발급
    [2] sharedrive 목록 조회
    [3] 테스트 프로젝트 폴더 생성: [POC-2604]테스트프로젝트
    [4] 7개 sub 폴더 생성
    [5] 동일 이름 다시 호출 — idempotent 확인
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

# backend/ 모듈 import 경로
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

# .env 로드 (dotenv 없으면 무시)
try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / "backend" / ".env")
except ImportError:
    pass

# settings를 강제로 활성화 (PoC는 무조건 enabled)
os.environ["WORKS_DRIVE_ENABLED"] = "true"

from app.services import sso_drive  # noqa: E402
from app.settings import get_settings  # noqa: E402


async def main() -> None:
    get_settings.cache_clear()
    s = get_settings()
    print(f"[준비] client_id={s.works_client_id[:6]}*** sa={s.works_service_account_id[:6]}***")
    print(f"[준비] sharedrive={s.works_drive_sharedrive_id} root={s.works_drive_root_folder_id}")

    print("\n[1] access_token 발급 시도...")
    try:
        token, exp = await sso_drive._request_access_token(s)
        print(f"  ✓ access_token 발급 OK (expires_in={exp}, len={len(token)})")
    except sso_drive.DriveError as e:
        print(f"  ✗ 실패: {e}")
        return

    print("\n[2] sharedrive 목록 조회...")
    try:
        body = await sso_drive.list_sharedrives(s)
        print(f"  응답: {json.dumps(body, ensure_ascii=False, indent=2)[:500]}")
    except sso_drive.DriveError as e:
        print(f"  ✗ 실패: {e}")
        # 계속 진행 — 실제 폴더 생성 시도

    code = os.environ.get("POC_CODE", "POC-2604")
    name = os.environ.get("POC_NAME", "테스트프로젝트")
    print(f"\n[3] 프로젝트 폴더 생성 시도: [{code}]{name}")
    try:
        fid, url = await sso_drive.ensure_project_folder(
            s, code=code, project_name=name
        )
        print(f"  ✓ folderId={fid}")
        print(f"  ✓ webUrl={url or '(응답에 URL 키 없음 — 응답 schema 추가 점검 필요)'}")
    except sso_drive.DriveError as e:
        print(f"  ✗ 실패: {e}")
        return

    print("\n[4] 동일 이름 재호출 (idempotent 확인)...")
    try:
        fid2, url2 = await sso_drive.ensure_project_folder(
            s, code=code, project_name=name
        )
        if fid == fid2:
            print(f"  ✓ 같은 folderId 재사용 확인 ({fid2})")
        else:
            print(f"  ⚠ 다른 ID 반환 ({fid} vs {fid2}) — idempotent 깨짐")
    except sso_drive.DriveError as e:
        print(f"  ✗ 실패: {e}")

    print("\n[완료] PoC 정상 종료. 위 응답을 보고 sso_drive.py의 endpoint/응답 키를 정착시키세요.")


if __name__ == "__main__":
    asyncio.run(main())
