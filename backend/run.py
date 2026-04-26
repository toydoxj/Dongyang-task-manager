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

    # 3. .env 로드 (이미 환경변수가 있으면 override 안 함)
    from dotenv import load_dotenv

    for candidate in (
        os.environ.get("BACKEND_DATA_DIR"),
        exe_dir,
        os.path.dirname(exe_dir),
    ):
        if candidate:
            env_path = os.path.join(candidate, ".env")
            if os.path.isfile(env_path):
                load_dotenv(env_path, override=False)
                break
    load_dotenv(override=False)  # 기본 탐색

    # 4. DATABASE_URL 기본값 (사용자별 데이터 디렉토리)
    if not os.environ.get("DATABASE_URL"):
        data_dir = os.environ.get("BACKEND_DATA_DIR") or os.path.join(exe_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        # SQLite URL 은 forward slash 권장
        db_path = os.path.join(data_dir, "app.db").replace("\\", "/")
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"

    # 5. 정적 frontend 위치 (백엔드가 서빙)
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
