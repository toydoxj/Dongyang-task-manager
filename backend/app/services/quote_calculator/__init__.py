"""구조설계 견적서 산출 엔진.

사장이 운영하던 xlsx 견적서 양식(`docs/설계견적*.xlsx`)의 IF·ROUND·RIGHT
공식을 그대로 파이썬으로 재현. 셀 dump로 검증된 식 (5192m²·요율 1·1.2·0.5
입력 → 25,000,000원 출력)을 fixture로 단위 테스트.

단가 정책 (사용자 명시 2026-05-08): 구조감리는 기술사, 나머지는 고급기술자
기준 — 모두 건설분야. ENGINEERING_RATES_BY_GRADE dict가 단가의 단일 소스.
strategy docstring 검증값은 xlsx 사본의 옛 단가(예: 내진평가 300,980, 보강
설계 242,055) 기반이라 신 단가 적용 후 결과 다를 수 있음. xlsx 옛 사례 vs
현재 산출이 다른 것은 정상.

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

# 직접인건비 단가 — 한국엔지니어링협회 통계법 제27조 기반 기술자 노임단가
# (1인 1일 기준, 원). 매년 1월 갱신 — 운영 시점에 ENGINEERING_RATES_BY_GRADE
# dict 한 곳만 수정하면 모든 strategy에 반영. 사장 운영 분야는 건설.
ENGINEERING_RATES_BY_GRADE: dict[str, int] = {
    # 등급(한글) → 건설분야 단가 (2026 기준 표)
    "기술사": 467_217,
    "특급기술자": 373_353,
    "고급기술자": 310_884,
    "중급기술자": 295_138,
    "초급기술자": 235_459,
    "고급숙련기술자": 281_075,
    "중급숙련기술자": 250_087,
    "초급숙련기술자": 218_142,
}

# 종류별 default 등급 — 사용자가 quote_form에서 미선택(None)이면 적용.
# 사용자 명시: 구조감리=기술사, 3자검토·BMA책임자=특급기술자, BMA점검자=초급기술자,
# 그 외 = 고급기술자 (모두 건설분야).
DAILY_RATE_SENIOR_ENGINEER = ENGINEERING_RATES_BY_GRADE["고급기술자"]      # 310,884
DAILY_RATE_PROFESSIONAL_ENGINEER = ENGINEERING_RATES_BY_GRADE["기술사"]   # 467,217
DAILY_RATE_BMA_RESPONSIBLE = ENGINEERING_RATES_BY_GRADE["특급기술자"]    # 373,353
DAILY_RATE_JUNIOR_ENGINEER = ENGINEERING_RATES_BY_GRADE["초급기술자"]    # 235,459


def _resolve_rate(grade: str | None, default_grade: str) -> int:
    """등급명 → 단가. 빈 값/미지원 등급은 default_grade로 fallback.

    사용자가 등급을 명시 선택하면 그 단가 사용 — 매년 표 갱신 시 dict만
    업데이트하면 모든 strategy에 자동 반영.
    """
    if grade and grade in ENGINEERING_RATES_BY_GRADE:
        return ENGINEERING_RATES_BY_GRADE[grade]
    return ENGINEERING_RATES_BY_GRADE[default_grade]


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


class SpecialNoteItem(BaseModel):
    """용역범위 list 항목 — 라벨(포함/제외/일반) + 텍스트.

    PDF에 [포함] / [제외] 태그 + 텍스트로 표시. type='plain'이면 태그 없음.
    """

    model_config = ConfigDict(populate_by_name=True)
    type: str = "plain"  # "include" | "exclude" | "plain"
    text: str = ""


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
    # 영업 정보와 동기화 — True(default): 영업정보 탭의 규모·층수·위치·용역명을
    # 견적 form에 echo (input disabled). False: 견적별 자체 입력 (영업정보 변경에
    # 영향 X). 영업 1건에 견적 종류·대상 건축물이 다른 케이스 대응
    # (예: 신축 구조설계 5,000㎡ + 기존건물 정밀안전진단 2,000㎡).
    sync_with_sale: bool = True
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
    # 직접인건비 단가 등급 — None이면 strategy별 default (구조감리=기술사,
    # 3자검토=특급기술자, 그 외=고급기술자). 사용자가 ENGINEERING_RATES_BY_GRADE
    # 키 중 하나로 override 가능.
    engineer_grade: str | None = None
    # 점검류 (PR-Q4~Q7) — 책임자/점검자 인.일 분리 입력 (수동 입력 fallback)
    inspection_responsible_days: float | None = Field(default=None, ge=0)
    inspection_inspector_days: float | None = Field(default=None, ge=0)
    # BMA 책임자/점검자 등급 — None이면 default (책임자=특급, 점검자=초급)
    bma_responsible_grade: str | None = None
    bma_inspector_grade: str | None = None
    # 건축물관리법점검 자동 산정 (PR-Q4b) — 산정표 기반.
    # 입력하면 별표 1 보간 + 별표 3 보정 + 제37조 군집 + 제38조 추가 보정 자동.
    # 미입력 시 inspection_responsible_days/inspector_days 수동 흐름 fallback.
    bma_inspection_type: str = ""        # "정기" | "정기+구조" (그 외 수동)
    bma_skip_structural: bool = False    # 제38조② 구조안전 생략 (× 0.8)
    bma_skip_utility: bool = False       # 제38조③ 급수·배수·냉난방·환기 생략 (× 0.9)
    bma_optional_task_amount: float = Field(default=0, ge=0)  # 선택과업비 (마감재 해체)
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
    # 시특법 점검 자동 산정 (PR-Q5b) — 정기/정밀점검/정밀안전진단
    # 별표 22 base 인.일 보간 + 별표 23 조정비 + 제62조 보정 자동 적용.
    # 빈 값이면 자동 산정 skip하고 manhours_override 흐름 사용 (backward 호환).
    # structure_form은 line 120의 메타 필드를 그대로 사용 — STRUCTURE_FACTORS 키
    # ("철근콘크리트"/"철골조" 등) 중 하나면 자동 산정 트리거.
    building_usage: str = ""               # 별표 23(2): 업무용/상업용/주거용/특수용/경기장 등
    # 준공년도 — 입력하면 backend가 (산정 시점 - completion_year)로 경과년수 자동 계산.
    # aging_years는 직접 입력 호환 유지 (legacy + 수동 override). 우선순위: completion_year > aging_years.
    completion_year: int | None = Field(default=None, ge=1900, le=2100)
    aging_years: int | None = Field(default=None, ge=0)
    complexity: str = ""                   # 단순/보통/복잡
    prev_report: str = ""                  # 미제공/CAD/보고서+CAD
    facility_type: str = ""                # 기본/인접/군집(소)/군집(대)/혼합
    sub_facility_areas: list[float] = []   # 인접·군집 부속 면적
    # 직접경비 단가 (사용자 입력) — 시특법 점검 자동 산정용
    # 시특법 자동 산정 단가 — 별표 25 권장값 default. 사용자가 입력 X면 default 적용.
    travel_unit_cost: float = Field(default=50_000, ge=0)    # 여비 1회 왕복 (1인)
    helper_daily_wage: float = Field(default=180_000, ge=0)  # 시중 특별인부 일당
    vehicle_daily_cost: float = Field(default=30_000, ge=0)  # 차량 일일 손료
    fuel_unit_price: float = Field(default=1_800, ge=0)      # 휘발유 ℓ당
    print_unit_cost: float = Field(default=5_000, ge=0)      # 인쇄비 책당
    print_copies: int = Field(default=3, ge=0)               # 인쇄 부수
    risk_pct: float = Field(default=10, ge=0, le=100)        # 위험수당 % (10~20)
    machine_pct: float = Field(default=0, ge=0, le=100)      # 기계기구 손료 %
    # 기계기구 default는 frontend에서 quote_type 분기 (정기 0 / 정밀 5 / 진단 10).
    # backend는 입력값 그대로 사용 — 사용자 override 가능.
    # 별표 26 선택과업 (PR-Q5b — 시특법 점검 자동 산정 시) ─────
    # A. 실측도면 작성 (별표 26-1) — 본 견적 adjusted × pct
    opt_field_drawings: bool = False
    opt_field_drawings_scope: str = "기본"            # "기본"(10%) | "상세"(20%)
    # B. 구조해석 (별표 26-10-(3)) — 면적·구조형식별 인 × 단가
    opt_structural_analysis: bool = False
    opt_analysis_struct_type: str = "RC계"          # "RC계" | "PC조" | "특수구조"
    opt_analysis_count: int = Field(default=1, ge=1)  # 개소 수
    # C. 내진성 평가 (별표 26-15) — 구조해석 인 × 배수 × 단가
    # 배수: 간략(등가정적·모드스펙) 2.0 / 정밀(시간이력·비선형·P-δ) 2.5~3.0
    # frontend 슬라이더가 method 라디오와 결합되어 multiplier 단일 값 전송.
    opt_seismic_eval: bool = False
    opt_seismic_multiplier: float = Field(default=2.0, ge=2.0, le=3.0)
    # 그 외 (별표 26-6/7/11/12/13/16) — 자유 입력 항목
    opt_other_items: list[DirectExpenseItem] = []
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
    payment_terms: str = ""    # 지불방법
    # 용역범위 — 신 모델: list[SpecialNoteItem]. legacy 호환 위해 special_notes
    # textarea도 보존 (items 비어 있으면 라인별 split).
    special_notes_items: list[SpecialNoteItem] = []
    special_notes: str = ""    # legacy — 라인별 [포함]/[제외] 끝맺음 자유 입력
    quote_note: str = ""       # 견적 비고 — 사용자 자유 입력 (모달·PDF 표시)
    # ── legacy (기존 영업 호환) ──
    # 기존 quote_form_data가 이 필드들을 갖고 있을 수 있음. direct_expense_items가
    # 비었을 때만 합산해서 사용.
    printing_fee: float = Field(default=0, ge=0)
    survey_fee: float = Field(default=0, ge=0)
    transport_persons: int = Field(default=0, ge=0)


class OptionalTaskBreakdown(BaseModel):
    """별표 26 추가과업 항목별 산정 내역 — PDF 별도 페이지 표시용."""

    model_config = ConfigDict(populate_by_name=True)

    label: str = ""           # "실측도면(상세 20%)" / "구조해석(RC계 1개소)" 등
    persons: float = 0.0      # 인원수 (실측도면·자유입력은 0)
    unit_rate: float = 0.0    # 단가 (인원 × 단가 산정 시), 실측도면은 0
    base_pct: float = 0.0     # 비율 (실측도면용, 0.10 또는 0.20)
    base_amount: float = 0.0  # 기준 금액 (실측도면 base = subtotal_base)
    amount: float = 0.0       # 최종 금액 (direct_expense에 합산된 값)
    note: str = ""            # 산식 설명 ("subtotal × 20%" / "11인 × 310,884원")


class ManhourFormulaStep(BaseModel):
    """기본과업 인.일 산식 단계별 항목 — PDF 표시용 (별표 22 + 보정 누적)."""

    model_config = ConfigDict(populate_by_name=True)

    label: str = ""        # "별표 22 base" / "구조형식 보정 (별표 23-1)" 등
    operator: str = ""     # "" / "×" / "+" (누적 연산)
    value: float = 0.0     # 단계 값
    note: str = ""         # "30,000㎡ 정밀안전진단" / "철근콘크리트" 등


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
    # 별표 25 직접경비 항목별 분해 — 시특법 자동 산정 시에만 채워짐.
    # 1페이지 산출 근거 column에 "산정 상세 내역 참조" 표시 + 2페이지 분해 표.
    direct_expense_breakdown: list[OptionalTaskBreakdown] = []
    # 별표 26 추가과업 분해 — 시특법 자동 산정 시에만 채워짐.
    # PDF 별도 산정 페이지 + 산정 결과 패널 hover 표시용.
    optional_tasks: list[OptionalTaskBreakdown] = []
    # 기본과업 인.일 산식 단계별 — 시특법 자동 산정 시 PDF 2페이지 표시용.
    # 별표 22 base → 별표 23 보정 → 제62조 보정 → 추가과업 합산 → 전체 인.일.
    manhours_formula: list[ManhourFormulaStep] = []
    # 시특법 자동 산정 외업/내업 인.일 (별표 22 기준 × 보정 계수). 0이면 미적용.
    manhours_outdoor: float = 0.0
    manhours_indoor: float = 0.0


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


# PR-DE: _calculate_struct_design + _calculate_struct_review는 strategies/struct.py로 이동.
# _DISPATCH 정의 직전에 import 한다 (아래 # ── 종류별 산출 strategy dispatch ── 섹션).


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
    # 단가 — 사용자 선택 등급 우선, 없으면 default(고급기술자).
    direct_labor = mh_total * _resolve_rate(inp.engineer_grade, "고급기술자")

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

    # 구조감리 default = 기술사. 사용자 선택 등급 우선.
    direct_labor = mh_total * _resolve_rate(inp.engineer_grade, "기술사")

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
    # default = 고급기술자. 사용자 선택 등급 우선.
    direct_labor = mh_total * _resolve_rate(inp.engineer_grade, "고급기술자")

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

    내진보강설계와 동일 흐름이나 단가는 특급기술자(건설) 373,353원/일 (사용자 명시).
    xlsx 옛 사례(L85~L88, 단가 292,249)와 결과 다를 수 있음.
    """
    mh_total = (
        int(inp.manhours_override) if inp.manhours_override is not None else 0
    )
    # 3자검토 default = 특급기술자. 사용자 선택 등급 우선.
    direct_labor = mh_total * _resolve_rate(inp.engineer_grade, "특급기술자")

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
    # default = 고급기술자. 사용자 선택 등급 우선.
    rate = _resolve_rate(inp.engineer_grade, "고급기술자")

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
# PR-DE: 구조설계 / 구조검토는 strategies/struct.py로 분리. 본 시점에 helper
# 들이 모두 정의됐으므로 partial loading 충돌 없음.
# PR-DF: 건축물관리법점검 / 시특법(정기·정밀·진단)도 strategies/inspection.py 분리.
from app.services.quote_calculator.strategies.struct import (  # noqa: E402
    _calculate_struct_design,
    _calculate_struct_review,
)
from app.services.quote_calculator.strategies.inspection import (  # noqa: E402
    _calculate_inspection_bma,
    _calculate_inspection_legal,
)

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
