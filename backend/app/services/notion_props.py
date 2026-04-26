"""노션 page properties → 파이썬 값 추출 헬퍼.

노션 API 응답의 properties 는 타입별로 구조가 달라서 반복 코드를 유발한다.
이 모듈은 자주 쓰이는 추출을 한 줄 함수로 제공한다.
"""
from __future__ import annotations

from typing import Any


def title(props: dict[str, Any], name: str) -> str:
    arr = (props.get(name) or {}).get("title") or []
    return arr[0].get("plain_text", "") if arr else ""


def rich_text(props: dict[str, Any], name: str) -> str:
    arr = (props.get(name) or {}).get("rich_text") or []
    return "".join(seg.get("plain_text", "") for seg in arr)


def select_name(props: dict[str, Any], name: str) -> str:
    sel = (props.get(name) or {}).get("select")
    return sel.get("name", "") if sel else ""


def status_name(props: dict[str, Any], name: str) -> str:
    st = (props.get(name) or {}).get("status")
    return st.get("name", "") if st else ""


def multi_select_names(props: dict[str, Any], name: str) -> list[str]:
    arr = (props.get(name) or {}).get("multi_select") or []
    return [o.get("name", "") for o in arr]


def number(props: dict[str, Any], name: str) -> float | None:
    return (props.get(name) or {}).get("number")


def checkbox(props: dict[str, Any], name: str) -> bool:
    return bool((props.get(name) or {}).get("checkbox"))


def date_range(props: dict[str, Any], name: str) -> tuple[str | None, str | None]:
    """(start, end) ISO 문자열 튜플. 단일 날짜면 (start, None)."""
    d = (props.get(name) or {}).get("date")
    if not d:
        return None, None
    return d.get("start"), d.get("end")


def relation_ids(props: dict[str, Any], name: str) -> list[str]:
    arr = (props.get(name) or {}).get("relation") or []
    return [r.get("id", "") for r in arr]


def formula_value(props: dict[str, Any], name: str) -> Any:
    f = (props.get(name) or {}).get("formula") or {}
    t = f.get("type")
    return f.get(t) if t else None


def rollup_value(props: dict[str, Any], name: str) -> Any:
    r = (props.get(name) or {}).get("rollup") or {}
    t = r.get("type")
    if t == "number":
        return r.get("number")
    if t == "date":
        return r.get("date")
    if t == "array":
        return r.get("array") or []
    return r.get(t) if t else None
