# 동양구조 업무관리 — Release 빌드 스크립트
#
# 단계:
#   1. backend (PyInstaller) 빌드
#   2. frontend (Next.js 정적 export) 빌드
#   3. Electron NSIS 빌드 (자동 업데이트 PAT 임시 주입)
#   4. (옵션) GitHub Releases 게시
#
# 사용:
#   pwsh scripts/release.ps1                  # 로컬 빌드만
#   $env:GH_PAT="ghp_..."; pwsh scripts/release.ps1   # PAT 주입 빌드
#   pwsh scripts/release.ps1 -Publish         # 빌드 + GitHub 게시 (GH_TOKEN 필요)

param(
    [switch]$Publish,
    [switch]$SkipBackend,
    [switch]$SkipFrontend
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

function Stage($msg) {
    Write-Host "`n=== $msg ===" -ForegroundColor Cyan
}

# 1. 백엔드 PyInstaller 빌드
if (-not $SkipBackend) {
    Stage "백엔드 PyInstaller 빌드"
    Set-Location "$Root/backend"
    uv run pyinstaller backend.spec --noconfirm
}

# 2. 프론트 정적 export
if (-not $SkipFrontend) {
    Stage "프론트엔드 정적 export"
    Set-Location "$Root/frontend"
    npm run build:electron
}

# 3. Electron NSIS 빌드
Stage "Electron 패키징"
Set-Location "$Root/electron"

$tokenFile = "update-token.txt"
if ($env:GH_PAT) {
    Write-Host "  PAT 감지 - 자동 업데이트 활성 빌드" -ForegroundColor Green
    $env:GH_PAT | Out-File -Encoding ASCII -FilePath $tokenFile -NoNewline
} else {
    Write-Warning "  GH_PAT 미설정 - 자동 업데이트 비활성 빌드 (수동 다운로드만 가능)"
    Set-Content -Path $tokenFile -Value "" -NoNewline -Encoding ASCII
}

try {
    if ($Publish) {
        if (-not $env:GH_TOKEN) {
            throw "Publish 모드: GH_TOKEN 환경변수가 필요합니다 (electron-builder가 release 게시에 사용)"
        }
        Write-Host "  GitHub Releases 게시 모드" -ForegroundColor Green
        npm run release
    } else {
        npm run build
    }
} finally {
    Remove-Item $tokenFile -Force -ErrorAction SilentlyContinue
}

Stage "완료"
Write-Host "결과: $Root/electron/dist/" -ForegroundColor Green
Get-ChildItem "$Root/electron/dist/*.exe" | Format-Table Name, @{N="Size(MB)";E={[math]::Round($_.Length/1MB,1)}}
