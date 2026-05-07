"""구조설계 견적서 산출 엔진.

사장이 운영하던 xlsx 견적서 양식(`docs/설계견적*.xlsx`)의 IF·ROUND·RIGHT
공식을 그대로 파이썬으로 재현. 셀 dump로 검증된 식 (5192m²·요율 1·1.2·0.5
입력 → 25,000,000원 출력)을 fixture로 단위 테스트.

산출 흐름:
1. baseline_manhours(area_m2): 연면적 구간별 IF식 4단계 (1k/2k/5k/15k/50k/100k 분기)
2. manhours_total = ROUND(ROUND(baseline, 0) × type_rate × structure_rate × coefficient, 0)
3. direct_labor = manhours_total × 310,884 (고급기술자 단가)
4. direct_expense = printing + survey + 25,000 × transport_persons
5. overhead = direct_labor × 1.10
6. tech_fee = (direct_labor + overhead) × 0.20
7. subtotal = direct_labor + overhead + tech_fee
8. adjusted = subtotal × adjustment_pct/100 + direct_expense
9. truncated = round(adjusted) % 1_000_000  (Excel RIGHT(TEXT, 7) 재현 — 100만 미만 절삭)
10. final = adjusted - truncated  (백만 단위로 떨어지는 깔끔한 견적가)
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

# 직접인건비 단가 — 정부 기술자 등급별 노임단가 (고급기술자, 2026 기준).
# 매년 단가 발표 시 갱신.
DAILY_RATE_SENIOR_ENGINEER = 310_884


class DirectExpenseItem(BaseModel):
    """직접경비 동적 항목 — 사용자가 항목명·금액 자유 입력."""

    model_config = ConfigDict(populate_by_name=True)
    name: str = ""
    amount: float = Field(default=0, ge=0)


class QuoteInput(BaseModel):
    """견적서 입력값. 사용자가 입력하는 모든 변수."""

    model_config = ConfigDict(populate_by_name=True)

    # 메타
    service_name: str = ""  # 용역명
    location: str = ""  # 위치
    structure_form: str = ""  # 구조형식
    # 규모 — 영업 정보(Sale 모델)와 동일 필드. 견적서 입력이 영업 row의
    # gross_floor_area/floors_above/floors_below/building_count를 채움.
    floors_above: int | None = Field(default=None, ge=0)  # 지상층수
    floors_below: int | None = Field(default=None, ge=0)  # 지하층수
    building_count: int | None = Field(default=None, ge=0)  # 동수
    floors_text: str = ""  # legacy 자유 텍스트 — 비면 above/below로 자동 표기
    # 수신처
    recipient_company: str = ""
    recipient_person: str = ""
    recipient_phone: str = ""
    recipient_email: str = ""
    # 사양 — 산출에 필수
    gross_floor_area: float = Field(default=0, ge=0)  # 연면적 m²
    type_rate: float = Field(default=1.0, gt=0)  # 종별 요율 (0.8~1.2)
    structure_rate: float = Field(default=1.0, gt=0)  # 구조방식 요율 (0.5~1.5)
    coefficient: float = Field(default=1.0, gt=0)  # 계수 (0.5: 계산서만, 1.0: 계산서+도면)
    # 투입인원 직접 입력 — None이면 (연면적 × 요율들)로 자동 산출.
    # 정수면 그 값을 사용 (자동 산출 무시).
    manhours_override: int | None = Field(default=None, ge=0)
    # 직접경비 — 동적 항목 list. 비어 있으면 산출에 0원.
    # legacy 필드(printing_fee/survey_fee/transport_persons)는 backward 호환용.
    direct_expense_items: list[DirectExpenseItem] = []
    # 제경비 / 기술료 % — default는 사장 운영 표준 (110% / 20%)
    overhead_pct: float = Field(default=110, ge=0, le=500)
    tech_fee_pct: float = Field(default=20, ge=0, le=200)
    # 조정·옵션
    adjustment_pct: float = Field(default=87, ge=0, le=200)  # 당사조정 % (default 87)
    # 절삭 단위 — 백만(1,000,000) / 십만 / 만 등. 0이면 절삭 안 함.
    truncate_unit: int = Field(default=1_000_000, ge=0)
    # 최종 금액 직접 지정 — 정수면 truncate_unit 무시하고 그 값 사용 (수동 가격).
    final_override: int | None = Field(default=None, ge=0)
    # VAT 포함 여부 — UI 표시 + PDF 출력에만 영향. 영업 등록 금액(estimated_amount)
    # 은 항상 공급가액(final, VAT 별도). True면 산출 패널/PDF에 공급가액·VAT·합계
    # 3줄을 추가 표시.
    vat_included: bool = False
    # 자유 텍스트
    payment_terms: str = ""  # 지불방법
    special_notes: str = ""  # 특이사항
    # ── legacy (기존 영업 호환) ──
    # 기존 quote_form_data가 이 필드들을 갖고 있을 수 있음. direct_expense_items가
    # 비었을 때만 합산해서 사용.
    printing_fee: float = Field(default=0, ge=0)
    survey_fee: float = Field(default=0, ge=0)
    transport_persons: int = Field(default=0, ge=0)


class QuoteResult(BaseModel):
    """산출 결과."""

    model_config = ConfigDict(populate_by_name=True)

    manhours_baseline: float  # 연면적 기반 인.일 (반올림 전)
    manhours_baseline_rounded: int  # 정수 인.일 (xlsx ROUND inner)
    manhours_total: int  # 요율들 곱 + 반올림 (xlsx H19)
    direct_labor: float  # K20
    direct_expense: float  # K24 (인쇄+조사+교통)
    overhead: float  # K25
    tech_fee: float  # K26
    subtotal: float  # K27
    adjusted: float  # K28
    truncated: int  # K29 (100만 미만)
    final: int  # K30 (백만 단위 절삭 후 — 사장 표기용, 항상 공급가액)
    vat_amount: int  # final × 10% (한국 부가세, round 1원 단위)
    final_with_vat: int  # final + vat_amount
    per_pyeong_area: float  # P28 (평수 = 연면적/3.3)
    per_pyeong: float  # Q28 (평당 단가 = final / per_pyeong_area)


def baseline_manhours(area_m2: float) -> float:
    """연면적 구간별 인.일 산출 (xlsx H19의 inner IF 식).

    구간:
      ≤  1,000:  18
      ≤  2,000:  18 + 0.012 × (A - 1,000)
      ≤  5,000:  30 + 0.010 × (A - 2,000)
      ≤ 15,000:  60 + 0.009 × (A - 5,000)
      ≤ 50,000: 150 + 0.008 × (A - 15,000)
      ≤100,000: 430 + 0.007 × (A - 50,000)
      >100,000: 780 + 0.006 × (A - 100,000)
    """
    if area_m2 <= 1_000:
        return 18.0
    if area_m2 <= 2_000:
        return 18 + 0.012 * (area_m2 - 1_000)
    if area_m2 <= 5_000:
        return 30 + 0.010 * (area_m2 - 2_000)
    if area_m2 <= 15_000:
        return 60 + 0.009 * (area_m2 - 5_000)
    if area_m2 <= 50_000:
        return 150 + 0.008 * (area_m2 - 15_000)
    if area_m2 <= 100_000:
        return 430 + 0.007 * (area_m2 - 50_000)
    return 780 + 0.006 * (area_m2 - 100_000)


def _excel_round_half_up(value: float, ndigits: int = 0) -> int | float:
    """Excel ROUND 호환 반올림 (half-away-from-zero).

    Python의 built-in round()는 banker's rounding이라 0.5는 짝수 쪽으로 감.
    Excel은 0.5를 항상 위로(절대값 증가) 반올림 → 결과 차이 가능.
    """
    import math

    factor = 10 ** ndigits
    if value >= 0:
        return int(math.floor(value * factor + 0.5)) / factor if ndigits else int(
            math.floor(value * factor + 0.5)
        )
    return -(int(math.floor(-value * factor + 0.5)) / factor) if ndigits else -int(
        math.floor(-value * factor + 0.5)
    )


def calculate(inp: QuoteInput) -> QuoteResult:
    """견적서 산출 — xlsx 식 그대로 파이썬 재현."""
    # 1. 인.일 산출 — manhours_override가 있으면 그 값, 없으면 자동(ROUND 두 번)
    bm = baseline_manhours(inp.gross_floor_area)
    bm_rounded = int(_excel_round_half_up(bm, 0))
    if inp.manhours_override is not None:
        mh_total = int(inp.manhours_override)
    else:
        mh_total = int(
            _excel_round_half_up(
                bm_rounded * inp.type_rate * inp.structure_rate * inp.coefficient, 0
            )
        )

    # 2. 산출
    direct_labor = mh_total * DAILY_RATE_SENIOR_ENGINEER
    # 직접경비: 새 동적 항목 list 우선, 없으면 legacy 필드 fallback
    if inp.direct_expense_items:
        direct_expense = sum(item.amount for item in inp.direct_expense_items)
    else:
        direct_expense = (
            inp.printing_fee + inp.survey_fee + 25_000 * inp.transport_persons
        )
    overhead = direct_labor * (inp.overhead_pct / 100)
    tech_fee = (direct_labor + overhead) * (inp.tech_fee_pct / 100)
    subtotal = direct_labor + overhead + tech_fee

    # 3. 당사 조정 (조정% 적용 + 직접경비 더함)
    adjusted = subtotal * (inp.adjustment_pct / 100) + direct_expense

    # 4. 절삭 — final_override 우선, 없으면 truncate_unit으로 절삭
    adjusted_int = int(_excel_round_half_up(adjusted, 0))
    if inp.final_override is not None:
        final_amount = int(inp.final_override)
        truncated = adjusted_int - final_amount  # 표시용 (음수 가능)
    else:
        unit = inp.truncate_unit if inp.truncate_unit > 0 else 1
        truncated = adjusted_int % unit
        final_amount = adjusted_int - truncated

    # 6. VAT (한국 부가세 10%) — final은 항상 공급가액. UI/xlsx 표시 분기는
    # vat_included 플래그가 결정하지만 계산값 자체는 항상 채워 응답에 일관성 유지.
    vat_amount = int(_excel_round_half_up(final_amount * 0.1, 0))
    final_with_vat = final_amount + vat_amount

    # 7. 평당 (P28, Q28)
    per_pyeong_area = inp.gross_floor_area / 3.3 if inp.gross_floor_area else 0
    per_pyeong = final_amount / per_pyeong_area if per_pyeong_area else 0

    return QuoteResult(
        manhours_baseline=bm,
        manhours_baseline_rounded=bm_rounded,
        manhours_total=mh_total,
        direct_labor=direct_labor,
        direct_expense=direct_expense,
        overhead=overhead,
        tech_fee=tech_fee,
        subtotal=subtotal,
        adjusted=adjusted,
        truncated=truncated,
        final=final_amount,
        vat_amount=vat_amount,
        final_with_vat=final_with_vat,
        per_pyeong_area=per_pyeong_area,
        per_pyeong=per_pyeong,
    )
