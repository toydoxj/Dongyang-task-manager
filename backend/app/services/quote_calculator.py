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
# 내진평가 패키지 부속 모듈 — xlsx 운영 양식 단가 (사장 사용 견적서 사본 추출)
DAILY_RATE_REINFORCEMENT = 242_055         # 내진보강설계·기술감리
DAILY_RATE_THIRD_PARTY = 292_249           # 3자검토


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
    # 내진성능평가 패키지 부속 모듈 — 사장 운영상 별 영업 row로 분리 작성하고
    # parent_lead_id로 묶어 통합 PDF 출력하는 패턴.
    REINFORCEMENT_DESIGN = "내진보강설계"
    THIRD_PARTY_REVIEW = "3자검토"
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
    # 내진성능평가 (PR-Q8) — ① 현장조사 외업/내업, ② 해석 인.일 (3 필드 분리)
    # None + has_structural_drawings 지정 시 PR-Q8b 보간 자동 채움.
    # 해석 인.일은 보간 base × 4계수(방법별·경년·구조형식·용도)인데 4계수가 매
    # 견적마다 다르므로 사용자가 xlsx 보고 수동 입력 권장.
    field_outdoor_days: float | None = Field(default=None, ge=0)
    field_indoor_days: float | None = Field(default=None, ge=0)
    analysis_days: float | None = Field(default=None, ge=0)
    # 내진성능평가 보간용 — 구조도면 보유 여부 (xlsx F44). True=도면有, False=도면無.
    # field_outdoor/indoor_days 미입력 + area 있으면 자동 보간 트리거.
    has_structural_drawings: bool | None = Field(default=None)
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


def _calculate_struct_review(inp: QuoteInput) -> QuoteResult:
    """구조검토용역견적서 산출.

    산식은 구조설계와 동일하나 인.일 자동 산출 흐름은 사용 안 함 — 사용자가
    manhours_override(인.일)를 직접 입력하는 모델. 미입력(None)이면 0으로
    처리해 자동 산출 트리거를 차단한다.
    """
    if inp.manhours_override is None:
        # manhours_override를 0으로 강제 → struct_design 자동 산출 분기 안 탐.
        # type_rate/structure_rate/coefficient도 산출에 영향 없음 (mh가 직접 0).
        return _calculate_struct_design(
            inp.model_copy(update={"manhours_override": 0})
        )
    return _calculate_struct_design(inp)


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


# 내진성능평가 면적·도면 유무 보간 table (PR-Q8b).
# xlsx V48:AC56 영역 그대로 — 사장 운영 양식의 표준 인.일 기준.
# 컬럼: (연면적, 도면有_외업, 도면有_내업, 도면無_외업, 도면無_내업, 해석base)
_SEISMIC_AREA_TABLE: list[tuple[int, int, int, int, int, int]] = [
    (200,    4,  2,   8,  4,   7),
    (500,    5,  3,  10,  6,   9),
    (1000,   7,  4,  14,  8,  11),
    (3000,   9,  5,  18, 10,  15),
    (5000,  11,  6,  22, 12,  18),
    (10000, 12,  6,  24, 12,  20),
    (30000, 21,  8,  42, 16,  28),
    (50000, 29, 10,  58, 20,  35),
    (100000,50, 15, 100, 30,  53),
]


def interpolate_seismic_manhours(
    area_m2: float, *, has_drawings: bool
) -> tuple[float, float, float]:
    """xlsx V47~AC59 면적·도면 유무 보간 → (외업, 내업, 해석base) 인.일 (PR-Q8b).

    선형 보간 — area가 table 두 행 사이에 있으면 비례 계산. table 범위 밖
    (200 미만, 100,000 초과)은 끝 값으로 cap (사용자가 수동 override 권장).

    해석 base는 4계수(방법별·경년·구조형식·용도) 곱하기 전 값. 실제 사장이
    적용하는 해석 인.일은 base × 계수곱이라 사용자가 xlsx 보고 직접 곱해 입력
    하는 모델 (4계수가 매 견적마다 다름).

    검증: area=6602.3, has_drawings=False (xlsx F44='무')
        ratio = (6602.3 - 5000) / 5000 = 0.32046
        외업 = 22 + (24 - 22) × 0.32046 = 22.64092  ← xlsx AA58
        내업 = 12 + (12 - 12) × 0.32046 = 12        ← xlsx AB58
        해석 = 18 + (20 - 18) × 0.32046 = 18.64092  ← xlsx AC58
    """
    table = _SEISMIC_AREA_TABLE
    # 범위 밖 cap
    if area_m2 <= table[0][0]:
        row = table[0]
        outdoor = row[1] if has_drawings else row[3]
        indoor = row[2] if has_drawings else row[4]
        return (float(outdoor), float(indoor), float(row[5]))
    if area_m2 >= table[-1][0]:
        row = table[-1]
        outdoor = row[1] if has_drawings else row[3]
        indoor = row[2] if has_drawings else row[4]
        return (float(outdoor), float(indoor), float(row[5]))

    # 선형 보간
    for i in range(len(table) - 1):
        lo, hi = table[i], table[i + 1]
        if lo[0] <= area_m2 <= hi[0]:
            ratio = (area_m2 - lo[0]) / (hi[0] - lo[0])
            yes_out = lo[1] + (hi[1] - lo[1]) * ratio
            yes_in = lo[2] + (hi[2] - lo[2]) * ratio
            no_out = lo[3] + (hi[3] - lo[3]) * ratio
            no_in = lo[4] + (hi[4] - lo[4]) * ratio
            analysis_base = lo[5] + (hi[5] - lo[5]) * ratio
            outdoor = yes_out if has_drawings else no_out
            indoor = yes_in if has_drawings else no_in
            return (outdoor, indoor, analysis_base)

    # 도달 불가 (위 if/loop가 모든 케이스 커버) — 안전 fallback
    row = table[-1]
    outdoor = float(row[1] if has_drawings else row[3])
    indoor = float(row[2] if has_drawings else row[4])
    return (outdoor, indoor, float(row[5]))


def _calculate_reinforcement_design(inp: QuoteInput) -> QuoteResult:
    """내진보강설계 strategy.

    사용자가 4 모듈(내진성능평가/내진보강설계/3자검토/구조감리) 중 일부를
    별 영업으로 분리 작성하는 패턴. parent_lead_id로 묶어 통합 PDF 출력 (PR-G1).

    산출은 단순 — 단일 인.일 × 단가 → overhead × 110% → tech × 20% → 합산
    → 조정 → 절삭. xlsx L81~L84 검증:
        mh=9, rate=242,055
        direct = 9 × 242,055 = 2,178,495   # L81
        oh     = 2,178,495 × 1.1 = 2,396,344.5  # L82
        tech   = (2,178,495+2,396,344.5) × 0.2 = 914,967.9  # L83
        subtotal = 5,489,807.4              # L84
    """
    mh_total = (
        int(inp.manhours_override) if inp.manhours_override is not None else 0
    )
    direct_labor = mh_total * DAILY_RATE_REINFORCEMENT

    if inp.direct_expense_items:
        direct_expense = sum(item.amount for item in inp.direct_expense_items)
    else:
        direct_expense = (
            inp.printing_fee + inp.survey_fee + 25_000 * inp.transport_persons
        )

    overhead = direct_labor * (inp.overhead_pct / 100)
    tech_fee = (direct_labor + overhead) * (inp.tech_fee_pct / 100)
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


def _calculate_third_party_review(inp: QuoteInput) -> QuoteResult:
    """내진보강설계 검증(3자검토) strategy.

    내진보강설계와 동일 흐름 — 단가만 292,249원/일로 상이. xlsx L85~L88 검증:
        mh=6, rate=292,249
        direct = 6 × 292,249 = 1,753,494   # L85
        oh     = 1,753,494 × 1.1 = 1,928,843.4  # L86
        tech   = (1,753,494+1,928,843.4) × 0.2 = 736,467.48  # L87
        subtotal = 4,418,804.88              # L88
    """
    mh_total = (
        int(inp.manhours_override) if inp.manhours_override is not None else 0
    )
    direct_labor = mh_total * DAILY_RATE_THIRD_PARTY

    if inp.direct_expense_items:
        direct_expense = sum(item.amount for item in inp.direct_expense_items)
    else:
        direct_expense = (
            inp.printing_fee + inp.survey_fee + 25_000 * inp.transport_persons
        )

    overhead = direct_labor * (inp.overhead_pct / 100)
    tech_fee = (direct_labor + overhead) * (inp.tech_fee_pct / 100)
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


def _calculate_seismic_eval(inp: QuoteInput) -> QuoteResult:
    """내진성능평가 strategy (PR-Q8).

    xlsx 산출 흐름은 두 섹션 합산:

    ① 현장조사 (외업/내업 인.일 분리)
       direct_labor = (외업 + 내업) × 300,980 (기술자 단가)
       lodging      = 30,000 × 외업                  (현장체제비, L50)
       machinery    = direct_labor × 10%             (기계기구 손료, L51)
       other        = direct_labor × 10%             (기타 현장경비, L52)
       overhead     = direct_labor × overhead_pct/100 (L53, default 110%)
       tech_fee     = (direct_labor + overhead) × tech_fee_pct/100 (L54, 20%)
       subtotal_1   = ① 모든 항목 합                 (L55)

    ② 내진성능평가 (해석 인.일 단일)
       direct_labor_2 = 해석인일 × 300,980           (L56)
       overhead_2     = direct_labor_2 × 110%        (L57)
       tech_fee_2     = (direct_labor_2 + overhead_2) × 20% (L58)
       subtotal_2     = ② 합                         (L59)

    ③ 합산·조정·절삭
       total          = subtotal_1 + subtotal_2 + direct_expense (L60)
       adjusted       = total × adjustment_pct/100   (L61, default 45%)
       truncated      = adjusted % truncate_unit     (L62, default 백만)
       final          = adjusted - truncated         (L63)

    인.일 자동 산출(연면적·구조도면 유무·해석방법·등급 보간 — xlsx V47~AC59)은
    table 너무 복잡해 backend에 옮기지 않음. 사용자가 xlsx 보고 수동 입력
    (field_outdoor_days/field_indoor_days/analysis_days 신규 필드).

    xlsx 검증 (외업 22.64092, 내업 12, 해석 67.667, adj=0.45, 백만 절삭):
    - field_direct  = 34.64092 × 300,980 = 10,426,224.10  # L48
    - lodging       = 30,000 × 22.64092  =    679,227.6   # L50
    - machinery     = 10,426,224.10×0.1  =  1,042,622.41  # L51
    - other         = 10,426,224.10×0.1  =  1,042,622.41  # L52
    - field_oh      = 10,426,224.10×1.1  = 11,468,846.51  # L53
    - field_tech    = 21,895,070.61×0.2  =  4,379,014.12  # L54
    - subtotal_1   = 29,038,557.16                        # L55
    - analysis_d    = 67.667 × 300,980    = 20,366,413.66  # L56
    - analysis_oh   = 22,403,055.03                       # L57
    - analysis_tech = 8,553,893.74                        # L58
    - subtotal_2   = 51,323,362.42                        # L59
    - total         = 80,361,919.58                        # L60
    - adjusted      = 36,162,863.81                        # L61
    - final         = 36,000,000                           # L63 ≈ xlsx 35,999,999.81
    """
    # PR-Q8b — 외업/내업/해석 인.일이 None이고 has_structural_drawings + 면적이
    # 있으면 xlsx V47~AC59 보간 table로 자동 산출. 사용자 수동 입력은 그대로 우선.
    field_outdoor = inp.field_outdoor_days
    field_indoor = inp.field_indoor_days
    analysis = inp.analysis_days
    if (
        inp.has_structural_drawings is not None
        and inp.gross_floor_area
        and (field_outdoor is None or field_indoor is None or analysis is None)
    ):
        auto_out, auto_in, auto_analysis_base = interpolate_seismic_manhours(
            inp.gross_floor_area,
            has_drawings=inp.has_structural_drawings,
        )
        if field_outdoor is None:
            field_outdoor = auto_out
        if field_indoor is None:
            field_indoor = auto_in
        # 해석 base는 4계수(방법별·경년·구조형식·용도) 곱하기 전 값. 사용자가
        # 수동 입력 안 했으면 base 그대로 사용 — 정확하지 않을 수 있어 결과 패널
        # 확인 필수.
        if analysis is None:
            analysis = auto_analysis_base

    field_outdoor = field_outdoor or 0
    field_indoor = field_indoor or 0
    analysis = analysis or 0
    rate = DAILY_RATE_ENGINEER  # 300,980 — 기술자

    # ① 현장조사
    field_direct = (field_outdoor + field_indoor) * rate
    lodging = 30_000 * field_outdoor
    machinery = field_direct * 0.1
    other_expense = field_direct * 0.1
    field_overhead = field_direct * (inp.overhead_pct / 100)
    field_tech = (field_direct + field_overhead) * (inp.tech_fee_pct / 100)
    field_subtotal = (
        field_direct + lodging + machinery + other_expense + field_overhead + field_tech
    )

    # ② 내진성능평가
    analysis_direct = analysis * rate
    analysis_overhead = analysis_direct * (inp.overhead_pct / 100)
    analysis_tech = (analysis_direct + analysis_overhead) * (inp.tech_fee_pct / 100)
    analysis_subtotal = analysis_direct + analysis_overhead + analysis_tech

    # ③ 추가 직접경비 (사용자 입력) → 합산·조정·절삭
    if inp.direct_expense_items:
        direct_expense = sum(item.amount for item in inp.direct_expense_items)
    else:
        direct_expense = (
            inp.printing_fee + inp.survey_fee + 25_000 * inp.transport_persons
        )

    total = field_subtotal + analysis_subtotal + direct_expense
    adjusted = total * (inp.adjustment_pct / 100)

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

    # QuoteResult는 단일 direct_labor/overhead/tech 슬롯 — 두 섹션 합산해 표시
    mh_total = int(round(field_outdoor + field_indoor + analysis))
    per_pyeong_area = inp.gross_floor_area / 3.3 if inp.gross_floor_area else 0
    per_pyeong = final_amount / per_pyeong_area if per_pyeong_area else 0

    return QuoteResult(
        manhours_baseline=0,
        manhours_baseline_rounded=0,
        manhours_total=mh_total,
        direct_labor=field_direct + analysis_direct,
        # 직접경비는 (체제비 + 기계 + 기타 + 사용자 입력)을 합산 — PDF 표는 단일
        # ②행에 표시되므로 모두 묶음. 추후 PDF 분기 필요.
        direct_expense=lodging + machinery + other_expense + direct_expense,
        overhead=field_overhead + analysis_overhead,
        tech_fee=field_tech + analysis_tech,
        subtotal=field_subtotal + analysis_subtotal,
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
    QuoteType.STRUCT_REVIEW: _calculate_struct_review,  # 인.일 직접 입력
    QuoteType.PERF_SEISMIC: _calculate_struct_design,   # 구조설계와 산식 동일
    QuoteType.INSPECTION_REGULAR: _calculate_inspection_legal,  # PR-Q5
    QuoteType.INSPECTION_DETAIL: _calculate_inspection_legal,   # PR-Q5
    QuoteType.INSPECTION_DIAGNOSIS: _calculate_inspection_legal,  # PR-Q6
    QuoteType.INSPECTION_BMA: _calculate_inspection_bma,  # PR-Q4
    QuoteType.SEISMIC_EVAL: _calculate_seismic_eval,  # PR-Q8
    QuoteType.REINFORCEMENT_DESIGN: _calculate_reinforcement_design,
    QuoteType.THIRD_PARTY_REVIEW: _calculate_third_party_review,
    QuoteType.SUPERVISION: _calculate_supervision,  # PR-Q3
    QuoteType.FIELD_SUPPORT: _calculate_field_support,  # PR-Q2
    QuoteType.CUSTOM: _calculate_struct_design,
}
