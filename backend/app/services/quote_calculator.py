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

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

# 직접인건비 단가 — 정부 기술자 등급별 노임단가 (2026 기준). 매년 갱신.
# 종류별 strategy가 적합한 등급을 import해 사용.
DAILY_RATE_SENIOR_ENGINEER = 310_884       # 고급기술자 — 구조설계·점검류
DAILY_RATE_FIELD_SUPPORT = 253_985         # 현장기술지원 단가 (xlsx 실 사례)
DAILY_RATE_PROFESSIONAL_ENGINEER = 446_055  # 기술사 — 구조감리
DAILY_RATE_ENGINEER = 300_980              # 기술자 — 내진성능평가


class QuoteType(StrEnum):
    """견적서 종류 — PDF 헤더·파일명·문서번호 분류 코드·산출 strategy 분기 키.

    값은 노션 select 옵션 명·DB 저장값과 일치 (한글). 프론트 select 라벨도 동일.
    """

    STRUCT_DESIGN = "구조설계"
    STRUCT_REVIEW = "구조검토"
    PERF_SEISMIC = "성능기반내진설계"
    INSPECTION_REGULAR = "정기안전점검"
    INSPECTION_DETAIL = "정밀점검"
    INSPECTION_DIAGNOSIS = "정밀안전진단"
    INSPECTION_BMA = "건축물관리법점검"
    SEISMIC_EVAL = "내진성능평가"
    SUPERVISION = "구조감리"
    FIELD_SUPPORT = "현장기술지원"
    CUSTOM = "기타"


class DirectExpenseItem(BaseModel):
    """직접경비 동적 항목 — 사용자가 항목명·금액 자유 입력."""

    model_config = ConfigDict(populate_by_name=True)
    name: str = ""
    amount: float = Field(default=0, ge=0)


class QuoteInput(BaseModel):
    """견적서 입력값. 사용자가 입력하는 모든 변수."""

    model_config = ConfigDict(populate_by_name=True)

    # 견적서 종류 — dispatch 키. 빈 값/미지정이면 STRUCT_DESIGN으로 처리.
    quote_type: QuoteType = QuoteType.STRUCT_DESIGN
    # CUSTOM(기타)일 때만 PDF 헤더 제목으로 사용. 다른 종류는 _TITLE_MAP 참조.
    custom_title: str = ""
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
    # 값이 있으면 그 값을 사용 (자동 산출 무시). 정기/정밀점검은 시특법 4계수 곱한
    # 소수 인.일(15.24, 36.19 등) 입력이 필요해 float 허용.
    manhours_override: float | None = Field(default=None, ge=0)
    # 점검류 (PR-Q4~Q7) — 책임자/점검자 인.일 분리 입력
    inspection_responsible_days: float | None = Field(default=None, ge=0)
    inspection_inspector_days: float | None = Field(default=None, ge=0)
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
    """견적서 종류별 dispatch. 미구현 종류는 임시로 구조설계 strategy fallback —
    PR-Q2~Q9에서 종류별 strategy로 교체 예정.
    """
    strategy = _DISPATCH.get(inp.quote_type, _calculate_struct_design)
    return strategy(inp)


def _calculate_struct_design(inp: QuoteInput) -> QuoteResult:
    """구조설계용역견적서 산출 — xlsx 식 그대로 파이썬 재현."""
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


def _calculate_field_support(inp: QuoteInput) -> QuoteResult:
    """현장기술지원용역견적서 산출 (PR-Q2).

    구조설계와 거의 동일 흐름이나 핵심 차이:
    - baseline_manhours 자동 산출 X — 사용자가 인.일을 직접 입력
      (manhours_override 필수, 없으면 0)
    - 단가가 다름: 고급기술자 253,985원/인.일
    - 산출 행 라벨이 동일하므로 PDF template 그대로 재사용 가능
    - 직접경비/제경비(110%)/기술료(20%)/조정/절삭 모두 구조설계와 동일
    - default 조정%는 80 (xlsx 실 사례)

    xlsx 검증 (현장지원26-07-002.xlsx):
    K17=5인.일, H27=80%, 직접경비=50,000(교통비 25,000×2)
    → K27=2,610,168.8 → K28=610,169 (백만 미만) → K29=2,000,000
    """
    # 인.일 — 직접 입력 우선, 없으면 0 (현장지원은 자동 산출 모델 없음)
    mh_total = (
        int(inp.manhours_override) if inp.manhours_override is not None else 0
    )

    # 직접인건비 — 단가만 다름 (253,985원/인.일)
    direct_labor = mh_total * DAILY_RATE_FIELD_SUPPORT

    # 직접경비: 동적 list 우선, 없으면 legacy 합산
    if inp.direct_expense_items:
        direct_expense = sum(item.amount for item in inp.direct_expense_items)
    else:
        direct_expense = (
            inp.printing_fee + inp.survey_fee + 25_000 * inp.transport_persons
        )

    overhead = direct_labor * (inp.overhead_pct / 100)
    tech_fee = (direct_labor + overhead) * (inp.tech_fee_pct / 100)
    subtotal = direct_labor + overhead + tech_fee
    adjusted = subtotal * (inp.adjustment_pct / 100) + direct_expense

    # 절삭 — final_override 우선, 없으면 truncate_unit으로 절삭
    adjusted_int = int(_excel_round_half_up(adjusted, 0))
    if inp.final_override is not None:
        final_amount = int(inp.final_override)
        truncated = adjusted_int - final_amount
    else:
        unit = inp.truncate_unit if inp.truncate_unit > 0 else 1
        truncated = adjusted_int % unit
        final_amount = adjusted_int - truncated

    # VAT
    vat_amount = int(_excel_round_half_up(final_amount * 0.1, 0))
    final_with_vat = final_amount + vat_amount

    # 평당 — 현장지원은 회당 견적이라 의미 약함. 호환을 위해 채워둠.
    per_pyeong_area = inp.gross_floor_area / 3.3 if inp.gross_floor_area else 0
    per_pyeong = final_amount / per_pyeong_area if per_pyeong_area else 0

    return QuoteResult(
        manhours_baseline=0,
        manhours_baseline_rounded=0,
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


def _calculate_supervision(inp: QuoteInput) -> QuoteResult:
    """구조감리용역견적서 산출 (PR-Q3).

    구조설계와 산출 모델 자체가 다름:
    - 인.일 = 현장 방문회수 × 3 (회당 3인.일 hardcoded — xlsx K16=H14*3).
      사용자가 manhours_override로 81 직접 입력하는 패턴 (또는 visit_count
      신규 필드는 추후). 현 PR은 manhours_override 활용.
    - 단가: 기술사 446,055원/인.일 (xlsx E18 표기는 452,718이나 K18 수식은
      446055로 hardcoded — xlsx 사본 정정 안 된 oldest로 보임. 446055 사용)
    - tech_fee 30% (구조설계 20%)
    - **K25 합계가 직접경비 포함** (구조설계는 ⑧=①+⑥+⑦, 감리는
      ⑤+①+⑥+⑦ 모두 더함). 따라서 K26 조정은 단순 ×adj% (직접경비 더함 X)

    xlsx 검증 (구조감리26-08-003.xlsx K28=54,000,000):
    K16=81 (=H14*3, H14=27회), K22=800,000 (=200,000*4 외업), H26=55%
    → K18=36,130,455 → K23=39,743,500.5 → K24=22,762,186.65
    → K25=99,436,142.15 → K26=54,689,878.1825 → K28=54,000,000
    """
    mh_total = (
        int(inp.manhours_override) if inp.manhours_override is not None else 0
    )

    direct_labor = mh_total * DAILY_RATE_PROFESSIONAL_ENGINEER

    if inp.direct_expense_items:
        direct_expense = sum(item.amount for item in inp.direct_expense_items)
    else:
        direct_expense = (
            inp.printing_fee + inp.survey_fee + 25_000 * inp.transport_persons
        )

    overhead = direct_labor * (inp.overhead_pct / 100)
    tech_fee = (direct_labor + overhead) * (inp.tech_fee_pct / 100)
    # 구조감리: subtotal에 직접경비 포함, adjusted는 직접경비 더하지 않음
    subtotal = direct_labor + overhead + tech_fee + direct_expense
    adjusted = subtotal * (inp.adjustment_pct / 100)

    adjusted_int = int(_excel_round_half_up(adjusted, 0))
    if inp.final_override is not None:
        final_amount = int(inp.final_override)
        truncated = adjusted_int - final_amount
    else:
        unit = inp.truncate_unit if inp.truncate_unit > 0 else 1
        truncated = adjusted_int % unit
        final_amount = adjusted_int - truncated

    vat_amount = int(_excel_round_half_up(final_amount * 0.1, 0))
    final_with_vat = final_amount + vat_amount

    per_pyeong_area = inp.gross_floor_area / 3.3 if inp.gross_floor_area else 0
    per_pyeong = final_amount / per_pyeong_area if per_pyeong_area else 0

    return QuoteResult(
        manhours_baseline=0,
        manhours_baseline_rounded=0,
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


def _calculate_inspection_bma(inp: QuoteInput) -> QuoteResult:
    """건축물관리법점검 strategy (PR-Q4).

    xlsx '건축물관리법점검견적26-09-02.xls' 양식 transcribe.

    산출 모델
    - 책임자 인.일 × 456,237 + 점검자 인.일 × 235,459 (등급별 단가)
    - 매 단계 INT() (xlsx 수식이 INT()로 wrap, 결과 정수만 누적)
    - subtotal에 직접경비 포함 (구조감리와 동일 흐름) → adjusted = subtotal × adj%
    - 절삭은 truncate_unit (xlsx 양식은 ROUNDDOWN(_, -5) = 100,000 단위)
      → 사용자가 truncate_unit=100_000 선택 권장

    xlsx 검증 (책임자 1.44, 점검자 0.44, 직접경비 100,000, 조정 90%):
    - 직접인건비 = INT(456237×1.44) + INT(235459×0.44) = 656,981 + 103,601 = 760,582
    - 제경비    = INT(760,582 × 1.1)            = 836,640
    - 기술료    = INT((760,582+836,640) × 0.2)   = 319,444
    - 합계      = 760,582+836,640+319,444+100,000 = 2,016,666
    - 조정      = 2,016,666 × 0.9                = 1,814,999.4
    - 절삭(10만) = 14,999
    - 최종      = 1,800,000 (xlsx F23)
    """
    responsible = inp.inspection_responsible_days or 0
    inspector = inp.inspection_inspector_days or 0

    # 매 단계 INT() — xlsx 수식과 동일한 정수 누적 (truncation 보존)
    direct_labor = (
        int(responsible * 456_237) + int(inspector * 235_459)
    )
    direct_labor = int(direct_labor)  # F7 = INT(F8+F9)

    if inp.direct_expense_items:
        direct_expense = sum(item.amount for item in inp.direct_expense_items)
    else:
        direct_expense = (
            inp.printing_fee + inp.survey_fee + 25_000 * inp.transport_persons
        )

    overhead = int(direct_labor * (inp.overhead_pct / 100))           # F11=INT(F7*1.1)
    tech_fee = int((direct_labor + overhead) * (inp.tech_fee_pct / 100))  # F13=INT(...×0.2)
    subtotal = direct_labor + overhead + tech_fee + direct_expense    # F17 (직접경비 포함)
    adjusted = subtotal * (inp.adjustment_pct / 100)                  # F19 = F17 × adj

    adjusted_int = int(_excel_round_half_up(adjusted, 0))
    if inp.final_override is not None:
        final_amount = int(inp.final_override)
        truncated = adjusted_int - final_amount
    else:
        unit = inp.truncate_unit if inp.truncate_unit > 0 else 1
        truncated = adjusted_int % unit
        final_amount = adjusted_int - truncated

    vat_amount = int(_excel_round_half_up(final_amount * 0.1, 0))
    final_with_vat = final_amount + vat_amount

    # 인.일 합산은 표시용
    mh_total = int(round((responsible + inspector) * 100)) / 100
    per_pyeong_area = inp.gross_floor_area / 3.3 if inp.gross_floor_area else 0
    per_pyeong = final_amount / per_pyeong_area if per_pyeong_area else 0

    return QuoteResult(
        manhours_baseline=0,
        manhours_baseline_rounded=0,
        manhours_total=int(mh_total),
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


def _calculate_inspection_legal(inp: QuoteInput) -> QuoteResult:
    """정기안전점검 + 정밀점검 + 정밀안전진단 통합 strategy (PR-Q5/Q6).

    xlsx 시특법상 대가기준 sheet의 산출 흐름 transcribe.
    종류 분기는 시특법 sheet F11 코드(1=정밀안전진단/2=정밀점검/3=정기점검)에
    해당하지만 backend 흐름은 단일 — overhead/tech/adj/truncate default 차이만
    frontend QUOTE_TYPE_DEFAULTS에서 적용.

    산출
    - 인.일 = manhours_override (사용자가 시특법 sheet 4계수 곱한 H40 결과 입력)
    - direct_labor = ROUNDDOWN(인.일 × 310,884, 0)            # C59
    - overhead     = INT(direct_labor × 1.1)                  # D59 = INT(C59 × D54)
    - tech_fee     = INT((direct_labor + overhead) × 0.2)     # E59 = INT((C59+D59) × E54)
    - direct_expense = Σ direct_expense_items                  # F59 = J51 (사용자 입력 합계)
    - subtotal     = direct_labor + overhead + tech_fee + direct_expense   # J53
    - adjusted     = subtotal × adjustment_pct/100             # J56/J57
    - 절삭: 정기 100_000 / 정밀 1_000_000 (frontend default 분기, 사용자 변경 가능)

    xlsx 검증
    - 정기 (시특법 F11=3, mh=15.24, adj=0.27, unit=100_000, 직접경비=1,237,272):
        direct_labor = floor(15.24 × 310884) = 4,737,872   # C59
        overhead     = int(4737872 × 1.1)    = 5,211,659   # D59
        tech_fee     = int(9949531 × 0.2)    = 1,989,906   # E59
        subtotal     = 13,176,709                          # J53 (xlsx 13,176,708.75)
        adjusted     = 13,176,709 × 0.27     = 3,557,711.43
        truncated    = 57,711, final         = 3,500,000   # J58 ≈ xlsx 3,500,000.36
    - 정밀 (시특법 F11=2, mh=36.19, adj=0.88, unit=1_000_000, 직접경비=5,796,625):
        direct_labor = floor(36.19 × 310884) = 11,250,891  # C59
        overhead     = int(11250891 × 1.1)   = 12,375,980  # D59
        tech_fee     = int(23626871 × 0.2)   = 4,725,374   # E59
        subtotal     = 34,148,870                          # J54
        adjusted     = 34,148,870 × 0.88     = 30,051,005.6
        truncated    = 51,006, final         = 30,000,000  # J59 ≈ xlsx 29,999,999.6
    - 정밀안전진단 (시특법 F11=1, mh=54.42, overhead=1.2, tech=0.4, adj=0.45,
      unit=1_000_000, 직접경비=4,498,265):
        direct_labor = floor(54.42 × 310884) = 16,918,307  # C59
        overhead     = int(16918307 × 1.2)   = 20,301,968  # D59
        tech_fee     = int(37220275 × 0.4)   = 14,888,110  # E59
        subtotal     = 56,606,650                          # J54
        adjusted     = 56,606,650 × 0.45     = 25,472,992.5
        truncated    = 472,993, final        = 25,000,000  # J59 ≈ xlsx 24,999,999.5
    """
    import math

    mh = float(inp.manhours_override) if inp.manhours_override is not None else 0.0

    # 직접인건비 — ROUNDDOWN(인.일 × 단가, 0). 양수만 다루므로 floor와 동등.
    direct_labor = int(math.floor(mh * DAILY_RATE_SENIOR_ENGINEER))

    if inp.direct_expense_items:
        direct_expense = sum(item.amount for item in inp.direct_expense_items)
    else:
        direct_expense = (
            inp.printing_fee + inp.survey_fee + 25_000 * inp.transport_persons
        )

    overhead = int(direct_labor * (inp.overhead_pct / 100))
    tech_fee = int((direct_labor + overhead) * (inp.tech_fee_pct / 100))
    subtotal = direct_labor + overhead + tech_fee + direct_expense
    adjusted = subtotal * (inp.adjustment_pct / 100)

    adjusted_int = int(_excel_round_half_up(adjusted, 0))
    if inp.final_override is not None:
        final_amount = int(inp.final_override)
        truncated = adjusted_int - final_amount
    else:
        unit = inp.truncate_unit if inp.truncate_unit > 0 else 1
        truncated = adjusted_int % unit
        final_amount = adjusted_int - truncated

    vat_amount = int(_excel_round_half_up(final_amount * 0.1, 0))
    final_with_vat = final_amount + vat_amount

    per_pyeong_area = inp.gross_floor_area / 3.3 if inp.gross_floor_area else 0
    per_pyeong = final_amount / per_pyeong_area if per_pyeong_area else 0

    return QuoteResult(
        manhours_baseline=0,
        manhours_baseline_rounded=0,
        manhours_total=int(round(mh)),
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


# ── 종류별 산출 strategy dispatch ──
# PR-Q1: 모든 종류가 임시로 구조설계 strategy로 fallback. PR-Q2~Q9에서 점진적
# 으로 종류별 strategy 함수로 교체된다.
_DISPATCH: dict[QuoteType, "callable"] = {
    QuoteType.STRUCT_DESIGN: _calculate_struct_design,
    QuoteType.STRUCT_REVIEW: _calculate_struct_design,
    QuoteType.PERF_SEISMIC: _calculate_struct_design,
    QuoteType.INSPECTION_REGULAR: _calculate_inspection_legal,  # PR-Q5
    QuoteType.INSPECTION_DETAIL: _calculate_inspection_legal,   # PR-Q5
    QuoteType.INSPECTION_DIAGNOSIS: _calculate_inspection_legal,  # PR-Q6
    QuoteType.INSPECTION_BMA: _calculate_inspection_bma,  # PR-Q4
    QuoteType.SEISMIC_EVAL: _calculate_struct_design,
    QuoteType.SUPERVISION: _calculate_supervision,  # PR-Q3
    QuoteType.FIELD_SUPPORT: _calculate_field_support,  # PR-Q2
    QuoteType.CUSTOM: _calculate_struct_design,
}
