## 지침

1. 모든 절차를 진행할 때는 Codex mcp를 불러서 상의 후 결정. 코드 작성 후에도 확인 절차 진행
2. 에러 발생시 해당 에러는 /.claude/rule/error.md에 작성하여 반복되지 않도록 함.


**트레이드오프:** 이 지침은 속도보다 신중함에 가중치를 둠. 사소한 작업에는 판단에 따라 유연하게 적용할 것.

## 1. 코딩 전에 먼저 생각할 것

**가정하지 말 것. 혼란을 숨기지 말 것. 트레이드오프를 드러낼 것.**

구현하기 전에:

- 가정을 명시적으로 진술할 것. 불확실하면 질문할 것.
- 여러 해석이 가능하면 모두 제시할 것 — 임의로 선택하지 말 것.
- 더 단순한 접근법이 있다면 그 점을 말할 것. 필요하다면 반대 의견을 제시할 것.
- 불명확한 부분이 있으면 멈출 것. 무엇이 혼란스러운지 명시하고 질문할 것.

## 2. 단순함을 우선할 것

**문제를 해결하는 최소한의 코드만 작성할 것. 추측성 코드 금지.**

- 요청 범위를 벗어난 기능 추가 금지.
- 일회성 코드를 위한 추상화 금지.
- 요청되지 않은 "유연성"이나 "구성 가능성" 추가 금지.
- 발생할 수 없는 시나리오에 대한 예외 처리 금지.
- 200줄을 작성했는데 50줄로 가능했다면, 다시 작성할 것.

스스로에게 물을 것: "시니어 엔지니어가 이 코드를 보고 과도하게 복잡하다고 할까?" 그렇다면 단순화할 것.

## 3. 외과적 수정

**필요한 부분만 건드릴 것. 자신이 만든 흔적만 정리할 것.**

기존 코드를 수정할 때:

- 주변 코드, 주석, 포맷팅을 임의로 "개선"하지 말 것.
- 망가지지 않은 것을 리팩터링하지 말 것.
- 본인의 스타일이 다르더라도 기존 코드 스타일을 따를 것.
- 무관한 데드 코드를 발견하면 언급만 할 것 — 임의로 삭제하지 말 것.

수정으로 인해 고아 코드가 발생한 경우:

- **본인의 수정으로 인해** 사용되지 않게 된 import, 변수, 함수만 제거할 것.
- 별도 요청이 없는 한, 기존부터 존재하던 데드 코드는 제거하지 말 것.

판단 기준: 변경된 모든 줄은 사용자의 요청과 직접적으로 연결되어야 함.

## 4. 목표 기반 실행

**성공 기준을 정의할 것. 검증될 때까지 반복할 것.**

작업을 검증 가능한 목표로 변환할 것:

- "유효성 검증 추가" → "잘못된 입력에 대한 테스트를 작성하고 통과시킬 것"
- "버그 수정" → "버그를 재현하는 테스트를 작성한 뒤 통과시킬 것"
- "X 리팩터링" → "변경 전후 모두 테스트가 통과하도록 보장할 것"

다단계 작업의 경우, 간략한 계획을 먼저 진술할 것:

```
1. [단계] → 검증: [확인 방법]
2. [단계] → 검증: [확인 방법]
3. [단계] → 검증: [확인 방법]
```

---

## 5. 프로젝트 환경 (Task_DY 특화)

**Stack:** FastAPI + Postgres(SQLAlchemy 2 + alembic) + Notion API + NAVER WORKS Drive ↔ Next.js 16 + React 19 + Tailwind 4 + shadcn/ui + Zustand + SWR + WeasyPrint(PDF)

**명령어**
- `cd backend && uv add 'pkg>=v'` — pip은 PEP 668 차단, uv 필수
- `cd backend && source .venv/bin/activate && python -c "..."` — 로컬 검증
- `cd backend && alembic heads` / `alembic upgrade head` — DB schema
- `cd frontend && npx tsc --noEmit` — type check
- `pdftoppm -r 100 -png in.pdf out` — PDF→PNG 시각 디버깅 (poppler 설치됨)

**핵심 패턴**
- `quote_form_data` 신 schema: `{forms:[{id, doc_number, suffix, input, result, is_external?, attached_pdf_*?}]}`. POST/PATCH /sales 라우터에서 단일 schema → list-wrap 즉시 변환 필수 (안 하면 `normalize_quote_forms`가 매 호출 새 uuid → quote_id mismatch).
- alembic version naming: 직전 revision + 새 영문 prefix `{x}{prev}{date}_desc.py`.
- 노션 schema: `backend/app/services/notion_schema.py SALES_DB_REQUIRED` dict 부팅 시 자동 등록. drop은 노션 UI 수동.
- 단가: `backend/app/services/quote_calculator.py ENGINEERING_RATES_BY_GRADE` (매년 1월 갱신).
- 견적서 13종 + `_CODE_MAP` 분류 코드 (구조설계 01 ~ 기타 99). 영업당 다중 견적 모델 (PR-M) — `parent_lead_id` 폐기됨.
- xlsx 검증: `docs/quote_formulas/*.md` dump → backend strategy transcribe → ±0원 일치.

**Quirks**
- frontend: Next.js 16 / React 19 (학습 데이터와 차이) — `node_modules/next/dist/docs/` 참조
- backend: KST `_KST = timezone(timedelta(hours=9))`
- WeasyPrint paged media: flex `justify-content: center` 부분 동작. `running()` element는 page bottom margin 영역에 자동 배치.
- Render: backend Docker 빌드 5-8분 (WeasyPrint + cairo + fonts-nanum). 짧은 시간 6+ commits push → pipeline limit (dashboard에서 큐 cancel 또는 plan 업그레이드).
- 한글 파일명 표기 주의 ("프**레**젠테이션" vs "프**리**젠테이션").
- PDF 결과 검증 protocol: build_quote_pdf() → /tmp PDF → pdftoppm PNG → Read 시각 확인 → 사용자 OK → push.

**주요 디렉터리**
- `backend/app/routers/sales.py` — 영업/견적 CRUD, PDF 라우터
- `backend/app/services/quote_*.py` — 산출 strategy / PDF / forms helper
- `backend/app/templates/quote_template.html` — PDF Jinja2 템플릿
- `frontend/components/sales/SalesEditModal.tsx` — 영업 모달 (견적 list view + form view)
- `frontend/components/sales/QuoteForm.tsx` — 견적 입력 form
- `docs/quote_formulas/*.md` — xlsx 산출식 dump (PR-Q0 산출물)
