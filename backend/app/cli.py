"""CLI 부트스트랩 — 노션 → 미러 풀 sync.

사용:
    python -m app.cli sync-all          # 모든 kind 풀 sync
    python -m app.cli sync projects     # 특정 kind만
    python -m app.cli sync-master-blocks <page_id>  # 마스터 페이지 본문 블록
"""
from __future__ import annotations

import asyncio
import logging
import sys

from app.services.sync import ALL_KINDS, get_sync

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


async def _sync_all() -> None:
    sync = get_sync()
    result = await sync.sync_all(full=True)
    print("== sync 결과 ==")
    for k, n in result.items():
        print(f"  {k:10s}: {n}")


async def _sync_one(kind: str) -> None:
    if kind not in ALL_KINDS:
        print(f"unknown kind: {kind}. 가능: {', '.join(ALL_KINDS)}")
        sys.exit(2)
    sync = get_sync()
    n = await sync.sync_kind(kind, full=True)  # type: ignore[arg-type]
    print(f"{kind}: {n} 페이지")


async def _sync_master_blocks(page_id: str) -> None:
    sync = get_sync()
    n = await sync.sync_master_blocks(page_id)
    print(f"master blocks ({page_id}): {n} 블록")


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(0)
    cmd = args[0]
    if cmd == "sync-all":
        asyncio.run(_sync_all())
    elif cmd == "sync" and len(args) >= 2:
        asyncio.run(_sync_one(args[1]))
    elif cmd == "sync-master-blocks" and len(args) >= 2:
        asyncio.run(_sync_master_blocks(args[1]))
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
