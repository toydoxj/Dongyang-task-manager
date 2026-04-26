"""노션 4개 DB 스키마 검증.

사용법:
    cd backend
    uv run python ../scripts/check_notion_schema.py

각 DB의 (1) 접근 권한, (2) 필수 속성, (3) 속성 타입 일치를 검증한다.
"""
from __future__ import annotations

import asyncio
import os
import sys

# backend/ 를 import path 에 추가
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "backend"))

# Windows cp949 콘솔에서도 한글 깨지지 않게
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.exceptions import AppError  # noqa: E402
from app.services.notion import get_notion  # noqa: E402
from app.settings import get_settings  # noqa: E402


# 각 DB 의 (alias) → (settings 속성, 기대 속성 dict)
EXPECTED: dict[str, dict[str, str]] = {
    "PROJECTS": {
        "프로젝트명": "title",
        "진행단계": "select",
        "시작일": "date",
        "계약기간": "date",
        "완료일": "date",
        "담당자": "multi_select",
        "담당팀": "multi_select",
        "업무내용": "multi_select",
        "용역비(VAT제외)": "number",
    },
    "TASKS": {
        "내용": "title",
        "프로젝트": "relation",
        "상태": "status",
        "진행률": "number",
        "기간": "date",
        "담당자": "multi_select",
    },
    "CASHFLOW": {
        "수금일": "date",
        "수금액(원)": "number",
    },
    "EXPENSE": {
        "지출일": "date",
        "금액": "number",
        "구분": "select",
    },
}


def db_id_for(alias: str) -> str:
    s = get_settings()
    mapping = {
        "PROJECTS": s.notion_db_projects,
        "TASKS": s.notion_db_tasks,
        "CASHFLOW": s.notion_db_cashflow,
        "EXPENSE": s.notion_db_expense,
    }
    return mapping[alias]


async def check_one(alias: str) -> tuple[bool, list[str]]:
    """반환: (전체 OK?, 메시지 목록)"""
    msgs: list[str] = []
    db_id = db_id_for(alias)
    if not db_id:
        return False, [f"  [SKIP] {alias}: settings 미설정"]

    try:
        ds = await get_notion().get_data_source(db_id)
    except AppError as exc:
        return False, [f"  [ERR] {alias}: 접근 실패 - {exc.message}"]
    except Exception as exc:
        return False, [f"  [ERR] {alias}: 예외 - {exc}"]

    title_arr = ds.get("title") or []
    title = title_arr[0].get("plain_text", "") if title_arr else "(no title)"
    props = ds.get("properties", {})
    msgs.append(f"  [OK]  {alias} - '{title}' ({len(props)} props)")

    expected = EXPECTED[alias]
    missing = []
    type_mismatch = []
    for name, expected_type in expected.items():
        if name not in props:
            missing.append(name)
            continue
        actual_type = props[name].get("type")
        if actual_type != expected_type:
            type_mismatch.append(f"{name}({actual_type}≠{expected_type})")

    if missing:
        msgs.append(f"        ⚠ 누락 속성: {', '.join(missing)}")
    if type_mismatch:
        msgs.append(f"        ⚠ 타입 불일치: {', '.join(type_mismatch)}")
    return not missing and not type_mismatch, msgs


async def main() -> int:
    print("=== 노션 DB 스키마 검증 ===\n")
    overall = True
    for alias in EXPECTED.keys():
        ok, msgs = await check_one(alias)
        for m in msgs:
            print(m)
        overall &= ok
    print("\n=== 결과:", "전체 OK ✓" if overall else "문제 발견 ✗", "===")
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
