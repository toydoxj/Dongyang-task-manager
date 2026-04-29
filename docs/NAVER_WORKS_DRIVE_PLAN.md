# NAVER WORKS Drive 연동 — 프로젝트별 폴더 자동 생성 계획

> 작성: 2026-04-29
> 상태: 사용자 의사결정 대기 (코드 미착수)
> 선행: NAVER WORKS OIDC SSO Phase 1 (운영 중, commit `b621e0d`)

---

## 1. 목표

WORKS 공용 드라이브에 다음 구조를 **프로젝트마다 자동 생성**:

```
[업무관리] (공용 드라이브의 루트 폴더 — admin이 사전 생성)
└─ [{CODE}]{프로젝트명}/         예: [25-001]서울아파트
   ├─ 1. 건축도면
   ├─ 2. 구조도면
   ├─ 3. 구조계산서
   ├─ 4. 구조해석및설계
   ├─ 5. 문서(심의자료 등)
   ├─ 6. 계약서
   └─ 7. 기타
```

폴더 web URL은 프로젝트 데이터에 저장 → UI에서 "WORKS Drive 열기" 1클릭 진입.

---

## 2. NAVER WORKS API 가능성 점검

| 항목 | 확인 결과 |
|---|---|
| 공유 드라이브에 폴더 생성 | ✅ `POST /v1.0/sharedrive/.../folders` 계열 endpoint 존재 (공식 doc 페이지 — 정확한 path는 PoC에서 확정) |
| 서비스 계정(JWT) 인증 | ⚠️ **PoC 필요**. 일반적으로 지원하지만 도메인 위임 설정이 필요할 수 있음 |
| 사용자 access_token 위임 | ✅ 가능. 단 사용자가 `drive` scope 동의 필요 |
| 공유 드라이브 ID 획득 | ⚠️ admin이 콘솔/API로 조회 — 사전 환경변수 등록 |
| 폴더 URL 반환 | ✅ 응답에 `folderId` + `webUrl` 포함 (일반적 패턴) |

**불확실 영역은 PoC 1일 안에 해결 가능 수준**.

---

## 3. 사용자 의사결정 필요 항목

### 3-1. 인증 방식

| 옵션 | 장점 | 단점 |
|---|---|---|
| **A. Service Account (JWT)** (권장) | 사용자 동의 0회. 백엔드가 항상 같은 권한으로 폴더 생성. 운영 단순 | 콘솔에서 service account 발급 + 도메인 권한 부여 필요. PoC 1일 |
| B. 사용자 OAuth 토큰 위임 | 추가 설정 거의 없음 | 폴더 생성한 사용자가 폴더 소유자 → 퇴사 시 권한 이슈. scope 추가 동의 필요 |

### 3-2. 트리거 시점

| 옵션 | 비고 |
|---|---|
| **A. 프로젝트 생성 직후 자동** (권장) | 기존 흐름과 매끄러움. API 실패해도 프로젝트 생성은 성공 (폴더는 retry/admin 수동) |
| B. admin이 명시 버튼 클릭 시만 | 즉시성 떨어짐. 누락 가능 |

### 3-3. 기존 1500+ 프로젝트 처리

| 옵션 | 비고 |
|---|---|
| **A. 신규 프로젝트만** (권장) | 즉시 적용. 기존은 admin이 필요 시 수동 |
| B. 일괄 backfill 스크립트 | 1500+ × 8 폴더 = 12,000+ API 호출. rate limit 우려. 야간 배치 필요 |
| C. admin 페이지에 "폴더 생성" 버튼 | 기존 프로젝트 행마다 수동 트리거. 안전 |

### 3-4. 폴더 URL 저장 위치

| 옵션 | 비고 |
|---|---|
| **A. 노션 DB 컬럼 신설** (권장) | 단일 source 유지. Mirror에도 자연스럽게 반영. 노션 DB에 `WORKS Drive URL` (URL 타입) 컬럼 1개 추가 |
| B. 자체 DB만 | mirror_projects에 컬럼 추가. 노션과 분리 |

### 3-5. 폴더 이름 충돌 처리

`[25-001]서울아파트`가 이미 있을 때:

| 옵션 | 비고 |
|---|---|
| **A. 기존 폴더 그대로 사용 (idempotent)** (권장) | 폴더 ID/URL만 가져와 저장. 안전 |
| B. 신규로 강제 생성 (`[25-001]서울아파트 (2)`) | 혼란 유발 |
| C. 에러 반환 + admin 알림 | 안전하지만 운영 부담 |

### 3-6. 권한 정책

| 옵션 | 비고 |
|---|---|
| **A. [업무관리] 폴더의 권한 상속** (권장) | admin이 [업무관리] 자체에 회사 전체 권한 부여 → 하위는 자동 상속 |
| B. 폴더마다 프로젝트 멤버에게 명시 권한 | 매 멤버 변경 시 polling. 복잡 |

### 3-7. 7개 sub 폴더 — 회사 표준 vs 프로젝트별 커스텀

| 옵션 | 비고 |
|---|---|
| **A. 7개 고정** (사용자 명시) | 코드에 상수로 박음 |
| B. admin이 sub 폴더 set을 settings로 편집 | 유연하나 과한 추상화 |

---

## 4. 권장 시나리오 (사용자 답변 채택 가정)

위 7개 결정에서 모두 **A**(권장) 선택 시 흐름:

```
admin이 사전 1회 작업:
1. NAVER WORKS Developer Console → 앱에 'drive' scope 추가
2. Service Account 발급 + Private Key 다운로드
3. 어드민 콘솔에서 service account에 [업무관리] 폴더 권한 부여
4. [업무관리] 루트 폴더 생성 + 회사 전체 권한 부여
5. 환경변수 등록:
   - WORKS_DRIVE_ENABLED=true
   - WORKS_SERVICE_ACCOUNT_ID
   - WORKS_PRIVATE_KEY (PEM)
   - WORKS_DRIVE_ROOT_FOLDER_ID  (= [업무관리]의 folderId)

신규 프로젝트 생성 시:
1. 사용자가 task UI에서 프로젝트 생성 (기존 흐름)
2. backend가 노션에 프로젝트 row 생성 (기존)
3. backend가 동일 트랜잭션 끝에 sso_drive 모듈 호출:
   a. JWT 발급 (Service Account → access_token)
   b. POST /v1.0/sharedrive/.../folders — 부모=root, name=[CODE]프로젝트명
      → 이미 있으면 GET으로 기존 folderId 가져옴 (idempotent)
   c. 7개 sub 폴더 일괄 생성
   d. 부모 폴더의 webUrl 받아옴
4. 노션 'WORKS Drive URL' 컬럼에 webUrl 저장 (write-through로 mirror도 갱신)
5. UI: 프로젝트 카드/모달에 "WORKS Drive 열기" 버튼 노출 (URL 비어있으면 비활성)

실패 처리:
- API 실패 시 프로젝트 생성은 그대로 성공
- 실패 사유는 logs + admin 페이지에 "폴더 미생성 프로젝트" 리스트
- admin 페이지에 "재시도" 버튼
```

---

## 5. Phase 분할

| Phase | 목표 | 예상 작업 |
|---|---|---|
| **D-0 (1일, PoC)** | 인증·API 가능성 검증 | Service Account 발급 → JWT으로 sharedrive 조회 → 폴더 1개 생성 → 응답 schema 확정 |
| **D-1 (2일)** | sso_drive 모듈 + 환경변수 + 노션 컬럼 추가 | `app/services/sso_drive.py`, settings, render.yaml, 노션 schema |
| **D-2 (2일)** | 프로젝트 생성 hook + 라우터 + UI | `routers/projects.py`에 폴더 생성 호출, 프론트 카드/모달에 "Drive 열기" 버튼, admin 페이지 "재시도" |
| **D-3 (1일)** | 검증·롤아웃 | 단위 테스트, 스테이징에서 5개 프로젝트 생성 검증, production 활성 |

총 **6일**. (Phase 1 SSO는 12일 plan했지만 5일 만에 끝났음 — 비슷한 규모 예상.)

---

## 6. 위험 / 완화

| 위험 | 완화 |
|---|---|
| Drive API rate limit (분당 N건) | 폴더 생성 직렬화 + retry with backoff |
| Service Account JWT 도메인 권한 부여가 콘솔에서 안 보일 가능성 | PoC에서 우선 점검. 안 되면 옵션 B(사용자 OAuth)로 fallback 검토 |
| 프로젝트명 변경 시 기존 폴더 이름 어떻게 | **Phase D 범위 외**. 첫 버전은 생성 시 이름만. 변경 추적은 후속 |
| 프로젝트 삭제·archive 시 폴더 처리 | **Phase D 범위 외**. 삭제 안 함이 안전 (감사·복원 위해) |
| 일괄 backfill 1500+ × 8 호출 | 옵션 C(admin 수동 버튼)로 우회. 야간 batch는 별도 작업 |

---

## 7. 사용자에게 묻는 의사결정 (요약)

| 번호 | 질문 | 권장 |
|---|---|---|
| Q1 | 인증 방식 — Service Account vs 사용자 OAuth | Service Account |
| Q2 | 트리거 — 자동 vs 수동 | 자동 (프로젝트 생성 직후) |
| Q3 | 기존 1500+ 프로젝트 처리 | 신규만 + admin 수동 버튼 |
| Q4 | 폴더 URL 저장 — 노션 DB 컬럼 vs 자체 DB | 노션 DB |
| Q5 | 동일 이름 폴더 충돌 — 기존 사용 vs 신규 강제 vs 에러 | 기존 사용(idempotent) |
| Q6 | 권한 — 루트 상속 vs 폴더별 명시 | 루트 상속 |
| Q7 | 7개 sub 폴더 — 고정 vs 편집 가능 | 고정 |

---

## 8. 다음 액션

1. 사용자가 Q1~Q7 답변 (또는 권장안 일괄 채택 의사 표명)
2. Phase D-0 PoC 시작 (admin이 Console에서 service account 발급 + 권한 부여)
3. PoC 통과 후 D-1~D-3 코드 작업

> 본 plan은 의사결정 대기 단계. 코드 변경 없음.
