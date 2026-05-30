from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.routers.master_projects import _needs_image_url_refresh


def _row(image_type: str, synced_at: datetime) -> SimpleNamespace:
    return SimpleNamespace(
        content={"type": image_type, image_type: {"url": "https://example.com/a.png"}},
        synced_at=synced_at,
    )


def test_master_image_file_rows_refresh_after_signed_url_window() -> None:
    rows = [_row("file", datetime.now(UTC) - timedelta(minutes=11))]

    assert _needs_image_url_refresh(rows)


def test_master_image_empty_rows_refresh_for_initial_sync() -> None:
    assert _needs_image_url_refresh([])


def test_master_image_fresh_file_rows_do_not_refresh() -> None:
    rows = [_row("file", datetime.now(UTC) - timedelta(minutes=3))]

    assert not _needs_image_url_refresh(rows)


def test_master_image_external_rows_do_not_refresh() -> None:
    rows = [_row("external", datetime.now(UTC) - timedelta(days=1))]

    assert not _needs_image_url_refresh(rows)
