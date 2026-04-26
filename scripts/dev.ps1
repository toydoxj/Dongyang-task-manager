# 동양구조 업무관리 — 개발 모드 통합 실행
#
# 백엔드(uvicorn) + 프론트(Next dev)를 별도 창으로 띄우고,
# Electron은 현재 창에서 실행한다. Ctrl+C로 모두 정리됨.
#
# 사전 요구사항:
#   - uv (https://docs.astral.sh/uv/)
#   - Node.js 20+
#   - 의존성: cd backend && uv sync; cd frontend && npm install; cd electron && npm install

param(
    [switch]$NoElectron  # Electron 없이 백엔드+프론트만 띄울 때
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

function Stop-AllJobs {
    Get-Job | Where-Object { $_.State -eq "Running" } | Stop-Job
    Get-Job | Remove-Job -Force
}

try {
    Write-Host "[backend] uvicorn 기동 (port 8000)" -ForegroundColor Cyan
    $backend = Start-Job -ScriptBlock {
        param($r)
        Set-Location "$r/backend"
        uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
    } -ArgumentList $Root

    Write-Host "[frontend] Next dev 기동 (port 3000)" -ForegroundColor Cyan
    $frontend = Start-Job -ScriptBlock {
        param($r)
        Set-Location "$r/frontend"
        npm run dev
    } -ArgumentList $Root

    if ($NoElectron) {
        Write-Host "백엔드+프론트 기동 완료. Ctrl+C 로 종료." -ForegroundColor Green
        Wait-Job $backend, $frontend
    } else {
        Write-Host "두 서버가 떴는지 잠시 대기..." -ForegroundColor Yellow
        Start-Sleep -Seconds 5

        Write-Host "[electron] 셸 실행" -ForegroundColor Cyan
        Set-Location "$Root/electron"
        npm run dev
    }
}
finally {
    Write-Host "정리 중..." -ForegroundColor Yellow
    Stop-AllJobs
}
