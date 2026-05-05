"""견적서 xlsx 출력 — 사장 운영 양식(`templates/quote_template.xlsx`)에 셀 fill.

사용자가 입력한 값(form_data['input'])을 template의 알려진 셀 좌표에 채워 넣고,
산출 셀(K18~K30 등)의 Excel 수식은 그대로 두어 Excel이 열릴 때 자동 계산.
산출 결과는 quote_form_data['result']에도 저장되지만 xlsx에는 수식 유지가 정답
(원본과 동일한 인쇄·재계산 동작).

template 셀 좌표는 docs/설계견적26-01-007*.xlsx 셀 dump 분석 결과:
  B3  문서번호 (예: " 26 - 01 - 007")
  D4  수신처 회사명          J4  전화
  D5  참조자                 J5  E-mail
  D6  용역명
  D7  위치
  E8  연면적 (number)
  J8  층수 텍스트
  D9  구조형식
  J12 계수 (0.5/1.0)
  H16 종별 요율
  H17 구조방식 요율
  K21 보고서인쇄비           K22 추가조사비
  I23 교통비 인.일
  H28 당사조정 %
  D31 지불방법
  D32 특이사항
  G33 작성일
"""
from __future__ import annotations

import io
from datetime import date
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "quote_template.xlsx"
_SHEET_NAME = "구조검토"


def build_quote_xlsx(
    form_data: dict[str, Any], *, doc_number: str = ""
) -> bytes:
    """form_data['input']를 template에 fill 후 bytes 반환.

    Excel 수식(K18~K30, D10 NUMBERSTRING 등)은 그대로 보존되어 Excel/Numbers/
    LibreOffice가 열 때 자동 재계산된다.
    """
    if not _TEMPLATE_PATH.exists():
        raise FileNotFoundError(
            f"견적서 템플릿이 없습니다: {_TEMPLATE_PATH}. "
            "backend/app/templates/quote_template.xlsx 를 배포에 포함하세요."
        )

    wb = load_workbook(_TEMPLATE_PATH)
    ws = wb[_SHEET_NAME]
    inp = form_data.get("input") or {}

    # 헤더
    if doc_number:
        # 사장 양식의 공백 패턴(" 26 - 01 - 007") 유지
        yy, mm, nnn = doc_number.split("-")
        ws["B3"] = f" {yy} - {mm} - {nnn}"

    # 수신처
    ws["D4"] = inp.get("recipient_company", "")
    ws["D5"] = inp.get("recipient_person", "")
    if inp.get("recipient_phone"):
        ws["J4"] = inp["recipient_phone"]
    if inp.get("recipient_email"):
        ws["J5"] = inp["recipient_email"]

    # 용역 정보
    ws["D6"] = inp.get("service_name", "")
    ws["D7"] = inp.get("location", "")
    if inp.get("gross_floor_area") is not None:
        ws["E8"] = float(inp["gross_floor_area"])
    if inp.get("floors_text"):
        ws["J8"] = inp["floors_text"]
    if inp.get("structure_form"):
        ws["D9"] = f"  {inp['structure_form']}"  # template은 두 칸 들여쓴 형태

    # 산출 변수
    ws["J12"] = float(inp.get("coefficient", 1.0))
    ws["H16"] = float(inp.get("type_rate", 1.0))
    ws["H17"] = float(inp.get("structure_rate", 1.0))
    ws["H28"] = int(inp.get("adjustment_pct", 87))

    # 직접경비
    ws["K21"] = int(inp.get("printing_fee") or 0)
    ws["K22"] = int(inp.get("survey_fee") or 0)
    ws["I23"] = int(inp.get("transport_persons") or 0)

    # 자유 텍스트
    if inp.get("payment_terms"):
        ws["D31"] = f" {inp['payment_terms']}"
    if inp.get("special_notes"):
        ws["D32"] = f" {inp['special_notes']}"

    # 작성일 (오늘 KST)
    ws["G33"] = "            " + date.today().strftime("%Y. %m. %d")

    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()


def quote_filename(doc_number: str, service_name: str) -> str:
    """파일명 규칙: 설계견적{doc_number}({service_name 안전한 일부}).xlsx.

    윈도우 금지 문자(\\/:*?"<>|) + 줄바꿈 제거. 30자 cap.
    """
    safe = "".join(c for c in service_name if c not in r'\/:*?"<>|' + "\r\n")
    safe = safe.strip()[:30]
    return f"설계견적{doc_number}({safe}).xlsx"
