# 주간업무일지 PDF 폰트 적용 기준

> 출처: `backend/app/templates/weekly_report.html`, `backend/app/templates/_schedule_mini.html`
> 마지막 업데이트: 2026-05-11

폰트 family는 `NanumGothic` 단일. 사이즈는 17개 이상의 분기로 흩어져 있음. 본 문서는 현재 적용 기준의 스냅샷이며 일관성 정리 시 참조.

---

## A. 헤더·타이틀 (페이지 상단 running element)

| 영역 | pt | weight | 비고 |
|---|---|---|---|
| 메인 제목 "주간업무일지" `.title-line` | **15pt** | 700 | 자간 0.02em |
| 기간 라벨 (옆 회색) `.period` | 10pt | 500 | color #555 |
| h1 (사용처 거의 없음) | 15pt | 700 | 자간 0.05em |
| 우측 회사 로고 옆 한글 "(주)동양구조" `.brand-text .ko` | 9pt | 700 | |
| 우측 영문 회사명 `.brand-text .en` | **4pt** | 700 | 자간 -0.1em (≈ 90%) / nowrap |

## B. 본문·섹션 일반

| 영역 | pt | 비고 |
|---|---|---|
| `body` 기본 | **8pt** | line-height 1.35 |
| `h2` (섹션 헤더 회색 박스) | 8pt | 700 + 좌측 #888 막대 + 배경 #ececec |
| `h3` | 8pt | 700 |
| `.summary-line` (인원현황) | 7pt | 배경 #f7f7f5 |
| 공지·교육·건의 `<ul>` | 8pt | (건의 sub `· 작성자 · 상태` = 7pt #888) |

## C. 표 공통 (글로벌 `table`)

| 영역 | pt | 비고 |
|---|---|---|
| `table` 본문 td | **7pt** | 자간 -0.04em / table-layout fixed |
| `th` 헤더 | 6.5pt | 700 / center / 배경 #ebeef0 |
| `.empty` (빈 칸) | 5pt | italic + 점선 border |
| `.scale-cell` (영업/신규 규모 cell) | 5pt | 본문 -2pt |

## D. 길이 기반 자동 축소 (em 비례 — base 폰트에 따라 결과 달라짐)

| class | 비율 | 7pt base | 6.5pt base |
|---|---|---|---|
| `cell-shrink-1` | 0.85em | 6.5pt | 6pt |
| `cell-shrink-2` | 0.75em | 6pt | 5.5pt |
| `cell-shrink-3` | 0.65em | 5.5pt | 5pt |
| `cell-shrink-4` | 0.55em | 5pt | 5pt |

### Jinja 매크로 적용 규칙

| 매크로 | 적용 cell | 임계값 (글자 수) |
|---|---|---|
| `fit_cell` | 용역명·프로젝트명 (넓은 cell) | 18 → -1 / 30 → -2 |
| `fit_client_cell` | 발주처·제출처 (좁은 cell, 한 단어 회사명) | 8 → -1 / 10 → -2 / 13 → -3 / 15 → -4 |

`fit_client_cell`이 더 공격적인 이유: 회사명은 한 단어라 줄바꿈 시 가독성 매우 나쁨. ㈜포스코에이앤씨종합건축사사무소(16자)도 한 줄로 보장하기 위해 -4단계까지.

## E. 섹션별 표 (예외 폰트)

| 섹션 | 본문 | th | 기타 |
|---|---|---|---|
| **팀별 업무 현황** `.tw-table` | **6.5pt** | (글로벌 6.5pt) | 직급 `.tw-emp .pos` = 6pt / **CODE(2번째) + 지난주(6번째) + 이번주(7번째) 컬럼 = 5.5pt** (-1pt) |
| **개인 주간 일정** `.schedule-mini` | **6pt** | **5.5pt** | 직급 `.emp-cell .pos` = 5pt / `.schedule-chip` = 5pt 600 / `.schedule-card-header` = 6.5pt 700 (count = 6pt) |
| **대기/보류 프로젝트** `.stage-table` | **5.5pt** | **5.5pt** | 가장 작음 / line-height 1.15 |

## F. 기타

| 영역 | pt | 비고 |
|---|---|---|
| 페이지 footer "p. x / y" `@bottom-right` | 8pt | #888 |
| `.footer-note` | 6pt | #999 / 우측 정렬 |
| `.badge` (입찰 등) | 6pt | 배경 #eee |
| `.badge-bid` | 6pt | 배경 #ddf #339 |

---

## 사이즈 ladder 요약 (큰 → 작은)

```
15pt — 헤더 메인 제목 / h1
10pt — 헤더 기간 라벨
 9pt — 헤더 한글 회사명
 8pt — body / h2 / h3 / 공지·교육·건의 본문 / footer page no
 7pt — table 본문 / .summary-line(인원현황) / 건의 sub
6.5pt — table th / 팀별업무 본문 / 개인일정 카드 헤더 / cell-shrink-1
 6pt — 팀별업무 직급 / 카드 count / footer-note / badge / cell-shrink-2
       (.tw-table 안에서는 cell-shrink-1)
5.5pt — 개인일정 mini th / 팀별업무 CODE+업무 cell / 대기·보류 표 / cell-shrink-3
       (.tw-table 안에서는 cell-shrink-2)
 5pt — 개인일정 직급 / 규모 cell / chip / .empty / cell-shrink-4
       (.tw-table 안에서는 cell-shrink-3·4 모두 5pt floor)
 4pt — 헤더 영문 회사명
```

---

## 일관성 문제점 (정리 시 참조)

1. **"본문" 정의가 4가지** — 일반 표 7pt / 팀별업무 6.5pt / 개인일정 6pt / 대기·보류 5pt. 같은 "표 안 본문 텍스트"라도 표마다 다름.
2. **th 헤더 사이즈 3가지** — 6.5pt(공통) / 5.5pt(개인일정) / 5pt(대기·보류). 시각 hierarchy 혼동.
3. **cell-shrink는 em 기반** — base font가 7pt(공통) / 6.5pt(팀별업무)에 따라 결과 pt 다름. 같은 클래스 적용해도 어떤 표에선 5.95pt, 어떤 표에선 5.53pt.
4. **직급 사이즈 2가지** — 팀별업무 6pt / 개인일정 5pt.

---

## 향후 정리 옵션

### A. 표준 ladder 정의 + 모든 표 통일
8pt body / 7pt body-sm / 6.5pt th / 6pt th-sm / 5pt micro 같은 5단계만 사용. 모든 섹션이 그 안에서 선택. 일관성 최고지만 시각 변경 큼.

### B. 섹션별 base는 그대로, cell-shrink만 통일
cell-shrink를 em 대신 절대 pt(`5.5pt` / `5pt` / `4.5pt` / `4pt`)로 변경 → 표 base 무관하게 동일 결과. 침습 적음.

### C. 특정 섹션만 다듬기
사용자가 시각 검증 후 어색한 부분만 ±0.5pt 조정.
