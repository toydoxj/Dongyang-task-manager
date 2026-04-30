"""sso_works_bot._normalize_private_key — 다양한 PEM 입력 형태가 표준 multi-line으로
복원되는지 회귀 검증.

운영 사례(2026-04-30): Render env에 PEM을 붙여넣으니 줄바꿈이 공백으로 squash되어
cryptography가 `MalformedFraming` 에러를 냈다. 이후 single-line/공백평탄화 PEM도
자동 복원하도록 강화. 본 테스트는 그 패턴 4종을 모두 커버한다.
"""
from __future__ import annotations

from app.services.sso_works_bot import _normalize_private_key

# 32자 base64 한 줄 + 32자 한 줄짜리 가짜 PEM. 실제 키와 무관 — 정규화 로직만 검증.
_BODY_LINES = [
    "MIIBVgIBADANBgkqhkiG9w0BAQEFAASCAUAwggE8AgEAAkEA",
    "iLnnYr4QUpxbKKRH/3JHxXwjYO2YGGz0JfjJg+kJxZpkJzkJ",
    "ZrL8Yh4kJ1vN3qGz0JfjJg+kJxZpkJzkJZrL8Yh4kJ1vN3qG",
]
_HEADER = "-----BEGIN PRIVATE KEY-----"
_FOOTER = "-----END PRIVATE KEY-----"
_BODY_PLAIN = "".join(_BODY_LINES)


def _expected() -> str:
    """정규화 후 기대값 — 64자 단위로 wrap된 multi-line PEM."""
    wrapped = "\n".join(
        _BODY_PLAIN[i : i + 64] for i in range(0, len(_BODY_PLAIN), 64)
    )
    return f"{_HEADER}\n{wrapped}\n{_FOOTER}\n"


def test_normal_multiline_passthrough() -> None:
    """이미 정상 multi-line이면 trailing newline만 보장."""
    raw = f"{_HEADER}\n" + "\n".join(_BODY_LINES) + f"\n{_FOOTER}"
    out = _normalize_private_key(raw)
    assert out.startswith(_HEADER)
    assert out.endswith(f"{_FOOTER}\n")
    assert "\n" in out


def test_escaped_newlines_single_line() -> None:
    """`\\n` 이스케이프된 single-line — 실제 줄바꿈으로 복원."""
    raw = f"{_HEADER}\\n" + "\\n".join(_BODY_LINES) + f"\\n{_FOOTER}"
    out = _normalize_private_key(raw)
    assert "\\n" not in out
    assert "\n" in out
    assert _HEADER in out
    assert _FOOTER in out


def test_whitespace_squashed_single_line() -> None:
    """multi-line이 공백으로 평탄화된 케이스 — Render env 운영 사고 패턴.

    cryptography의 MalformedFraming의 실제 트리거. base64 본문이 공백으로
    잘려도 64자 wrap으로 표준 PEM 복원.
    """
    raw = f"{_HEADER} " + " ".join(_BODY_LINES) + f" {_FOOTER}"
    out = _normalize_private_key(raw)
    assert out == _expected()


def test_mixed_whitespace_squashed() -> None:
    """탭/CR/혼합 공백도 모두 흡수."""
    raw = f"{_HEADER}\t" + "\t \r ".join(_BODY_LINES) + f"  \r\t{_FOOTER}"
    out = _normalize_private_key(raw)
    assert out == _expected()


def test_empty_returns_empty() -> None:
    assert _normalize_private_key("") == ""
    assert _normalize_private_key("   ") == ""


def test_unknown_format_passthrough() -> None:
    """base64조차 아닌 임의 문자열은 그대로 반환 (cryptography가 에러 메시지 띄우도록)."""
    raw = "not a pem at all!"  # `!`는 base64 alphabet 외
    assert _normalize_private_key(raw) == raw


def test_marker_missing_multiline_body() -> None:
    """BEGIN/END 마커 누락 + base64 본문만 multi-line으로 들어온 케이스 (실제 운영
    사고). PKCS#8 PRIVATE KEY로 가정하고 마커 자동 추가 + 64자 wrap."""
    raw = "\n".join(_BODY_LINES)
    out = _normalize_private_key(raw)
    assert out.startswith("-----BEGIN PRIVATE KEY-----\n")
    assert out.endswith("-----END PRIVATE KEY-----\n")
    # 본문은 64자 단위 wrap된 expected와 동일
    inner = out.split("-----BEGIN PRIVATE KEY-----\n")[1].split("\n-----END")[0]
    assert inner == "\n".join(
        _BODY_PLAIN[i : i + 64] for i in range(0, len(_BODY_PLAIN), 64)
    )


def test_marker_missing_single_line_body() -> None:
    """마커 누락 + base64 본문이 공백 평탄화된 single-line 케이스."""
    raw = " ".join(_BODY_LINES)  # space로 합쳐짐
    out = _normalize_private_key(raw)
    assert out.startswith("-----BEGIN PRIVATE KEY-----\n")
    assert out.endswith("-----END PRIVATE KEY-----\n")
