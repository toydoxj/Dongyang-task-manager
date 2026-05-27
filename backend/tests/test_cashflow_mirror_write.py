"""PR-GA 회귀 — cashflow income update/delete mirror-first + outbox (PR-FZ 패턴).

수금(income) update/delete는 노션 동기 호출 0건. create는 노션 직접 유지.
지출(expense)은 read 전용이라 전환 대상 아님.
"""
from __future__ import annotations

import inspect

from app.routers.cashflow import (
    IncomeUpdateRequest,
    _income_update_props,
    create_income,
    delete_income,
    update_income,
)


def test_income_update_delete_no_notion_dependency() -> None:
    assert "notion" not in inspect.signature(update_income).parameters
    assert "notion" not in inspect.signature(delete_income).parameters


def test_income_create_keeps_notion_dependency() -> None:
    assert "notion" in inspect.signature(create_income).parameters


def test_income_update_props_empty_when_no_fields() -> None:
    assert _income_update_props(IncomeUpdateRequest()) == {}


def test_income_update_props_builds_only_changed_fields() -> None:
    props = _income_update_props(IncomeUpdateRequest(amount=5000, note="2차 수금"))
    assert props["수금액(원)"]["number"] == 5000
    assert props["비고"]["rich_text"][0]["text"]["content"] == "2차 수금"
    assert "수금일" not in props  # 미지정 필드 제외
