"""FastAPI 애플리케이션 진입점."""
from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.db import init_db
from app.exceptions import AppError
from app.routers import admin_bot as admin_bot_router
from app.routers import admin_calendar as admin_calendar_router
from app.routers import admin_drive as admin_drive_router
from app.routers import auth as auth_router
from app.routers import cashflow as cashflow_router
from app.routers import clients as clients_router
from app.routers import contract_items as contract_items_router
from app.routers import employees as employees_router
from app.routers import master_projects as master_projects_router
from app.routers import projects as projects_router
from app.routers import sales as sales_router
from app.routers import seal_requests as seal_requests_router
from app.routers import suggestions as suggestions_router
from app.routers import tasks as tasks_router
from app.services.notion import get_notion
from app.services.notion_schema import ensure_all_schemas
from app.services.scheduler import shutdown_scheduler, start_scheduler
from app.services.sync import ALL_KINDS, get_sync
from app.settings import get_settings

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    from app.settings import validate_runtime_settings

    # JWT_SECRET 등 위험한 default 차단 — 누락 시 즉시 startup fail
    validate_runtime_settings()

    startup_task: asyncio.Task[None] | None = None
    # 운영은 alembic이 schema 처리. dev/test에서만 init_db() 자동 실행.
    if settings.auto_create_tables:
        init_db()
    # 노션 schema 자동 보강은 백그라운드로 실행해 헬스체크 지연을 피한다.
    async def _ensure_schemas_background() -> None:
        try:
            await ensure_all_schemas(get_notion(), settings)
        except Exception:  # noqa: BLE001
            logging.getLogger("startup").exception("노션 schema 보강 중 예외 (무시)")

    startup_task = asyncio.create_task(_ensure_schemas_background())
    start_scheduler()
    try:
        yield
    finally:
        if startup_task is not None and not startup_task.done():
            startup_task.cancel()
        shutdown_scheduler()


app = FastAPI(
    title="(주)동양구조 업무관리 API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    # localStorage + Authorization 헤더 사용 → cookie 기반 credential 불필요
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppError)
async def app_error_handler(req: Request, exc: AppError) -> JSONResponse:
    # 5xx로 변환되는 AppError(특히 NotionApiError 502)는 frontend에서 502로만 보여
    # 운영 trace가 어렵다. 본문을 logger.warning으로 한 줄 남겨 Render Logs에서
    # search 가능하게 한다. 4xx는 운영 사용자 에러라 noise만 늘어나서 제외.
    if exc.status_code >= 500:
        logging.getLogger("app.error").warning(
            "%s on %s %s — %s",
            exc.error_code,
            req.method,
            req.url.path,
            exc.message,
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={"error_code": exc.error_code, "message": exc.message},
    )


app.include_router(auth_router.router, prefix="/api")
app.include_router(projects_router.router, prefix="/api")
app.include_router(tasks_router.router, prefix="/api")
app.include_router(cashflow_router.router, prefix="/api")
app.include_router(clients_router.router, prefix="/api")
app.include_router(contract_items_router.router, prefix="/api")
app.include_router(sales_router.router, prefix="/api")
app.include_router(master_projects_router.router, prefix="/api")
app.include_router(employees_router.router, prefix="/api")
app.include_router(suggestions_router.router, prefix="/api")
app.include_router(seal_requests_router.router, prefix="/api")
app.include_router(admin_drive_router.router, prefix="/api")
app.include_router(admin_calendar_router.router, prefix="/api")
app.include_router(admin_bot_router.router, prefix="/api")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


def _verify_cron(authorization: str | None = Header(default=None)) -> None:
    secret = settings.cron_secret
    if not secret:
        raise HTTPException(status_code=503, detail="CRON_SECRET 미설정")
    expected = f"Bearer {secret}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="invalid cron token")


# 진행 중 manual sync. 중복 호출(사용자가 응답 빠르다고 여러 번 누름)이
# 여러 sync_all을 동시 spawn해 worker를 더 부하 주는 일을 방지.
# "_all"은 sync_all 트리거, 그 외는 kind별.
#
# 주의: 이 set은 process-local. uvicorn workers > 1 환경에선 worker별로
# 독립이므로 worker 간 동시 manual sync 가 둘 다 통과할 수 있음. 그러나:
#  - 정기 sync는 별도 cron container(HTTP 미경유) 라 race 없음
#  - manual sync 는 admin이 가끔 누르는 상황이라 빈도 낮음
#  - 동작은 idempotent (notion upsert + 노션 rate limit이 자연 직렬화)
# 정밀 cluster-wide dedup이 필요해지면 PgBouncer 호환 row-mutex 또는
# direct DB connection의 advisory lock 으로 별도 작업.
_running_sync: set[str] = set()

# asyncio.create_task의 결과를 강한 참조로 보관. event loop은 weak ref만
# 잡으므로 reference 없으면 mid-execution에서 GC되어 sync 끊김.
# (공식 asyncio.create_task 문서의 경고)
_bg_tasks: set[asyncio.Task[None]] = set()


async def _run_sync_in_bg(*, kind: str | None, full: bool) -> None:
    """fire-and-forget으로 sync 실행. 결과는 Render Logs에서 확인."""
    key = kind or "_all"
    cron_logger = logging.getLogger("dy.cron")
    try:
        sync = get_sync()
        if kind:
            n = await sync.sync_kind(kind, full=full)  # type: ignore[arg-type]
            cron_logger.info(
                "manual cron %s full=%s done: %d", kind, full, n
            )
        else:
            result = await sync.sync_all(full=full)
            cron_logger.info(
                "manual cron sync_all full=%s done: %s", full, result
            )
    except Exception:  # noqa: BLE001
        cron_logger.exception("manual cron sync 실패")
    finally:
        _running_sync.discard(key)


def _spawn_bg_sync(*, kind: str | None, full: bool) -> None:
    """create_task + 강한 참조 유지. done 시 set에서 자동 제거."""
    task = asyncio.create_task(_run_sync_in_bg(kind=kind, full=full))
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)


@app.post("/api/cron/sync", status_code=202)
async def cron_sync(
    full: bool = False,
    _ok: None = Depends(_verify_cron),
) -> dict[str, str]:
    """수동 트리거 (외부 cron은 더 이상 이 endpoint를 호출하지 않고
    `python -m app.scripts.sync_once --kind <kind>`를 별도 cron container에서 실행).

    무거운 sync가 worker를 막아 다른 요청이 502 되는 문제를 방지하기 위해
    fire-and-forget으로 실행. 즉시 202 반환, 결과는 Render Logs에서 확인.
    이미 실행 중이면 중복 spawn 금지(already_running) — process-local guard.

    full sync는 KST 7~22시(업무시간)에는 차단 — 새벽에만 허용.
    """
    if full:
        from datetime import datetime, timedelta, timezone

        kst = datetime.now(timezone(timedelta(hours=9)))
        if 7 <= kst.hour <= 22:
            raise HTTPException(
                status_code=409,
                detail=(
                    "full sync는 KST 7~22시(업무시간)에 실행할 수 없습니다. "
                    "새벽에 다시 시도하세요."
                ),
            )
    if _running_sync:
        return {"status": "already_running", "active": ",".join(sorted(_running_sync))}
    _running_sync.add("_all")
    _spawn_bg_sync(kind=None, full=full)
    return {"status": "started", "full": str(full).lower()}


@app.post("/api/cron/sync/{kind}", status_code=202)
async def cron_sync_one(
    kind: str,
    full: bool = False,
    _ok: None = Depends(_verify_cron),
) -> dict[str, str]:
    if kind not in ALL_KINDS:
        raise HTTPException(status_code=400, detail=f"unknown kind: {kind}")
    # sync_all이 돌고 있으면 그 안에 이 kind도 포함되니 추가 spawn 금지.
    # 동일 kind가 이미 진행 중일 때도 마찬가지.
    if "_all" in _running_sync or kind in _running_sync:
        return {"status": "already_running", "kind": kind}
    _running_sync.add(kind)
    _spawn_bg_sync(kind=kind, full=full)
    return {"status": "started", "kind": kind, "full": str(full).lower()}


# task 시작일 도래 자동 진행 — 매일 아침 cron으로 호출
_running_auto_progress = False


async def _run_auto_progress_in_bg() -> None:
    global _running_auto_progress
    cron_logger = logging.getLogger("dy.cron")
    try:
        from app.services.notion import get_notion
        from app.services.task_auto_progress import auto_progress_tasks

        result = await auto_progress_tasks(get_notion())
        cron_logger.info("auto-progress done: %s", result)
    except Exception:  # noqa: BLE001
        cron_logger.exception("auto-progress 실패")
    finally:
        _running_auto_progress = False


@app.post("/api/cron/auto-progress", status_code=202)
async def cron_auto_progress(
    _ok: None = Depends(_verify_cron),
) -> dict[str, str]:
    """task 시작일 도래 시 '진행 중' + 프로젝트 진행단계 '진행중' 자동 처리.

    매일 아침 외부 cron이 호출. fire-and-forget 202. process-local 중복 차단.
    """
    global _running_auto_progress
    if _running_auto_progress:
        return {"status": "already_running"}
    _running_auto_progress = True
    task = asyncio.create_task(_run_auto_progress_in_bg())
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)
    return {"status": "started"}


# 정적 frontend 서빙 (FRONTEND_DIST 환경변수가 설정되었을 때만)
# — 반드시 라우터 등록 뒤에 와야 /api/* 가 가려지지 않는다.
_frontend_dist = os.environ.get("FRONTEND_DIST", "")
if _frontend_dist and os.path.isdir(_frontend_dist):
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="frontend")
