# Phase 4-G 5차 재시도 설계 초안 (PR-EV)

> 작성: 2026-05-17
> 본 문서는 **설계 초안만** — 코드 수정 X. 운영 telemetry(`/admin/auth-stats`)
> 데이터 확보 + 사용자 명시 결정 후 PR-EW/EX/EY 단계로 구현.

## 1. 배경

Phase 4-G(JWT localStorage → httpOnly cookie 단독 인증) 4차 시도(PR-EM/EN,
2026-05-16)가 운영 회귀로 즉시 revert. 사고 원인 + 5차 안전망 보강 진행 상태:

### 4차 사고 요약
- cookie 발급 안 된 운영 사용자(PR-BH 1단계 이전 로그인 / third-party cookie
  차단 / domain mismatch)가 PR-EM 이전에는 localStorage token으로 backend
  header fallback 인증을 받고 있었음
- PR-EM이 `saveAuth` token 저장 중단 + PR-EN이 `Authorization` header 첨부
  제거 → backend는 여전히 header fallback을 제공하지만 frontend가 안 보냄 →
  401 무한 반복
- 즉시 revert: PR-EN(`b752a40`) + PR-EM(`7ea0824`)

### 5차 안전망 (현재 완료된 보강)
| 항목 | 완료 PR | 비고 |
|---|---|---|
| `verifyAndHydrateFromMe` reason 시그니처 | PR-EO (`feb2a4c`) | `{user, reason: 'ok'\|'unauthorized'\|'network'}` discriminated union |
| callback page playwright e2e | PR-EP (`cba951c`) | 3 시나리오(200/401/network) |
| backend auth channel 누적 카운터 | PR-ES (`2012260`) | `_auth_channel_counts` + `/api/auth/channel-stats` admin endpoint |
| frontend admin/auth-stats UI | PR-ET (`857f9ed`) | verdict 카드(GO/관찰/NO-GO) + 30초 자동 갱신 |
| USER_MANUAL + /help 사용법 | PR-EU (`5416cfe`) | 5차 판단 기준 명시 |

## 2. 5차 본격 PR 단계

5차는 4차와 동일한 변경(PR-EM/EN의 frontend cookie-only 전환)이지만, 운영
telemetry로 사전 검증된 시점에 진행한다는 점이 핵심 차이. **3단계 분리 유지**
— 회귀 시 단독 revert로 header fallback 즉시 복귀 가능.

### 사전 조건 (필수, 만족 안 하면 시작 금지)
1. `/admin/auth-stats` 페이지에서 `cookie_ratio ≥ 0.99` 확인
2. `since`로 누적 기간이 **운영 1주 이상**임을 확인 (Render restart 시 reset
   되므로 짧으면 다시 1주 대기)
3. 같은 사용자가 자주 호출해 ratio가 왜곡되지 않았는지 — `total` 누적값이
   충분(수천 건+)함을 확인
4. INCIDENT #5/#6 1차 충족 모두 살아있음 (`docs_audit` 자동 검증)

### PR-FA (1단계) — AuthGuard reason 활용
`components/AuthGuard.tsx`의 `refresh()` 흐름에서 PR-EO `verifyAndHydrateFromMe`
호출 (4차 PR-EM에서 추가했다가 revert) — 단, **reason별 차등 분기**:

```ts
// AuthGuard.refresh() 안, isLoggedIn() 분기
const result = await verifyAndHydrateFromMe();
if (result.reason === 'ok') {
  setUser(result.user);
  setPhase('ready');
} else if (result.reason === 'unauthorized') {
  // cookie 만료 또는 미발급 — silent SSO 시도 후 실패 시 login redirect
  if (worksOn && !hasError && !justLoggedOut) {
    const ssoUser = await trySilentSSO(window.location.pathname || '/');
    if (ssoUser) {
      setUser(ssoUser);
      setPhase('ready');
      return;
    }
  }
  setPhase('login');
} else {
  // 'network' — backend down 등. graceful: stale user 그대로 ready 진입
  // (PR Phase 0-B 정책 — backend down 시에도 가드 무력화 안 함)
  setUser(getUser());
  setPhase('ready');
}
```

**핵심:** 4차 PR-EM의 graceful fallback(401도 network도 동일하게 stale user
유지)이 cookie 만료 시점에 401 폭주를 표면화 못 한 것이 사고의 근원. PR-EO
reason 시그니처로 cookie 만료(`unauthorized`)와 backend down(`network`)을
구별해 차등 처리.

검증:
- vitest: AuthGuard.refresh reason별 분기 시나리오 3건 (ok/unauthorized/network)
- 운영 영향: 아직 cookie 발급 안 된 사용자(잔존 cohort, 0.01 이하 가정)에서
  silent SSO trigger 추가됨 — 성공 시 정상 진입, 실패 시 login redirect.
  완전한 logout이 아니라 재로그인 UX

### PR-FB (2단계) — `saveAuth` token 저장 중단 + `isLoggedIn` user-기반
4차 PR-EM과 동일 변경 — token 인자 무시 + `isLoggedIn` = `!!getUser()`.

PR-FA가 먼저 들어가 stale user 검증 회복 흐름이 보장된 상태에서 진행. 같은
commit으로 묶지 않는 이유: 회귀 시 PR-FB만 단독 revert해도 안전망(PR-FA)은
유지.

### PR-FC (3단계) — `authFetch`의 `Authorization` header 첨부 코드 제거
4차 PR-EN과 동일 변경 — `getToken` 함수 제거 + `authFetch`/`backendLogout`
에서 header 첨부 코드 제거.

PR-FB deploy 후 1~2일 telemetry로 cookie_ratio가 계속 99%+ 유지되는지
재확인 후 진행. 운영 cohort가 cookie로 완전히 전환됐는지 검증.

## 3. 회귀 방지 체크리스트

| # | 항목 | 4차 누락 여부 | 5차 보강 |
|---|---|---|---|
| 1 | callback hydration raw fetch | ✅ (PR-CY) | 유지 |
| 2 | saveAuth signature backward-compat | ✅ (PR-BN) | 유지 |
| 3 | authFetch silent retry 제외 list | ✅ (PR-DV) | 유지 |
| 4 | callback page에서 authFetch 호출 X | ✅ (PR-CY/DV) | 유지 |
| 5 | playwright e2e cookie 시나리오 | ❌ → ✅ (PR-EP) | 신규 |
| 6 | graceful fallback reason 구별 | ❌ → ✅ (PR-EO) | 신규 + PR-EW가 활용 |
| 7 | telemetry 운영 관찰 1주+ | ❌ → ✅ (PR-EL+ES+ET) | 신규 |
| 8 | cookie 발급 실패 사용자 잔존 검증 | ❌ → ✅ (cookie_ratio 모니터) | 신규 |

## 4. 회귀 시 즉시 대응

각 PR이 단독 revert 가능하도록 분리:
- PR-FC 회귀 → `git revert <hash>` → frontend가 다시 header 첨부 (PR-FB 잔존
  사용자의 localStorage token 활용)
- PR-FB 회귀 → `git revert <hash>` → frontend가 다시 token 저장 (PR-FA 잔존
  reason 분기 활용)
- PR-FA 회귀 → `git revert <hash>` → AuthGuard graceful 동작으로 복귀

5차 사고 발생 시 INCIDENT.md에 사고 entry + `.claude/rule/error.md`에 기록
필수 (CLAUDE.md 지침).

## 5. 결정 시점

본 설계는 **참고 자료**. 실제 PR-FA 진행은 다음 조건 모두 충족 시:
- (a) 운영 `cookie_ratio ≥ 0.99` × 1주 이상
- (b) 사용자 명시 결정 — "5차 진행"

조건 미충족 시 telemetry 관찰 지속. AuthGuard reason 시그니처(PR-EO)는 이미
적용됐지만 활용 안 됨 — 죽은 코드처럼 보일 수 있으나 5차 준비 인프라.

**주: 본 문서 초안 작성 시 5차 본격 PR을 PR-EW/EX/EY로 명명했으나, 2026-05-17
PR-EW가 다른 작업(_collect_overdue_seals notion filter push down, PR-CR 4순위)에
사용되면서 PR-FA/FB/FC로 재명명. 코드는 동일.**
