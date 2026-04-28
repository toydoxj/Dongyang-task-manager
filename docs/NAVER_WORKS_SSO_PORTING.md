# NAVER WORKS SSO 이식 가이드 (DY_MIDAS 등 사내 다른 앱 적용)

> 본 문서는 `task.dyce.kr` 백엔드(`api.dyce.kr`)에 도입된 NAVER WORKS OAuth 2.0 SSO를
> DY_MIDAS 같은 다른 사내 앱에서도 동일한 사용자·동일한 흐름으로 쓰기 위한 가이드입니다.
>
> 작성: 2026-04-29
> 기준 commit: `340bf2a` (Task_DY main)
> 참조 인계 문서: `_reference/DY_MIDAS_PROJECT/SSO_MIGRATION.md` (자체 인증 → task 위임 작업, 2026-04-27)

---

## 1. 사전 결정 — 두 가지 시나리오

| | A. **task SSO 공유** (권장) | B. 독립 NAVER WORKS 앱 |
|---|---|---|
| 사용자 풀 | `task` DB 단일 | DB 분리 |
| 로그인 흔적 | 한 번 NAVER 인증으로 모든 사내 앱 통합 | 앱마다 NAVER 인증 반복 |
| JWT_SECRET | task와 통일 필수 | 별개로 가능 |
| backend 변경 | task에 frontend whitelist 추가 (소규모) | 신규 앱 + redirect URI 등록 + 토큰 발급 흐름 전체 복제 |
| 운영 부담 | 낮음 | 중간 |
| 추천 | ✅ 권장 | 외부 협력사용 또는 분리가 강제될 때 |

---

## 2. 시나리오 A — task SSO 공유 (권장)

### 2.1 전제
- DY_MIDAS 백엔드는 이미 `auth_middleware.py`에서 `https://api.dyce.kr/api/auth/me`로
  토큰 검증을 위임 중. `JWT_SECRET`이 task 백엔드와 동일해야 한다 (재확인).
- DY_MIDAS frontend 도메인이 정해져 있어야 함 (예: `midas.dyce.kr`).

### 2.2 task 백엔드(`api.dyce.kr`)에 추가할 변경

**(1) `FRONTEND_BASE_URL` 단일값 → 화이트리스트로 확장**

`backend/app/settings.py` 변경 예:
```python
# 콤마 구분. https://task.dyce.kr,https://midas.dyce.kr
frontend_allowed_origins: str = ""

@property
def frontend_allowed_origins_list(self) -> list[str]:
    return [s.strip().rstrip("/") for s in self.frontend_allowed_origins.split(",") if s.strip()]
```

`backend/app/services/sso_works.py`의 `issue_state()`가 `next_path`만이 아니라
`origin`(frontend base)도 함께 인코딩하도록 확장.

```python
def issue_state(jwt_secret: str, next_path: str, origin: str) -> tuple[str, str]:
    payload = json.dumps({"n": nonce, "t": int(time.time()), "x": next_path, "o": origin}, ...)
    ...
```

`/auth/works/login`에서 `?front=https://midas.dyce.kr` query를 받아 화이트리스트 검증 후
state에 embed. callback에서 `state.o`를 fragment redirect 대상으로 사용.

**(2) Render 환경변수**

```yaml
- key: FRONTEND_ALLOWED_ORIGINS
  value: https://task.dyce.kr,https://midas.dyce.kr
```

기존 `FRONTEND_BASE_URL`은 default(첫 번째 항목)로 유지.

### 2.3 DY_MIDAS 변경

**(1) frontend `lib/auth.ts` (Task_DY와 동일한 파일을 보유)**

```ts
const TASK_AUTH_BASE = "https://api.dyce.kr"; // env로 분리 권장
const SELF_ORIGIN = typeof window !== "undefined" ? window.location.origin : "";

export function worksLoginUrl(next: string = "/"): string {
  const qs = new URLSearchParams({ next, front: SELF_ORIGIN }).toString();
  return `${TASK_AUTH_BASE}/api/auth/works/login?${qs}`;
}
```

`consumeCallbackFragment()`는 그대로 복사 (base64url UTF-8 디코딩 포함).

**(2) frontend 신규 페이지 `app/auth/works/callback/page.tsx`**

Task_DY의 같은 파일을 그대로 복사. `window.location.replace(result.next || "/")`로 hard navigate.

**(3) frontend 신규 server layout `app/auth/works/callback/layout.tsx`**

```tsx
export const dynamic = "force-dynamic";
export const revalidate = 0;
export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
```

(Vercel edge cache HIT 차단)

**(4) AuthGuard 수정**

`pathname.startsWith("/auth/works/callback")`이면 인증 검사 우회 + children passthrough.
(Task_DY `frontend/components/AuthGuard.tsx` 참조)

**(5) LoginForm — 자동 redirect**

진입 시 `window.location.replace(worksLoginUrl("/"))`. JS 비활성 fallback `<a href>` 유지.
(Task_DY `frontend/app/login/LoginForm.tsx` 참조)

### 2.4 흐름

```
midas.dyce.kr/login
  └─ window.location.replace → api.dyce.kr/api/auth/works/login?front=https://midas.dyce.kr
       └─ state에 origin=midas.dyce.kr embed → 302 NAVER WORKS authorize
            └─ 사용자 인증
                 └─ NAVER → api.dyce.kr/api/auth/works/callback
                      └─ token 교환 + UserInfo + JWT 발급
                           └─ 302 https://midas.dyce.kr/auth/works/callback#token=...
                                └─ frontend가 saveAuth + window.location.replace("/")
```

---

## 3. 시나리오 B — 독립 NAVER WORKS 앱

DY_MIDAS가 자체 sso_works 모듈을 가지는 방식. 사용자 풀이 분리되지 않으면 추천하지 않음.

### 3.1 NAVER WORKS Developer Console
- 별도 앱 등록. redirect URI = `https://midas-api.dyce.kr/api/auth/works/callback`
- Permission Scope = `user.read`

### 3.2 backend 복제
Task_DY에서 가져올 파일 (DY_MIDAS의 `backend/`로):
- `app/services/sso_works.py` 전체
- `app/routers/auth.py`의 `/works/login` + `/works/callback` 라우터 블록
- `app/settings.py`의 `WORKS_*` 8개 필드 + `WORKS_BLOCKED_EMAILS`

### 3.3 환경변수 8개

| Key | 용도 |
|---|---|
| `WORKS_ENABLED` | true/false (운영 토글) |
| `WORKS_CLIENT_ID` | 콘솔 발급 |
| `WORKS_CLIENT_SECRET` | 콘솔 발급 |
| `WORKS_DOMAIN_ID` | 콘솔 도메인 정보 (정수) |
| `WORKS_REDIRECT_URI` | `https://<api>/api/auth/works/callback` |
| `WORKS_AUTHORIZE_ENDPOINT` | 기본값 `https://auth.worksmobile.com/oauth2/v2.0/authorize` |
| `WORKS_TOKEN_ENDPOINT` | 기본값 `https://auth.worksmobile.com/oauth2/v2.0/token` |
| `WORKS_USERINFO_ENDPOINT` | 기본값 `https://www.worksapis.com/v1.0/users/me` |
| `WORKS_BLOCKED_EMAILS` | `dyce@dyce.kr` (마스터 차단) |
| `FRONTEND_BASE_URL` | DY_MIDAS frontend |

**중요**: NAVER WORKS는 OIDC discovery(`/.well-known/openid-configuration`)를 노출하지
않는다. endpoint를 직접 박아야 한다 (위 3개 default).

### 3.4 DB 마이그레이션

`users` 테이블에 컬럼 3개 추가:
```sql
ALTER TABLE users ADD COLUMN works_user_id VARCHAR;
CREATE UNIQUE INDEX ix_users_works_user_id ON users(works_user_id);
ALTER TABLE users ADD COLUMN auth_provider VARCHAR NOT NULL DEFAULT 'password';
ALTER TABLE users ADD COLUMN sso_login_at DATETIME;
```

### 3.5 frontend 복제
시나리오 A의 (2)~(5) 동일.

---

## 4. 핵심 보안 체크리스트

- [ ] **JWT_SECRET 통일** (시나리오 A) — 양쪽 환경변수가 정확히 같아야 토큰 호환
- [ ] `email.endswith("@dyce.kr")` 검증
- [ ] UserInfo `domainId`가 `WORKS_DOMAIN_ID`와 일치 검증
- [ ] state는 HMAC-SHA256 signed token (cookie 의존성 0). TTL 10분
- [ ] WORKS의 OIDC discovery 미지원 → endpoint 코드/환경변수 직접 사용
- [ ] id_token RS256+JWKS 검증 대신 access_token + UserInfo API 호출
- [ ] fragment(`#token=`) 도착 즉시 `history.replaceState`로 history 정리
- [ ] `WORKS_BLOCKED_EMAILS`에 마스터/시스템 계정 등재
- [ ] frontend callback 페이지에 server layout `force-dynamic`로 edge cache 차단

---

## 5. 우리가 겪은 시행착오 — 미리 피하세요

| 증상 | 원인 | 해결 |
|---|---|---|
| `Internal Server Error` (500) | OIDC discovery 404 → 예외가 catch 안 됨 | discovery 호출 자체 제거. endpoint 직접 |
| `WORKS 설정 누락` (503) | render.yaml에서 `WORKS_ENABLED: value: "false"`로 박아둠 | `sync: false`로 변경 → dashboard 권위 |
| `state 쿠키 누락` | cross-site redirect 후 SameSite=Lax cookie 일부 환경에서 누락 | cookie 폐기, signed state 사용 |
| `?error=...`로 돌아오는 무한 루프 | LoginForm이 자동 redirect | error query 있으면 redirect 차단 |
| 빌드 후에도 옛 페이지 표시 (`x-vercel-cache: HIT`) | callback 페이지 SSR HTML이 edge cache | `force-dynamic` server layout |
| callback에서 다시 로그인 화면으로 돌아감 | AuthGuard가 fragment 파싱 전에 LoginForm 표시 | `pathname.startsWith("/auth/works/callback")`이면 AuthGuard 우회 |
| router.replace 후 dashboard 못 옴 | SPA navigation이라 AuthGuard 재검사 안 함 | `window.location.replace`로 hard reload |

---

## 6. 검증 절차 (사용자 1명 기준)

1. `https://api.dyce.kr/api/auth/status` 응답에 `"works_enabled": true`
2. DY_MIDAS frontend 진입 → 즉시 NAVER WORKS authorize 화면
3. NAVER 로그인 → `https://api.dyce.kr/api/auth/works/callback?code=...&state=...`
4. backend가 frontend로 fragment redirect (시나리오 A: midas.dyce.kr, B: 자체 frontend)
5. dashboard 도착, localStorage에 `dy_auth_token` / `dy_auth_user` 저장
6. 같은 사용자가 task와 DY_MIDAS 양쪽에서 같은 user.id로 인식되는지 (시나리오 A 한정)

---

## 7. 참고 — Task_DY의 핵심 파일/라우트 (복제·참조 대상)

| 항목 | 파일 |
|---|---|
| OIDC 흐름 + UserInfo + signed state + upsert | `backend/app/services/sso_works.py` |
| `/auth/works/login`, `/auth/works/callback` | `backend/app/routers/auth.py` |
| WORKS_* / BLOCKED 환경변수 | `backend/app/settings.py` |
| `users` 테이블 SSO 컬럼 추가 | `backend/alembic/versions/k0i1j2k30208_users_sso_fields.py` |
| 마스터 계정 강등 | `backend/alembic/versions/l1j2k3l40209_block_master_account.py` |
| 자동 redirect + 에러 처리 | `frontend/app/login/LoginForm.tsx`, `frontend/app/login/page.tsx` |
| callback 페이지 + edge cache 차단 | `frontend/app/auth/works/callback/{page.tsx,layout.tsx}` |
| AuthGuard callback 우회 | `frontend/components/AuthGuard.tsx` |
| frontend helper | `frontend/lib/auth.ts`, `frontend/lib/types.ts` |

---

## 8. 후속 작업 후보 (참고)

- 시나리오 A 채택 시 `FRONTEND_ALLOWED_ORIGINS` whitelist 검증 코드를 task 측에 추가
- `auth_provider='works'` 사용자는 password reset UI 자체를 숨김
- Phase 2 후보(별도): Bot 알림 / Calendar 일정 / Drive 첨부 / Approval(전자결재) — 본 SSO와 무관하게 추가 가능
