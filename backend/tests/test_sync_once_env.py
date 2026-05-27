"""sync_once kind/env 정의와 Render full sync cron 환경변수 정합성."""
from __future__ import annotations

from pathlib import Path

import yaml


def test_sync_once_kind_env_matches_all_kinds() -> None:
    from app.scripts.sync_once import _KIND_ENV
    from app.services.sync import ALL_KINDS

    assert set(_KIND_ENV) == set(ALL_KINDS)


def test_render_full_sync_env_covers_sync_once_kinds() -> None:
    from app.scripts.sync_once import _KIND_ENV

    render_yaml = Path(__file__).resolve().parents[1] / "render.yaml"
    data = yaml.safe_load(render_yaml.read_text(encoding="utf-8"))
    services = data.get("services") or []
    full_sync = next(
        service for service in services
        if service.get("name") == "dy-task-sync-full"
    )
    env_keys = {
        item.get("key")
        for item in (full_sync.get("envVars") or [])
        if isinstance(item, dict)
    }

    expected = {"DATABASE_URL", "NOTION_API_KEY", *_KIND_ENV.values()}
    assert expected <= env_keys
