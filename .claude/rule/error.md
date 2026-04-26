# 에러 로그 (반복 방지용)

> claude.md 지침: 발생한 에러는 본 파일에 기록하여 반복되지 않도록 한다.

## 형식

```
### YYYY-MM-DD — 짧은 제목
- 컨텍스트: 어떤 작업 중에 발생했는가
- 증상: 에러 메시지/현상
- 원인: 근본 원인
- 해결: 어떻게 고쳤는가
- 재발 방지: 다음에 어떻게 피할 것인가
```

---

### 2026-04-26 — `.claude/rule`가 디렉토리가 아닌 빈 파일로 생성됨
- 컨텍스트: 프로젝트 초기화 중 `.claude/rule/error.md` 생성 시도
- 증상: `mkdir: cannot create directory '.claude/rule': File exists`
- 원인: 이전 세션에서 `rule`이 0바이트 파일로 생성되어 있었음
- 해결: 빈 파일 삭제 후 `mkdir -p`로 디렉토리 생성
- 재발 방지: 디렉토리 생성 전 `ls -la`로 동일 이름 파일 존재 여부 확인

### 2026-04-26 — packaged backend.exe가 Program Files data 디렉토리 생성 시 권한 거부
- 컨텍스트: NSIS 설치 후 첫 실행 — backend.exe가 `Program Files\dongyang-task-electron\resources\backend\data` 만들려다 실패
- 증상: `PermissionError: [WinError 5] 액세스가 거부되었습니다`, exit code 1
- 원인: run.py가 BACKEND_DATA_DIR 미설정 시 fallback을 `exe_dir/data`로 두어 read-only 위치 시도
- 해결:
  1) electron/main.js spawn env에 `BACKEND_DATA_DIR: app.getPath("userData")` 명시 전달
  2) run.py fallback도 `%LOCALAPPDATA%\동양구조 업무관리\data`로 강화
- 재발 방지: PyInstaller로 sidecar 만들 때 데이터 디렉토리는 절대 설치 위치(Program Files)에 의존하지 말 것. Electron이 항상 userData 경로를 명시 전달.

### 2026-04-26 — packaged frontend가 backend random port에 접근 못 함 (Failed to fetch)
- 컨텍스트: 설치 후 UI는 떴으나 모든 API 호출이 "Failed to fetch"
- 증상: 대시보드 빨간 에러 박스 "Failed to fetch"
- 원인: frontend의 `API_BASE`를 빌드 시점에 `process.env.NEXT_PUBLIC_API_BASE` (= `http://127.0.0.1:8000`)로 인라인. packaged 환경에서 backend는 `getFreePort()`로 랜덤 포트(예: 56727) 사용 → 8000으로 보낸 요청 모두 fail
- 해결: lib/types.ts의 `API_BASE`를 client-side에서 `window.location.origin` 사용하도록 동적 계산. backend가 frontend도 정적 서빙하므로 같은 origin으로 호출 가능
- 재발 방지: Electron sidecar + 정적 frontend 패턴에서 환경변수를 빌드 시점에 인라인 금지. client에서 런타임 `window.location.origin` 사용. dev에서는 별도 분기.

### 2026-04-26 — 노션 API 응답 지연 → Postgres 미러 캐싱 도입
- 컨텍스트: 모든 read endpoint가 노션 직접 호출 → 페이지당 1~3초. MasterProjectModal sub-project N+1, list_projects의 client/master title lookup 누적 호출
- 증상: UI 진입마다 1~3초 로딩, 클릭마다 추가 지연
- 원인: 노션 API 자체 200~800ms + RateLimiter 0.4초 + TTLCache 30초로 사실상 매번 cache miss
- 해결:
  1) `app/services/sync.py` NotionSyncService — 노션 → mirror_* 테이블 upsert
  2) `app/services/scheduler.py` APScheduler 5분 incremental + 1일 03:00 full reconcile
  3) read 라우터 모두 mirror 조회로 전환
  4) write 라우터는 노션 update 직후 sync.upsert_page (write-through)
  5) MasterProjectModal sub-project N+1 → mirror_projects 단일 IN 쿼리
- 재발 방지: 외부 API에 의존하는 read는 항상 mirror/cache 레이어 우선. 미러 부재 시만 fallback fetch + upsert.

### 2026-04-26 — Packaged 환경에서 노션 토큰 배포 방식
- 컨텍스트: 사용자 PC마다 .env 직접 두기 불편. NOTION_API_KEY 등 어떻게 배포?
- 결정: 옵션 A — `backend/.env.production` 파일을 PyInstaller datas에 번들 (사내 도구라 보안 trade-off 수용)
- 우선순위: `BACKEND_DATA_DIR/.env` (사용자 override) > `exe_dir/.env` > 번들 `.env.production` (기본값)
- JWT_SECRET은 첫 실행 시 user_dir에 자동 생성/저장 (`secrets.token_urlsafe(64)`)
- 재발 방지: `.env.production`은 .gitignore 처리, 빌드자만 보유. 토큰 유출 시 노션 통합 토큰 재발급으로 대응 가능
