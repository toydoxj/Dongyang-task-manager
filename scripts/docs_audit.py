"""docs/ 일관성 audit (Phase 4-H, PR-EE/EF).

repo root에서 `python scripts/docs_audit.py` 실행. stdlib만 사용 (venv 불필요).

검사 항목:
  1. (PR-EE) `docs/STATUS.md`의 commit hash 99개 → `git rev-parse`로 존재 검증
  2. (PR-EF) `docs/USER_MANUAL.md` ↔ `frontend/app/help/page.tsx` 섹션 번호(N.M)
     set 일치 검증 — V-3 cross-check 자동화. 한쪽에만 있는 번호 출력.

문구 자체는 양쪽이 의도적으로 다를 수 있어(예: USER_MANUAL `(\\`/me\\`)`, /help
`(/me)`) 번호만 비교한다.

확장 후보 (별도 cycle):
- INCIDENT.md 추적 항목 형식 (`- [ ]` / `- [x]`)
- PERMISSIONS.md 라우터 가드와 backend `require_*` 의존성 cross-check
- CI 통합 (`.github/workflows/`)

exit code:
  0 — 모든 검사 통과
  1 — 일부 검사 실패 (출력에 항목 + 세부)
  2 — 파일/git 접근 실패
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
STATUS_PATH = REPO_ROOT / "docs" / "STATUS.md"
USER_MANUAL_PATH = REPO_ROOT / "docs" / "USER_MANUAL.md"
HELP_PAGE_PATH = REPO_ROOT / "frontend" / "app" / "help" / "page.tsx"
INCIDENT_PATH = REPO_ROOT / "docs" / "INCIDENT.md"

# `| <7~8 hex> |` (마지막 column) 형식 매칭. 표 row 마지막 셀에 단독 hash만 있을 때.
COMMIT_HASH_RE = re.compile(r"\|\s*([0-9a-f]{7,8})\s*\|")

# USER_MANUAL.md: `### N.M ...` (예: "### 3.1 대시보드 ..."). MULTILINE — `^`가 줄 시작.
MANUAL_SECTION_RE = re.compile(r"^###\s+(\d+\.\d+)\s", re.MULTILINE)

# /help page: `<H3>N.M ...</H3>`
HELP_SECTION_RE = re.compile(r"<H3>(\d+\.\d+)\s")

# INCIDENT.md 체크리스트: `- [ ]` 또는 `- [x]` 만 valid. 그 외(`- [X]`, `- []`,
# `- [xx]` 등) 오타 검출.
CHECKLIST_VALID_RE = re.compile(r"^- \[[ x]\] ", re.MULTILINE)
CHECKLIST_ANY_RE = re.compile(r"^- \[", re.MULTILINE)


def _git_exists(hash_: str) -> bool:
    """git rev-parse로 해당 hash가 현재 repo에 존재하는지 확인."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", f"{hash_}^{{commit}}"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0
    except FileNotFoundError:
        print("git 명령을 찾을 수 없습니다 (PATH 확인)", file=sys.stderr)
        sys.exit(2)


def _check_status_commit_hashes() -> int:
    """1단계: STATUS.md commit hash가 git log에 존재 검증 (PR-EE)."""
    if not STATUS_PATH.is_file():
        print(f"STATUS.md 없음: {STATUS_PATH}", file=sys.stderr)
        return 2

    lines = STATUS_PATH.read_text(encoding="utf-8").splitlines()

    seen: set[str] = set()
    missing: list[tuple[int, str]] = []
    checked = 0

    for lineno, line in enumerate(lines, start=1):
        # 한 row에 hash가 여러 개 있을 수 있음 (예: "725d459 | a36642a") 모두 검사
        for match in COMMIT_HASH_RE.finditer(line):
            h = match.group(1)
            if h in seen:
                continue
            seen.add(h)
            checked += 1
            if not _git_exists(h):
                missing.append((lineno, h))

    if missing:
        print(f"[FAIL] STATUS.md에서 git log에 없는 commit hash {len(missing)}개:")
        for lineno, h in missing:
            print(f"  line {lineno}: {h}")
        return 1

    print(f"[OK] STATUS.md commit hash {checked}개 모두 git log에 존재")
    return 0


def _check_user_manual_help_sync() -> int:
    """2단계: USER_MANUAL.md ↔ /help page 섹션 번호 set 일치 (PR-EF)."""
    if not USER_MANUAL_PATH.is_file():
        print(f"USER_MANUAL.md 없음: {USER_MANUAL_PATH}", file=sys.stderr)
        return 2
    if not HELP_PAGE_PATH.is_file():
        print(f"/help page 없음: {HELP_PAGE_PATH}", file=sys.stderr)
        return 2

    manual_text = USER_MANUAL_PATH.read_text(encoding="utf-8")
    help_text = HELP_PAGE_PATH.read_text(encoding="utf-8")

    manual_sections = {m.group(1) for m in MANUAL_SECTION_RE.finditer(manual_text)}
    help_sections = {m.group(1) for m in HELP_SECTION_RE.finditer(help_text)}

    only_in_manual = sorted(manual_sections - help_sections)
    only_in_help = sorted(help_sections - manual_sections)

    if only_in_manual or only_in_help:
        print(
            f"[FAIL] USER_MANUAL.md ({len(manual_sections)}개) ↔ /help page "
            f"({len(help_sections)}개) 섹션 번호 불일치:"
        )
        if only_in_manual:
            print(f"  USER_MANUAL에만 있음: {', '.join(only_in_manual)}")
        if only_in_help:
            print(f"  /help page에만 있음: {', '.join(only_in_help)}")
        return 1

    print(
        f"[OK] USER_MANUAL.md ↔ /help page 섹션 번호 일치 "
        f"({len(manual_sections)}개)"
    )
    return 0


def _check_incident_checklist_format() -> int:
    """3단계: INCIDENT.md 체크리스트 항목 형식 검증 (PR-EH, 4-H 4단계).

    valid: `- [ ] ...` 또는 `- [x] ...` (소문자 x, 정확히 한 칸 padding)
    invalid 예: `- []`, `- [X]`, `- [ x]`, `- [xx]` 등 (오타로 GitHub 렌더 안 됨)
    미완료(- [ ])는 정보용으로 카운트만 표시.
    """
    if not INCIDENT_PATH.is_file():
        print(f"INCIDENT.md 없음: {INCIDENT_PATH}", file=sys.stderr)
        return 2

    lines = INCIDENT_PATH.read_text(encoding="utf-8").splitlines()

    invalid: list[tuple[int, str]] = []
    valid = 0
    pending = 0

    for lineno, line in enumerate(lines, start=1):
        if not line.startswith("- ["):
            continue
        if CHECKLIST_VALID_RE.match(line + "\n"):
            valid += 1
            if line.startswith("- [ ]"):
                pending += 1
        else:
            invalid.append((lineno, line[:80]))

    if invalid:
        print(f"[FAIL] INCIDENT.md 체크리스트 형식 오류 {len(invalid)}건:")
        for lineno, snippet in invalid:
            print(f"  line {lineno}: {snippet!r}")
        return 1

    pending_note = f", 미완료 {pending}개" if pending else ""
    print(f"[OK] INCIDENT.md 체크리스트 형식 {valid}개 모두 valid{pending_note}")
    return 0


def main() -> int:
    rc = 0
    checks = (
        _check_status_commit_hashes,
        _check_user_manual_help_sync,
        _check_incident_checklist_format,
    )
    for check in checks:
        result = check()
        if result == 2:
            return 2  # 접근 실패는 즉시 종료
        rc = rc or result
    return rc


if __name__ == "__main__":
    sys.exit(main())
