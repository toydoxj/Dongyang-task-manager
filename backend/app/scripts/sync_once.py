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
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
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

    # 늦은 import — 인자 파싱 실패 시 backend 모듈 로딩 비용 회피
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
