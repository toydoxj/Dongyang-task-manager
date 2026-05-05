"""kind별 또는 전체 incremental sync — Render cron container에서 standalone 실행.

web service worker 안에서 sync를 돌리지 않고 별도 cron 프로세스에서 실행해
사용자 API 응답이 sync 부담에 영향받지 않도록 분리한 진입점.

호출 예:
  python -m app.scripts.sync_once --kind projects
  python -m app.scripts.sync_once --kind master --full
  python -m app.scripts.sync_once                         # sync_all
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)


_KIND_ENV = {
    "projects": "NOTION_DB_PROJECTS",
    "tasks": "NOTION_DB_TASKS",
    "clients": "NOTION_DB_CLIENTS",
    "master": "NOTION_DB_MASTER",
    "cashflow": "NOTION_DB_CASHFLOW",
    "expense": "NOTION_DB_EXPENSE",
    "contract_items": "NOTION_DB_CONTRACT_ITEMS",
    "sales": "NOTION_DB_SALES",
}


def _bootstrap_env_from_settings() -> None:
    """pydantic-settings가 .env에서 로드한 값을 os.environ에 inject.

    sync_once.py는 OS env로 검증하지만, 로컬 dev에서 .env로만 값을 둔 경우
    OS env에는 값이 없다. pydantic-settings는 .env 자동 로드하므로 settings
    값을 한 번 OS env에 펌프해서 두 경로를 일치시킨다 (이미 OS env에 값 있으면 보존).
    """
    from app.settings import get_settings

    s = get_settings()
    pairs = [
        ("DATABASE_URL", s.database_url),
        ("NOTION_API_KEY", s.notion_api_key),
        ("NOTION_DB_PROJECTS", s.notion_db_projects),
        ("NOTION_DB_TASKS", s.notion_db_tasks),
        ("NOTION_DB_CLIENTS", s.notion_db_clients),
        ("NOTION_DB_MASTER", s.notion_db_master),
        ("NOTION_DB_CASHFLOW", s.notion_db_cashflow),
        ("NOTION_DB_EXPENSE", s.notion_db_expense),
        ("NOTION_DB_CONTRACT_ITEMS", s.notion_db_contract_items),
        ("NOTION_DB_SALES", s.notion_db_sales),
    ]
    for env_key, val in pairs:
        if val and not os.environ.get(env_key):
            os.environ[env_key] = val


def assert_required_env(kind: str) -> None:
    """cron 실행 전 필수 env 검증. 누락 시 0건 사일런트 성공 차단."""
    _bootstrap_env_from_settings()
    common = ["DATABASE_URL", "NOTION_API_KEY"]
    if kind:
        required = common + [_KIND_ENV[kind]]
    else:
        # full sync_all — 모든 kind의 DB ID 필요
        required = common + list(_KIND_ENV.values())
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        raise RuntimeError(
            f"필수 환경변수 누락: {', '.join(missing)}. "
            "Render cron service의 Environment 탭에서 backend web service와 "
            "동일한 값을 입력하세요."
        )


async def main() -> int:
    parser = argparse.ArgumentParser(description="Notion → mirror DB sync")
    parser.add_argument(
        "--kind",
        default="",
        help="projects/tasks/clients/master/cashflow/expense. 비우면 sync_all",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="full reconcile (archive 처리 포함). 미지정 시 incremental",
    )
    args = parser.parse_args()

    # env 누락 시 즉시 fail — sync_kind가 0건 성공으로 끝나는 사일런트 실패 차단
    if args.kind and args.kind not in _KIND_ENV:
        print(
            f"unknown kind: {args.kind}. allowed: {sorted(_KIND_ENV.keys())}",
            file=sys.stderr,
        )
        return 2
    assert_required_env(args.kind)

    # 늦은 import — env 검증 실패 시 backend 모듈 로딩 비용 회피
    from app.services.sync import ALL_KINDS, get_sync

    sync = get_sync()
    if args.kind:
        if args.kind not in ALL_KINDS:
            print(
                f"unknown kind: {args.kind}. allowed: {ALL_KINDS}",
                file=sys.stderr,
            )
            return 2
        n = await sync.sync_kind(args.kind, full=args.full)  # type: ignore[arg-type]
        print(f"sync {args.kind} full={args.full} done: {n}")
    else:
        result = await sync.sync_all(full=args.full)
        print(f"sync_all full={args.full} done: {result}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
