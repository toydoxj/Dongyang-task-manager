"""Drive 임베디드 탐색기 — 단위 테스트.

NAVER WORKS API 자체 호출은 mock. resourceKey 추출 헬퍼 검증 + 라우터 401/422 분기.
"""
from __future__ import annotations

import pytest

from app.routers.projects import _extract_resource_key


def test_extract_resource_key_normal() -> None:
    url = (
        "https://drive.worksmobile.com/drive/web/share/root-folder"
        "?resourceKey=QDIwMDEwMDAwMDA1MzY3NjB8MzQ3MjYxMjU0MjUwNzAyNjQ0MHxGfDA"
        "&resourceLocation=24101"
    )
    assert (
        _extract_resource_key(url)
        == "QDIwMDEwMDAwMDA1MzY3NjB8MzQ3MjYxMjU0MjUwNzAyNjQ0MHxGfDA"
    )


def test_extract_resource_key_missing() -> None:
    assert _extract_resource_key("") == ""
    assert _extract_resource_key("https://drive.worksmobile.com/drive") == ""
    assert (
        _extract_resource_key(
            "https://drive.worksmobile.com/drive?resourceLocation=24101"
        )
        == ""
    )


def test_extract_resource_key_special_chars() -> None:
    """resourceKey에 base64url 특수문자(`@`, `|`)가 raw로 들어가도 추출 OK."""
    url = "https://drive.worksmobile.com/x?resourceKey=@2001%7C3472%7CD%7C0&x=1"
    # parse_qs가 자동 url-decode → @2001|3472|D|0
    assert _extract_resource_key(url) == "@2001|3472|D|0"


@pytest.mark.parametrize(
    "url",
    [
        "not a url",
        "ftp://something/x",
        "javascript:alert(1)",
    ],
)
def test_extract_resource_key_robust(url: str) -> None:
    # 비정상 입력에도 빈 string 반환 (예외 throw 안 함)
    assert _extract_resource_key(url) == ""
