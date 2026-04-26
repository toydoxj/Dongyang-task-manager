"""PyInstaller 진입점 — uvicorn 서버 기동.

PyInstaller 번들 (sys.frozen) vs 개발 모드를 구분해 경로/환경을 보정한다.
"""
from __future__ import annotations

import os
import sys


def _setup_runtime() -> None:
    # 1. UTF-8 강제 (Windows cp949 콘솔에서 한글 깨짐 방지)
    for stream in (sys.stdout, sys.stderr):
        if stream and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
            except (AttributeError, ValueError):
                pass

    # 2. 경로
    if getattr(sys, "frozen", False):
        base_dir: str = sys._MEIPASS  # type: ignore[attr-defined]
        exe_dir: str = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        exe_dir = base_dir

    # 3. .env 로드 — 우선순위:
    #    (1) BACKEND_DATA_DIR/.env (사용자 override)
    #    (2) exe_dir/.env (수동 배치)
    #    (3) base_dir/.env.production (빌드에 번들된 기본값)
    from dotenv import load_dotenv

    loaded_user_env = False
    for candidate in (
        os.environ.get("BACKEND_DATA_DIR"),
        exe_dir,
        os.path.dirname(exe_dir),
    ):
        if candidate:
            env_path = os.path.join(candidate, ".env")
            if os.path.isfile(env_path):
                load_dotenv(env_path, override=False)
                loaded_user_env = True
                break
    if not loaded_user_env:
        bundled = os.path.join(base_dir, ".env.production")
        if os.path.isfile(bundled):
            load_dotenv(bundled, override=False)
    load_dotenv(override=False)  # 시스템 환경변수 fallback

    # 4. 사용자 데이터 디렉토리 (DB + JWT secret 영구 저장)
    user_dir = os.environ.get("BACKEND_DATA_DIR")
    if not user_dir:
        if sys.platform == "win32":
            base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
            user_dir = os.path.join(base, "동양구조 업무관리")
        else:
            user_dir = os.path.join(os.path.expanduser("~"), ".dongyang-task-manager")
    os.makedirs(user_dir, exist_ok=True)

    # 5. DATABASE_URL 기본값
    if not os.environ.get("DATABASE_URL"):
        data_dir = os.path.join(user_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        db_path = os.path.join(data_dir, "app.db").replace("\\", "/")
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"

    # 6. JWT_SECRET — 기본값/미설정이면 user_dir에 영구 저장 후 재사용
    weak = ("", "change-me-in-production")
    if os.environ.get("JWT_SECRET", "") in weak:
        secret_file = os.path.join(user_dir, ".jwt-secret")
        if os.path.isfile(secret_file):
            with open(secret_file, encoding="utf-8") as f:
                token = f.read().strip()
            if token:
                os.environ["JWT_SECRET"] = token
        if os.environ.get("JWT_SECRET", "") in weak:
            import secrets as _secrets

            token = _secrets.token_urlsafe(64)
            with open(secret_file, "w", encoding="utf-8") as f:
                f.write(token)
            os.environ["JWT_SECRET"] = token

    # 7. 정적 frontend 위치 (백엔드가 서빙)
    if not os.environ.get("FRONTEND_DIST"):
        candidate = os.path.join(base_dir, "frontend_out")
        if os.path.isdir(candidate):
            os.environ["FRONTEND_DIST"] = candidate


def main() -> None:
    _setup_runtime()

    # 환경 설정 후에 import 해야 settings 캐시가 정상 동작
    import uvicorn

    from app.main import app

    host = os.environ.get("BACKEND_HOST", "127.0.0.1")
    port = int(os.environ.get("BACKEND_PORT", "8000"))
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
