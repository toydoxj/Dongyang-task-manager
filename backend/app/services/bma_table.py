"""건축물관리법 정기/긴급점검 인.일 보간 + 별표 3 조정비 lookup.

출처: 건축물관리점검지침 (국토교통부고시 제2024-579호, 2025.1.1)
근거: 사장 운영 산정표 `건축물 정기점검 대가 산정표.xlsx` (별표 1·2·3 transcribe)

산식 흐름 (산정표 B25)
- 직접인건비 = 책임자×기술사단가 + 점검자×초급기술자단가
- 제경비 = 직접인건비 × 1.10 (제34조)
- 기술료 = (직접인건비+제경비) × 0.20 (제35조)
- 직접경비 = 100,000원 일괄 (제36조)
- 소계 = 직접인건비+제경비+기술료+직접경비
- 업무대가 = 소계 × 경과년수조정 × 용도조정 × 추가조정 + 선택과업비

PR-Q4b — 시특법(PR-Q5b) inspection_legal_table 패턴 재사용.
"""
from __future__ import annotations

from typing import Literal


# ── 별표 1: 정기점검·긴급점검 기준인원수 (인.일) ──────────
# 산정표 시트 1 F20/F21 산식 transcribe (선형 보간).
#
# 점검책임자:
#   ≤10,000㎡ → 1
#   10,000 < x ≤ 30,000 → 1 + (x-10,000)/20,000  (10,000=1, 30,000=2)
#   > 30,000 → 2
#   정기+구조 모드: 위 결과 + 1 (제33조②)
#
# 점검자:
#   ≤3,000 → 0  (3,000㎡ 미만은 3,000㎡ 적용 = 0)
#   3,000 < x ≤ 5,000  → 0 + (x-3,000)/2,000   (5,000=1)
#   5,000 < x ≤ 10,000 → 1 + (x-5,000)/5,000   (10,000=2)
#   10,000 < x ≤ 30,000 → 2 + (x-10,000)/20,000 (30,000=3)
#   30,000 < x ≤ 100,000 → 3 + (x-30,000)/70,000 (100,000=4)
#   > 100,000 → 4 + (x-100,000)/70,000  (extrapolation)


def interpolate_responsible_persons(area_m2: float, structural_extra: bool) -> float:
    """점검책임자 인.일 — 산정표 F20 산식.

    structural_extra=True면 정기+구조안전 추가 모드 (제33조②, +1 가산).
    """
    if area_m2 <= 10_000:
        base = 1.0
    elif area_m2 <= 30_000:
        base = 1.0 + (area_m2 - 10_000) / 20_000
    else:
        base = 2.0
    return base + (1.0 if structural_extra else 0.0)


def interpolate_inspector_persons(area_m2: float) -> float:
    """점검자 인.일 — 산정표 F21 산식 (선형 보간)."""
    if area_m2 <= 3_000:
        return 0.0
    if area_m2 <= 5_000:
        return (area_m2 - 3_000) / 2_000
    if area_m2 <= 10_000:
        return 1.0 + (area_m2 - 5_000) / 5_000
    if area_m2 <= 30_000:
        return 2.0 + (area_m2 - 10_000) / 20_000
    if area_m2 <= 100_000:
        return 3.0 + (area_m2 - 30_000) / 70_000
    # >100,000 — extrapolation
    return 4.0 + (area_m2 - 100_000) / 70_000


# ── 별표 3-(1): 경과년수 조정비 ─────────────────────────────
def bma_aging_factor(years: int) -> float:
    """경과년수 보정비 — 7단계 (사용승인 후 경과년수)."""
    if years <= 5:
        return 1.00
    if years <= 10:
        return 1.05
    if years <= 15:
        return 1.10
    if years <= 25:
        return 1.15
    if years <= 35:
        return 1.20
    if years <= 55:
        return 1.25
    return 1.30


# ── 별표 3-(2): 용도별 조정비 ─────────────────────────────
# 산정표 sheet 1의 M7~N20 + 지침 별표 3 본문 일치.
# 시특법 USAGE_FACTORS와 키 다름 — 별도 dict.
BMA_USAGE_FACTORS: dict[str, float] = {
    "근린생활시설": 1.00,
    "공동주택": 1.10,
    "판매시설": 1.10,
    "장례식장": 1.10,
    "교육연구시설": 1.10,
    "노유자시설": 1.20,
    "위락시설": 1.20,
    "관광휴게시설": 1.30,
    "문화및집회시설": 1.40,
    "운수시설": 1.40,
    "의료시설": 1.40,
    "도서관": 1.40,
    "운동시설": 1.40,
    "관광숙박시설": 1.40,
}


# ── 제37조: 군집건축물 (별표 2) ────────────────────────────
# 시특법 제61조와 동일 패턴 — sub_facility_areas 합산 처리.
# 1. 모두 1,000㎡ 미만 → 합계 면적의 base × 1.0
# 2. 모두 1,000㎡ 이상 → 최대 면적 base × 1.0 + Σ(부속 base × 0.7)
# 3. 혼합 → 최대 면적 base × 1.0 + Σ(부속 base × 0.7)
#
# inspection_legal_table.apply_facility_form()와 동일 시그니처. 견적 form에서
# facility_type/sub_facility_areas 동일 키 재사용 가능. (구현은 호출 시 양쪽 모두
# 같은 결과 — 시특법 helper 호출하거나 별도 helper 작성. 여기선 별도 정의.)


FacilityType = Literal["기본", "인접", "군집(소)", "군집(대)", "혼합"]


def apply_bma_facility_form(
    base_main: float,
    facility_type: FacilityType,
    sub_areas: list[float],
    base_lookup,
) -> float:
    """제37조 군집건축물 인.일 합산.

    base_lookup(area) → 면적별 base 인.일 (책임자 또는 점검자 단위로 호출).
    """
    if facility_type == "기본" or not sub_areas:
        return base_main
    if facility_type == "군집(소)":
        # 모두 1,000㎡ 미만 → 합계 면적의 base × 1.0
        total_area = sum(sub_areas)
        return base_lookup(total_area)
    # 인접 / 군집(대) / 혼합 — main + 부속 0.7
    sub_sum = sum(base_lookup(a) * 0.7 for a in sub_areas)
    return base_main + sub_sum


# ── 제38조 추가 보정 ────────────────────────────────────
# ② 구조안전 점검 생략 → × 0.8
# ③ 급수/배수/냉난방/환기 생략 → × 0.9
# 두 보정은 곱셈 누적 (둘 다 적용 시 × 0.72).


# 노임단가 default — xlsx 운영 표준
RESPONSIBLE_RATE_DEFAULT = 456_237   # 기술사 (특급기술자)
INSPECTOR_RATE_DEFAULT = 235_459     # 초급기술자
DIRECT_EXPENSE_FIXED = 100_000       # 제36조 직접경비 일괄
