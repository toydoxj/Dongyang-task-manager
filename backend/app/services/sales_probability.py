"""영업(Sales) 단계별 수주확률 + 기대매출 계산.

영업의 진행률은 마일스톤이 아닌 **단계 + 단계별 확률** 모델만 사용한다
(`PLAN_PROGRESS_EVAL.md §3.1` 참조 — 영업 단계는 마일스톤 적용 외).

kind에 따라 두 갈래의 단계 옵션이 다르며, 각 단계마다 사전 정의된 수주확률을
가진다. 기대매출 = 견적금액 × 수주확률.

추후 운영 안정 후 DB 테이블로 이전 가능 — 일단 코드 상수로 유지.
"""
from __future__ import annotations

SALES_KIND_BID = "수주영업"
SALES_KIND_PRESALES = "기술지원"

# 수주영업 단계별 수주확률 (사장 결정 — 보수적 분포).
# 사장이 운영하던 노션 단계 옵션을 사용자 결정에 따라 5단계로 재정렬.
# 매핑(노션 옵션 rename으로 진행): 견적준비→준비, 입찰대기→진행,
# 우선협상→제출, 낙찰→완료, 실주→종결.
BID_STAGES: dict[str, float] = {
    "준비": 0.05,
    "진행": 0.10,
    "제출": 0.10,
    "완료": 1.00,
    "종결": 0.00,
}

# /convert 가능 단계 — 수주확정 시점.
CONVERTIBLE_STAGES: frozenset[str] = frozenset({"완료"})

# 기술지원 단계별 수주확률 — PM 합의 후 시드 작성 시 채움.
# 미합의 상태에서는 PRESALES_DEFAULT_PROBABILITY fallback 적용 (사용자 결정: 10%).
PRESALES_STAGES: dict[str, float] = {
    # 예시 (PM 합의 후 활성화):
    # "요청접수": 0.05,
    # "검토중":   0.10,
    # "회신완료": 0.15,
    # "수주연계": 0.50,
    # "종료":     0.00,
}

# 기술지원의 미정의/미합의 단계 default 확률
PRESALES_DEFAULT_PROBABILITY: float = 0.10

STAGE_PROBABILITY_BY_KIND: dict[str, dict[str, float]] = {
    SALES_KIND_BID:      BID_STAGES,
    SALES_KIND_PRESALES: PRESALES_STAGES,
}


def stage_probability(kind: str | None, stage: str | None) -> float:
    """단계별 수주확률 [0.0, 1.0].

    - kind/stage 미설정: 0.0
    - 수주영업의 등록되지 않은 단계: 0.0
    - 기술지원의 등록되지 않은 단계: PRESALES_DEFAULT_PROBABILITY (10%)
    """
    if not kind or kind not in STAGE_PROBABILITY_BY_KIND:
        return 0.0
    table = STAGE_PROBABILITY_BY_KIND[kind]
    if stage and stage in table:
        return table[stage]
    if kind == SALES_KIND_PRESALES:
        return PRESALES_DEFAULT_PROBABILITY
    return 0.0


def expected_revenue(
    estimated_amount: float | None,
    kind: str | None,
    stage: str | None,
) -> float:
    """기대매출 = 견적금액 × 수주확률.

    견적금액이 없으면 0. 수주영업의 경우 단계가 없으면 0이지만, 기술지원은
    default 10%가 적용된다.
    """
    if estimated_amount is None:
        return 0.0
    return estimated_amount * stage_probability(kind, stage)
