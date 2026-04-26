"""FastAPI 애플리케이션 진입점."""
from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.db import init_db
from app.exceptions import AppError
from app.routers import auth as auth_router
from app.routers import cashflow as cashflow_router
from app.routers import clients as clients_router
from app.routers import employees as employees_router
from app.routers import master_projects as master_projects_router
from app.routers import projects as projects_router
from app.routers import tasks as tasks_router
from app.services.scheduler import shutdown_scheduler, start_scheduler
from app.services.sync import ALL_KINDS, get_sync
from app.settings import get_settings

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    init_db()
    start_scheduler()
    try:
        yield
    finally:
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
async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error_code": exc.error_code, "message": exc.message},
    )


app.include_router(auth_router.router, prefix="/api")
app.include_router(projects_router.router, prefix="/api")
app.include_router(tasks_router.router, prefix="/api")
app.include_router(cashflow_router.router, prefix="/api")
app.include_router(clients_router.router, prefix="/api")
app.include_router(master_projects_router.router, prefix="/api")
app.include_router(employees_router.router, prefix="/api")


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


@app.post("/api/cron/sync")
async def cron_sync(
    full: bool = False,
    _ok: None = Depends(_verify_cron),
) -> dict[str, int]:
    """수동/외부 cron 트리거. Header: Authorization: Bearer $CRON_SECRET."""
    return await get_sync().sync_all(full=full)


@app.post("/api/cron/sync/{kind}")
async def cron_sync_one(
    kind: str,
    full: bool = False,
    _ok: None = Depends(_verify_cron),
) -> dict[str, int]:
    if kind not in ALL_KINDS:
        raise HTTPException(status_code=400, detail=f"unknown kind: {kind}")
    n = await get_sync().sync_kind(kind, full=full)  # type: ignore[arg-type]
    return {kind: n}


# 정적 frontend 서빙 (FRONTEND_DIST 환경변수가 설정되었을 때만)
# — 반드시 라우터 등록 뒤에 와야 /api/* 가 가려지지 않는다.
_frontend_dist = os.environ.get("FRONTEND_DIST", "")
if _frontend_dist and os.path.isdir(_frontend_dist):
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="frontend")
