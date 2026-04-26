"""노션 API 통합 서비스 — 단일 클라이언트, Rate limit, 인메모리 TTL 캐시."""
from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from functools import lru_cache
from typing import Any

from notion_client import Client
from notion_client.errors import APIResponseError

from app.exceptions import NotFoundError, NotionApiError
from app.settings import get_settings

# 노션 공식 한도: 평균 3 req/s. 보수적으로 ~2.5 req/s.
_MIN_INTERVAL_S = 0.4
_CACHE_TTL_S = 30.0


class RateLimiter:
    """전역 호출 간격 보장."""

    def __init__(self, min_interval_s: float) -> None:
        self._min = min_interval_s
        self._last = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            delay = self._last + self._min - now
            if delay > 0:
                await asyncio.sleep(delay)
            self._last = time.monotonic()


class TTLCache:
    """단순 인메모리 TTL 캐시 (단일 프로세스 가정)."""

    def __init__(self, ttl_s: float) -> None:
        self._ttl = ttl_s
        self._store: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        ts, value = entry
        if time.monotonic() - ts >= self._ttl:
            self._store.pop(key, None)
            return None
        return value

    def put(self, key: str, value: Any) -> None:
        self._store[key] = (time.monotonic(), value)

    def invalidate(self, prefix: str = "") -> None:
        if not prefix:
            self._store.clear()
            return
        for k in list(self._store):
            if k.startswith(prefix):
                del self._store[k]


class NotionService:
    """노션 API 호출의 유일한 진입점."""

    def __init__(self, api_key: str) -> None:
        self._client = Client(auth=api_key)
        self._limiter = RateLimiter(_MIN_INTERVAL_S)
        self._cache = TTLCache(_CACHE_TTL_S)

    # ── 내부 호출 헬퍼 ──

    async def _call(
        self,
        fn: Callable[[], Any],
        *,
        cache_key: str | None = None,
    ) -> Any:
        if cache_key is not None:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached
        await self._limiter.wait()
        try:
            result = await asyncio.to_thread(fn)
        except APIResponseError as exc:
            if exc.status == 404:
                raise NotFoundError(f"노션 리소스를 찾을 수 없습니다: {exc}") from exc
            raise NotionApiError(f"노션 API 호출 실패: {exc}") from exc
        if cache_key is not None:
            self._cache.put(cache_key, result)
        return result

    # ── 데이터베이스 / 데이터 소스 ──
    #
    # 노션 2025+ 멀티-소스 데이터베이스 지원:
    #   databases.retrieve  →  메타데이터 + data_sources 목록만
    #   data_sources.retrieve →  실제 properties
    #   data_sources.query   →  쿼리
    #
    # 사용자 코드는 db_id 만 알면 되고, data_source_id 변환은 내부 처리.

    async def get_database(self, db_id: str) -> dict[str, Any]:
        """원시 database 객체 (data_sources 목록 포함, properties는 없음)."""
        return await self._call(
            lambda: self._client.databases.retrieve(database_id=db_id),
            cache_key=f"db:{db_id}",
        )

    async def _resolve_data_source_id(self, db_id: str) -> str:
        """db_id 를 첫 번째 data_source_id 로 변환 (단일 소스 가정)."""
        db = await self.get_database(db_id)
        sources = db.get("data_sources") or []
        if not sources:
            raise NotionApiError(f"DB {db_id} 에 data_source가 없습니다")
        return sources[0]["id"]

    async def get_data_source(self, db_id: str) -> dict[str, Any]:
        """db_id 입력 → properties 포함된 data source 객체 반환."""
        ds_id = await self._resolve_data_source_id(db_id)
        return await self._call(
            lambda: self._client.data_sources.retrieve(data_source_id=ds_id),
            cache_key=f"ds:{ds_id}",
        )

    async def query_database(
        self,
        db_id: str,
        *,
        filter: dict[str, Any] | None = None,
        sorts: list[dict[str, Any]] | None = None,
        page_size: int = 100,
        start_cursor: str | None = None,
    ) -> dict[str, Any]:
        ds_id = await self._resolve_data_source_id(db_id)
        opts: dict[str, Any] = {"data_source_id": ds_id, "page_size": page_size}
        if filter is not None:
            opts["filter"] = filter
        if sorts is not None:
            opts["sorts"] = sorts
        if start_cursor is not None:
            opts["start_cursor"] = start_cursor
        cache_key = f"query:{ds_id}:{json.dumps(opts, sort_keys=True, default=str)}"
        return await self._call(
            lambda: self._client.data_sources.query(**opts), cache_key=cache_key
        )

    async def query_all(
        self,
        db_id: str,
        *,
        filter: dict[str, Any] | None = None,
        sorts: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """페이지네이션 자동 처리, 모든 결과 누적."""
        results: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            page = await self.query_database(
                db_id, filter=filter, sorts=sorts, start_cursor=cursor
            )
            results.extend(page.get("results", []))
            if not page.get("has_more"):
                break
            cursor = page.get("next_cursor")
        return results

    # ── 페이지 ──

    async def get_page(self, page_id: str) -> dict[str, Any]:
        return await self._call(
            lambda: self._client.pages.retrieve(page_id=page_id),
            cache_key=f"page:{page_id}",
        )

    async def create_page(
        self, db_id: str, properties: dict[str, Any]
    ) -> dict[str, Any]:
        ds_id = await self._resolve_data_source_id(db_id)
        result = await self._call(
            lambda: self._client.pages.create(
                parent={"data_source_id": ds_id}, properties=properties
            ),
        )
        # 새 페이지 추가 → 해당 data source query 캐시 무효화
        self._cache.invalidate(f"query:{ds_id}")
        return result

    async def update_page(
        self, page_id: str, properties: dict[str, Any]
    ) -> dict[str, Any]:
        result = await self._call(
            lambda: self._client.pages.update(
                page_id=page_id, properties=properties
            ),
        )
        # 캐시 무효화: 해당 페이지 + 모든 query (어느 DB 소속인지 확실하지 않으므로 전체)
        self._cache.invalidate(f"page:{page_id}")
        self._cache.invalidate("query:")
        return result

    # ── 캐시 제어 (테스트/관리용) ──

    def clear_cache(self) -> None:
        self._cache.invalidate()

    # ── 발주처(협력업체) 매핑 ──

    async def fetch_title_dict(self, db_id: str) -> dict[str, str]:
        """relation lookup용: page_id → title 매핑."""
        cache_key = f"titlemap:{db_id}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        pages = await self.query_all(db_id)
        result: dict[str, str] = {}
        for p in pages:
            for prop in p.get("properties", {}).values():
                if prop.get("type") == "title":
                    arr = prop.get("title", [])
                    result[p.get("id", "")] = arr[0].get("plain_text", "") if arr else ""
                    break
        self._cache.put(cache_key, result)
        return result


@lru_cache(maxsize=1)
def get_notion() -> NotionService:
    """FastAPI Depends용 싱글턴 팩토리."""
    s = get_settings()
    if not s.notion_api_key:
        raise NotionApiError("NOTION_API_KEY가 설정되지 않았습니다 (.env 확인)")
    return NotionService(s.notion_api_key)
