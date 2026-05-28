"""운영 health check 경로 회귀 테스트."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(autouse=True)
def _disable_external_services(monkeypatch: pytest.MonkeyPatch) -> None:
    """health route 테스트는 외부 서비스 설정에 의존하지 않는다."""
    monkeypatch.setenv("WORKS_ENABLED", "false")
    monkeypatch.setenv("WORKS_BOT_ENABLED", "false")
    monkeypatch.setenv("WORKS_DRIVE_ENABLED", "false")


def test_health_routes_return_ok() -> None:
    """루트 health와 API prefix health 모두 같은 응답을 제공한다."""
    with TestClient(app) as client:
        for path in ("/health", "/api/health"):
            response = client.get(path)
            assert response.status_code == 200
            assert response.json() == {"status": "ok"}
