"""노션 page properties → 파이썬 값 추출 헬퍼.

노션 API 응답의 properties 는 타입별로 구조가 달라서 반복 코드를 유발한다.
이 모듈은 자주 쓰이는 추출을 한 줄 함수로 제공한다.
"""
from __future__ import annotations

from typing import Any


def _seg_text(seg: dict[str, Any]) -> str:
    """rich_text/title segment → 텍스트.

    노션 API 응답은 read 전용 `plain_text`를 채워주지만, mirror-direct write
    경로(PR-FR)에서 저장되는 write 포맷({"text": {"content": ...}})에는
    plain_text가 없다. 두 포맷 모두 읽도록 text.content로 fallback.
    """
    return seg.get("plain_text") or (seg.get("text") or {}).get("content", "")


def normalize_properties_for_mirror(
    props: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """mirror 저장용 properties 정규화 — write 포맷 segment에 plain_text 보강.

    mirror-direct write(PR-FR)가 저장하는 write 포맷({"text": {"content": v}})에는
    노션 read 응답의 `plain_text`가 없어, read helper / 자체 추출 루프가 빈 값으로
    읽는 cascade가 발생한다 (제목·코드·비고 소실). 노션 = 백업, mirror = 작업 DB
    원칙상 mirror에 저장되는 데이터 자체가 read 가능한 정상 포맷이어야 하므로,
    저장 직전 top-level title/rich_text property의 각 segment에 plain_text를 보강한다.

      - idempotent: 이미 plain_text가 있으면 그대로 둠 (노션 read-포맷에 무해)
      - top-level title/rich_text 배열만 비재귀 처리 — rollup/formula/people/date 등 미손상
      - text 키 없는 segment(mention/equation 등)는 보강하지 않음
      - 원본 dict는 변형하지 않음 (변경분만 얕은 복사, 변경 없으면 원본 그대로 반환)
    """
    if not props:
        return props
    out: dict[str, Any] | None = None
    for key, val in props.items():
        if not isinstance(val, dict):
            continue
        kind = (
            "title"
            if isinstance(val.get("title"), list)
            else ("rich_text" if isinstance(val.get("rich_text"), list) else None)
        )
        if kind is None:
            continue
        arr = val[kind]
        new_arr: list[Any] | None = None
        for i, seg in enumerate(arr):
            if (
                isinstance(seg, dict)
                and "plain_text" not in seg
                and isinstance(seg.get("text"), dict)
                and "content" in seg["text"]
            ):
                if new_arr is None:
                    new_arr = list(arr)
                new_arr[i] = {**seg, "plain_text": seg["text"]["content"]}
        if new_arr is not None:
            if out is None:
                out = dict(props)
            out[key] = {**val, kind: new_arr}
    return out if out is not None else props


def title(props: dict[str, Any], name: str) -> str:
    arr = (props.get(name) or {}).get("title") or []
    return _seg_text(arr[0]) if arr else ""


def rich_text(props: dict[str, Any], name: str) -> str:
    arr = (props.get(name) or {}).get("rich_text") or []
    return "".join(_seg_text(seg) for seg in arr)


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


def url(props: dict[str, Any], name: str) -> str:
    """url 타입 property 추출 — 빈 값이면 빈 문자열."""
    v = (props.get(name) or {}).get("url")
    return str(v) if v else ""


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


def files(props: dict[str, Any], name: str) -> list[dict[str, str]]:
    """files property → [{name, url, type}]. type='file'(노션호스팅, 1h URL) 또는 'external'."""
    arr = (props.get(name) or {}).get("files") or []
    out: list[dict[str, str]] = []
    for f in arr:
        item_name = f.get("name", "")
        if f.get("type") == "external":
            url = (f.get("external") or {}).get("url", "")
            out.append({"name": item_name, "url": url, "type": "external"})
        else:
            url = (f.get("file") or {}).get("url", "")
            out.append({"name": item_name, "url": url, "type": "file"})
    return out


def formula_value(props: dict[str, Any], name: str) -> Any:
    f = (props.get(name) or {}).get("formula") or {}
    t = f.get("type")
    return f.get(t) if t else None


def rollup_value(props: dict[str, Any], name: str) -> Any:
    """rollup 값을 사람이 읽을 수 있는 형태로 추출.

    - number/date: 그대로 반환
    - array: 각 element 의 type 별로 text/number/date 평탄화 → 콤마 join 문자열
    """
    r = (props.get(name) or {}).get("rollup") or {}
    t = r.get("type")
    if t == "number":
        return r.get("number")
    if t == "date":
        return r.get("date")
    if t == "array":
        return rollup_array_to_text(r.get("array") or [])
    return r.get(t) if t else None


def rollup_array_to_text(arr: list[dict[str, Any]]) -> str:
    """rollup array 항목을 사람이 읽을 수 있는 문자열로 평탄화."""
    parts: list[str] = []
    for it in arr:
        it_type = it.get("type")
        if it_type == "rich_text":
            seg = "".join(s.get("plain_text", "") for s in it.get("rich_text") or [])
            if seg:
                parts.append(seg)
        elif it_type == "title":
            seg = "".join(s.get("plain_text", "") for s in it.get("title") or [])
            if seg:
                parts.append(seg)
        elif it_type == "number":
            n = it.get("number")
            if n is not None:
                parts.append(str(n))
        elif it_type == "date":
            d = it.get("date") or {}
            s = d.get("start")
            if s:
                parts.append(s)
        elif it_type == "select":
            sel = it.get("select")
            if sel:
                parts.append(sel.get("name", ""))
        elif it_type == "multi_select":
            for opt in it.get("multi_select") or []:
                if opt.get("name"):
                    parts.append(opt["name"])
        elif it_type == "url":
            u = it.get("url")
            if u:
                parts.append(u)
        elif it_type:
            v = it.get(it_type)
            if isinstance(v, str | int | float):
                parts.append(str(v))
    return ", ".join(parts)
