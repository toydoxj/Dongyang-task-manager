"""docs/ 일관성 audit (Phase 4-H 1단계, PR-EE).

repo root에서 `python scripts/docs_audit.py` 실행. stdlib만 사용 (venv 불필요).

검사 항목 (1단계 — commit hash 일관성):
  1. `docs/STATUS.md`에서 마지막 column에 등장하는 commit hash(7~8 chars)를 추출
  2. 각 hash가 git log에 실제 존재하는지 `git rev-parse` 로 검증
  3. 없는 hash가 있으면 line 번호 + hash 출력 후 exit 1

확장 후보 (별도 cycle):
- INCIDENT.md 추적 항목 형식 (`- [ ]` / `- [x]`)
- USER_MANUAL.md ↔ `frontend/app/help/page.tsx` 섹션 매칭
- PERMISSIONS.md 라우터 가드와 backend `require_*` 의존성 cross-check
- PR-XX prefix 일관성 (STATUS와 git commit message)

CI 통합:
- 추후 `.github/workflows/`에 추가해 PR 시점 자동 검증 가능 (현재는 수동 실행).

exit code:
  0 — 모든 hash가 git log에 존재
  1 — 일부 hash가 git log에 없음 (출력에 line 번호 + hash)
  2 — git/STATUS.md 접근 실패
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
STATUS_PATH = REPO_ROOT / "docs" / "STATUS.md"

# `| <7~8 hex> |` (마지막 column) 형식 매칭. 표 row 마지막 셀에 단독 hash만 있을 때.
COMMIT_HASH_RE = re.compile(r"\|\s*([0-9a-f]{7,8})\s*\|")


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


def main() -> int:
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
        print(f"STATUS.md에서 git log에 없는 commit hash {len(missing)}개 발견:")
        for lineno, h in missing:
            print(f"  line {lineno}: {h}")
        print(f"\n총 검사: {checked}개 hash. 누락: {len(missing)}개")
        return 1

    print(f"OK — STATUS.md commit hash {checked}개 모두 git log에 존재")
    return 0


if __name__ == "__main__":
    sys.exit(main())
