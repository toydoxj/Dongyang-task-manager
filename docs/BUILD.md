# 빌드 가이드 (관리자용)

> 신규 버전 빌드/배포 절차.

## 사전 요구사항

- Windows 10/11 (현재 빌드 스크립트는 Windows 전용)
- Python 3.12+ + [uv](https://docs.astral.sh/uv/)
- Node.js 20+
- Git
- (자동 업데이트 빌드용) GitHub Personal Access Token

## 한 번에 빌드 (권장)

```powershell
# 환경변수 PAT 설정 (자동 업데이트 활성)
$env:GH_PAT = "ghp_xxxxxxxxxxxxxxxxxxx"

# 로컬 빌드
pwsh scripts/release.ps1

# 빌드 + GitHub Releases 게시
$env:GH_TOKEN = "ghp_xxxxxxxxxxxxxxxxxxx"  # publish 권한 있는 토큰
pwsh scripts/release.ps1 -Publish
```

빌드 결과: `electron/dist/동양구조 업무관리 Setup X.X.X.exe`

## 단계별 빌드

### 1. 백엔드 PyInstaller
```powershell
cd backend
uv run pyinstaller backend.spec --noconfirm
# 결과: backend/dist/backend/backend.exe
```

### 2. 프론트엔드 정적 export
```powershell
cd frontend
npm run build:electron
# 결과: frontend/out/
```

### 3. Electron NSIS 빌드
```powershell
cd electron
# (자동 업데이트 활성 빌드인 경우)
$env:GH_PAT | Out-File -Encoding ASCII update-token.txt -NoNewline
npm run build
# 결과: electron/dist/동양구조 업무관리 Setup 0.0.1.exe
Remove-Item update-token.txt
```

## GitHub PAT 발급

1. https://github.com/settings/tokens 접속
2. **Generate new token (classic)**
3. Scopes: `repo` (private repo 읽기 + Releases 게시 양쪽)
4. 만료 기간: 90일~1년 권장
5. 생성된 토큰을 안전한 곳에 보관 (다시 볼 수 없음)

## 자동 업데이트 동작

- 사용자가 앱 실행 시 `latest.yml` 메타파일 다운로드 → 새 버전 감지
- private repo 라 PAT 필요 — `update-token.txt` (extraResources)에서 읽음
- 사용자가 "다운로드" 동의 → 새 .exe 다운로드 → "재시작" → 설치

## 버전 올리기

`electron/package.json` 의 `version` 만 수정 후 빌드 — `latest.yml`이 새 버전을 표시.

## 코드사이닝 (TODO)

- 인증서 확보 시 `electron/package.json` 의 `win.signtoolOptions` 추가
- 미서명 빌드는 Windows SmartScreen 경고 발생 (정상 동작)
