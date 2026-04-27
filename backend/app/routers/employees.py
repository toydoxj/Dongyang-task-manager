"""/api/admin/employees — 직원 마스터 CRUD + 엑셀 import (admin only)."""
from __future__ import annotations

from datetime import date as Date
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.auth import User
from app.models.employee import (
    Employee,
    EmployeeCreate,
    EmployeeImportResult,
    EmployeeListResponse,
    EmployeeOut,
    EmployeeUpdate,
)
from app.security import get_current_user, require_admin, require_admin_or_lead
from app.services.employee_import import parse_workbook
from app.services.employee_link import link_employee_to_user

router = APIRouter(prefix="/admin/employees", tags=["employees"])

_MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5MB


@router.get("/teams-map")
def get_employee_teams_map(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """직원 이름 → 팀 매핑 (재직중만). 일반 사용자도 호출 가능 — 이름·팀만 노출."""
    rows = db.execute(
        select(Employee.name, Employee.team).where(Employee.resigned_at.is_(None))
    ).all()
    out: dict[str, str] = {}
    for name, team in rows:
        if name and team:
            out[name] = team
    return out


@router.get("", response_model=EmployeeListResponse)
def list_employees(
    q: str | None = Query(default=None, description="이름/이메일/소속 검색"),
    view: Literal["active", "resigned", "all"] = Query(
        default="active", description="재직중(기본)/퇴사자/전체"
    ),
    user: User = Depends(require_admin_or_lead),  # 팀장도 직원 명부 조회 가능
    db: Session = Depends(get_db),
) -> EmployeeListResponse:
    stmt = select(Employee)
    if view == "active":
        stmt = stmt.where(Employee.resigned_at.is_(None))
    elif view == "resigned":
        stmt = stmt.where(Employee.resigned_at.is_not(None))
    # 팀장은 본인 team의 직원만 (admin은 전체)
    if user.role == "team_lead":
        my_emp = (
            db.query(Employee).filter(Employee.linked_user_id == user.id).first()
        )
        my_team = (my_emp.team if my_emp else "") or ""
        if not my_team:
            return EmployeeListResponse(items=[], count=0)
        stmt = stmt.where(Employee.team == my_team)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                Employee.name.ilike(like),
                Employee.email.ilike(like),
                Employee.team.ilike(like),
            )
        )
    if view == "resigned":
        # 최근 퇴사자 우선
        stmt = stmt.order_by(
            Employee.resigned_at.desc(), Employee.name.asc()
        )
    else:
        stmt = stmt.order_by(Employee.team.asc(), Employee.name.asc())
    rows = db.execute(stmt).scalars().all()
    return EmployeeListResponse(
        items=[EmployeeOut.model_validate(r) for r in rows], count=len(rows)
    )


@router.post("/{emp_id}/resign", response_model=EmployeeOut)
def resign_employee(
    emp_id: int,
    on: Date | None = Query(default=None, description="퇴사일 (생략 시 오늘)"),
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> EmployeeOut:
    emp = db.get(Employee, emp_id)
    if emp is None:
        raise HTTPException(status_code=404, detail="직원을 찾을 수 없습니다")
    emp.resigned_at = on or Date.today()
    db.commit()
    db.refresh(emp)
    return EmployeeOut.model_validate(emp)


@router.post("/{emp_id}/restore", response_model=EmployeeOut)
def restore_employee(
    emp_id: int,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> EmployeeOut:
    emp = db.get(Employee, emp_id)
    if emp is None:
        raise HTTPException(status_code=404, detail="직원을 찾을 수 없습니다")
    emp.resigned_at = None
    db.commit()
    db.refresh(emp)
    return EmployeeOut.model_validate(emp)


@router.post("", response_model=EmployeeOut, status_code=status.HTTP_201_CREATED)
def create_employee(
    body: EmployeeCreate,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> EmployeeOut:
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="이름 필수")
    emp = Employee(
        name=body.name.strip(),
        position=body.position,
        team=body.team,
        degree=body.degree,
        license=body.license,
        grade=body.grade,
        email=body.email,
    )
    db.add(emp)
    db.flush()
    link_employee_to_user(db, emp)
    db.commit()
    db.refresh(emp)
    return EmployeeOut.model_validate(emp)


@router.patch("/{emp_id}", response_model=EmployeeOut)
def update_employee(
    emp_id: int,
    body: EmployeeUpdate,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> EmployeeOut:
    emp = db.get(Employee, emp_id)
    if emp is None:
        raise HTTPException(status_code=404, detail="직원을 찾을 수 없습니다")
    data = body.model_dump(exclude_unset=True)
    email_changed = "email" in data and data["email"] != emp.email
    for k, v in data.items():
        if v is None:
            continue
        setattr(emp, k, v)
    if email_changed:
        # 이메일 변경 → 새 이메일로 사용자 매칭 재시도 (이전 연결은 유지/덮어쓰기)
        link_employee_to_user(db, emp)
    db.commit()
    db.refresh(emp)
    return EmployeeOut.model_validate(emp)


@router.delete("/{emp_id}", status_code=204)
def delete_employee(
    emp_id: int,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    emp = db.get(Employee, emp_id)
    if emp is None:
        return
    db.delete(emp)
    db.commit()


@router.post("/upload", response_model=EmployeeImportResult)
async def upload_employees(
    file: UploadFile = File(...),
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> EmployeeImportResult:
    """엑셀 업로드 → 화이트리스트 컬럼만 in-memory parsing → upsert.

    매칭 키: 이메일이 있으면 이메일, 없으면 이름.
    """
    fname = (file.filename or "").lower()
    if not (fname.endswith(".xlsx") or fname.endswith(".xls")):
        raise HTTPException(status_code=400, detail="xlsx/xls 파일만 가능")
    content = await file.read()
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="5MB 초과")
    if not content:
        raise HTTPException(status_code=400, detail="빈 파일")

    try:
        parsed = parse_workbook(content)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=400, detail=f"엑셀 파싱 실패: {exc}"
        ) from exc

    inserted = 0
    updated = 0
    skipped = 0

    for p in parsed:
        existing: Employee | None = None
        if p.email:
            existing = db.execute(
                select(Employee).where(Employee.email == p.email)
            ).scalar_one_or_none()
        if existing is None:
            existing = db.execute(
                select(Employee).where(Employee.name == p.name)
            ).scalar_one_or_none()

        if existing is None:
            new_emp = Employee(
                name=p.name,
                position=p.position,
                team=p.team,
                degree=p.degree,
                license=p.license,
                grade=p.grade,
                email=p.email,
            )
            db.add(new_emp)
            db.flush()
            link_employee_to_user(db, new_emp)
            inserted += 1
        else:
            # 기존 값 보존: 엑셀에 빈 값이면 덮어쓰지 않음 (admin 보강분 보호)
            changed = False
            for field in ("position", "team", "degree", "license", "grade", "email"):
                new_val = getattr(p, field)
                if new_val and getattr(existing, field) != new_val:
                    setattr(existing, field, new_val)
                    changed = True
            if changed:
                # 이메일이 갱신됐을 수 있으므로 매칭 재시도
                link_employee_to_user(db, existing)
                updated += 1
            else:
                skipped += 1

    db.commit()
    return EmployeeImportResult(
        inserted=inserted,
        updated=updated,
        skipped=skipped,
        total_rows=len(parsed),
    )
