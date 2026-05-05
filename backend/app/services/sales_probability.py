"""영업 단계 정책 — /convert 가능 단계.

수주확률은 PM이 노션 '수주확률' number 컬럼에 직접 입력 (사장 결정).
expected_revenue 계산은 Sale.expected_revenue computed_field에서
estimated_amount × probability/100 로 직접 산출하므로, 단계별 자동 확률
모델(BID_STAGES/PRESALES_STAGES/STAGE_PROBABILITY_BY_KIND)은 폐기됨.

단계는 가시화/필터링 용도로만 사용 (예: /me에서 완료/종결 숨김).
"""
from __future__ import annotations

# 영업 유형(kind) 상수 — 노션 '유형' select 옵션과 일치.
SALES_KIND_BID = "수주영업"
SALES_KIND_PRESALES = "기술지원"

# /convert (수주 전환) 가능한 단계.
# 사장 결정: '완료' 단계만 — 계약 확정 후에만 프로젝트 생성.
CONVERTIBLE_STAGES: frozenset[str] = frozenset({"완료"})
