"""sync_once kind/env 정의와 Render cron HTTP trigger 정합성."""
from __future__ import annotations

from pathlib import Path

import yaml


def test_sync_once_kind_env_matches_all_kinds() -> None:
    from app.scripts.sync_once import _KIND_ENV
    from app.services.sync import ALL_KINDS

    assert set(_KIND_ENV) == set(ALL_KINDS)


def test_render_cron_services_are_http_triggers() -> None:
    render_yaml = Path(__file__).resolve().parents[1] / "render.yaml"
    data = yaml.safe_load(render_yaml.read_text(encoding="utf-8"))
    services = data.get("services") or []
    cron_services = {
        service.get("name"): service
        for service in services
        if service.get("type") == "cron"
    }

    expected = {
        "dy-task-sync-full": "/api/cron/sync?full=true&force=true",
        "dy-task-outbox-drain": "/api/cron/outbox-drain?batch=20",
        "dy-task-auto-progress-cron": "/api/cron/auto-progress",
    }

    assert set(expected) <= set(cron_services)
    for name, path in expected.items():
        service = cron_services[name]
        env_keys = {
            item.get("key")
            for item in (service.get("envVars") or [])
            if isinstance(item, dict)
        }
        assert service.get("buildCommand") == "true"
        assert service.get("autoDeployTrigger") == "off"
        assert env_keys == {"PYTHON_VERSION", "CRON_SECRET"}
        assert path in service.get("startCommand", "")
