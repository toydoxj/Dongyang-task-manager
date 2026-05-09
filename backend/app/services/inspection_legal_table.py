"""시특법 점검(정기/정밀/정밀안전진단) base 인.일 + 보정 계수 lookup.

출처: 시설물의 안전 및 유지관리 실시 등에 관한 지침
      (국토교통부고시 제2022-539호, 2022.9.28)
적용 범위: **건축물** (콘크리트구조, 상업용 기준)
단위: 인·일 (고급기술자, 한국엔지니어링협회 통계법 건설부분 노임단가)

본 모듈은 사장 운영 견적서의 시특법 sheet 산식을 backend로 transcribe.
산식 명세는 docs/quote_formulas/inspection_legal_spec.md 참조.
"""
from __future__ import annotations

from typing import Literal

# ── 별표 22: base 인.일 (건축물, 콘크리트구조, 상업용) ─────────────
# (면적, 정밀안전진단 전체, 정밀안전진단 외업,
#         정밀점검 전체, 정밀점검 외업,
#         정기점검 전체, 정기점검 외업)
# None = 해당 면적·종류 적용 X (예: 5,000㎡ 미만은 정밀점검·진단 적용 X)
_BLDG_BASE_TABLE: list[
    tuple[int, int | None, int | None, int | None, int | None, int, int]
] = [
    (500,    None, None, None, None, 3, 2),
    (1_000,  None, None, None, None, 3, 2),
    (3_000,  None, None, None, None, 4, 2),
    (5_000,   85,  26,   17,  11,    5, 3),
    (10_000,  93,  31,   18,  12,    6, 4),
    (30_000, 148,  66,   29,  21,   10, 7),
    (50_000, 205, 102,   39,  29,   14, 9),
    (100_000, 347, 193,  65,  50,   24, 15),
]

InspectionType = Literal["정기점검", "정밀점검", "정밀안전진단"]


def _column_idx(itype: InspectionType, outdoor: bool) -> int:
    """별표 22 컬럼 index — _BLDG_BASE_TABLE row 안 위치."""
    base = {"정밀안전진단": 1, "정밀점검": 3, "정기점검": 5}[itype]
    return base + (1 if outdoor else 0)


def interpolate_base(
    area_m2: float, inspection_type: InspectionType
) -> tuple[float, float] | None:
    """별표 24 선형 보간 — (전체, 외업) 인.일 반환.

    면적 범위:
      - 표 최소(500㎡) 미만: 첫 행 그대로 (외삽 X)
      - 표 최대(100,000㎡) 초과: 마지막 행 그대로
      - 사이: 인접 두 행 선형 보간

    적용 안 되는 종류 (예: 5,000㎡ 미만 정밀점검) — None 반환.
    """
    table = _BLDG_BASE_TABLE
    col_total = _column_idx(inspection_type, False)
    col_out = _column_idx(inspection_type, True)

    # 적용 가능한 row만 (해당 종류 컬럼이 None 아님)
    valid = [r for r in table if r[col_total] is not None]
    if not valid:
        return None

    # 범위 밖 cap
    if area_m2 <= valid[0][0]:
        return float(valid[0][col_total]), float(valid[0][col_out])
    if area_m2 >= valid[-1][0]:
        return float(valid[-1][col_total]), float(valid[-1][col_out])

    # 선형 보간
    for i in range(len(valid) - 1):
        lo, hi = valid[i], valid[i + 1]
        if lo[0] <= area_m2 <= hi[0]:
            ratio = (area_m2 - lo[0]) / (hi[0] - lo[0])
            total = lo[col_total] + (hi[col_total] - lo[col_total]) * ratio
            out = lo[col_out] + (hi[col_out] - lo[col_out]) * ratio
            return total, out

    return float(valid[-1][col_total]), float(valid[-1][col_out])


# ── 별표 23: 시설물별 조정비 (다. 건축물) ──────────────────
STRUCTURE_FACTORS: dict[str, float] = {
    "철근콘크리트": 1.00,
    "철골철근콘크리트": 1.00,
    "PC조": 1.00,
    "철골조": 0.80,
    "조적조": 0.90,
    "목구조": 1.20,
    "특수구조": 1.30,
}

USAGE_FACTORS: dict[str, float] = {
    "업무용": 1.00,
    "상업용": 1.00,           # 상업용·지하도상가
    "지하도상가": 1.00,
    "주거용": 1.10,
    "특수용": 1.20,
    "경기장": 1.20,
    "체육관": 1.20,
}


# ── 제62조: 보정 계수 ────────────────────────────────────
def aging_factor(years: int) -> float:
    """경과년수 보정비 — 5단계."""
    if years <= 15:
        return 1.00
    if years <= 25:
        return 1.05
    if years <= 35:
        return 1.10
    if years <= 55:
        return 1.15
    return 1.20


Complexity = Literal["단순", "보통", "복잡"]


def complexity_factor(level: Complexity) -> float:
    """구조복잡도 보정 (-15% / 0 / +15%)."""
    return {"단순": 0.85, "보통": 1.00, "복잡": 1.15}[level]


PrevReport = Literal["미제공", "CAD", "보고서+CAD"]


def prev_report_factor(level: PrevReport) -> float:
    """전차보고서 제공 여부 보정비."""
    return {"미제공": 1.00, "CAD": 0.97, "보고서+CAD": 0.95}[level]


# ── 별표 26: 선택과업 — 건축물 ───────────────────────────
# 10-(3) 구조해석 면적·구조형식별 기준인원수 (단위: **인**, 고급기술자, 개소당)
# 별표 22의 "인·일"과 단위 체계 다름 — 그대로 인원 × 단가로 직접인건비.
_BLDG_ANALYSIS_TABLE: list[tuple[int, int, int, int]] = [
    # (면적, RC·벽식·S조·SRC조, PC조·주상복합, 특수구조)
    (5_000,    7, 11, 14),
    (10_000,   8, 12, 16),
    (30_000,  11, 16, 22),
    (50_000,  14, 21, 27),
    (100_000, 21, 32, 42),
]

BuildingAnalysisType = Literal["RC계", "PC조", "특수구조"]


def _analysis_col(btype: BuildingAnalysisType) -> int:
    return {"RC계": 1, "PC조": 2, "특수구조": 3}[btype]


def interpolate_analysis_persons(
    area_m2: float, btype: BuildingAnalysisType
) -> float:
    """별표 26-10-(3) 구조해석 기준인원수 보간 (건축물).

    범위 밖 cap (5,000㎡ 미만은 5,000㎡ 값, 100,000㎡ 초과는 100,000㎡ 값).
    표는 5,000~100,000㎡로 정밀안전진단 적용 범위와 일치.
    """
    table = _BLDG_ANALYSIS_TABLE
    col = _analysis_col(btype)
    if area_m2 <= table[0][0]:
        return float(table[0][col])
    if area_m2 >= table[-1][0]:
        return float(table[-1][col])
    for i in range(len(table) - 1):
        lo, hi = table[i], table[i + 1]
        if lo[0] <= area_m2 <= hi[0]:
            ratio = (area_m2 - lo[0]) / (hi[0] - lo[0])
            return lo[col] + (hi[col] - lo[col]) * ratio
    return float(table[-1][col])


# ── 별표 26-15: 내진성 평가 배수 ─────────────────────────
# 간략(등가정적·모드스펙) 2.0 / 정밀(시간이력·비선형·P-δ) 2.5~3.0.
# 사용자가 frontend 슬라이더로 직접 값 입력 (QuoteInput.opt_seismic_multiplier).


# ── 별표 26-1: 실측도면 작성 비율 ────────────────────────
DrawingScope = Literal["기본", "상세"]


def drawing_pct(scope: DrawingScope) -> float:
    """별표 26-1: 실측도면 작성 비율 (정밀안전진단 대가 대비)."""
    return {"기본": 0.10, "상세": 0.20}[scope]


# ── 제61조: 시설물 형태 가중치 ─────────────────────────────
FacilityType = Literal["기본", "인접", "군집(소)", "군집(대)", "혼합"]


def apply_facility_form(
    base_main: float,
    facility_type: FacilityType,
    sub_areas: list[float],
    base_lookup,
) -> float:
    """시설물 형태에 따른 인.일 합산 (제61조).

    - "기본": main 그대로
    - "인접": main + Σ(인접 base × 0.7)
    - "군집(소)": Σ(면적) 합계의 base × 1.0 (모두 1,000㎡ 미만)
    - "군집(대)" / "혼합": main(최대) × 1.0 + Σ(부속 × 0.7)

    base_lookup(area) → base_total — main 외 면적의 base 인.일 산정 callback.
    """
    if facility_type == "기본" or not sub_areas:
        return base_main

    if facility_type == "군집(소)":
        # 모두 1,000㎡ 미만 → 합계 면적의 base 1.0
        total_area = sum(sub_areas)
        return base_lookup(total_area)

    # 인접 / 군집(대) / 혼합 — main + 부속 0.7
    sub_sum = sum(base_lookup(a) * 0.7 for a in sub_areas)
    return base_main + sub_sum
