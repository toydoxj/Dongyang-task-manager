"""인증 라우터 — 회원가입(최초 관리자/승인 신청), 로그인, 사용자 관리."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

VALID_ROLES = {"admin", "team_lead", "member"}

from app.db import get_db
from app.models.auth import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    User,
    UserInfo,
    UserUpdateRequest,
)
from app.security import (
    create_token,
    get_current_user,
    hash_password,
    require_admin,
    verify_password,
)
from app.services.employee_link import link_user_to_employee

router = APIRouter(prefix="/auth", tags=["auth"])


def _to_info(u: User) -> UserInfo:
    """midas_key 같은 비밀값은 응답에서 제외 (has_midas_key boolean만 노출)."""
    return UserInfo(
        id=u.id,
        username=u.username,
        name=u.name or "",
        email=u.email or "",
        role=u.role or "member",
        status=u.status or "active",
        notion_user_id=u.notion_user_id or "",
        midas_url=u.midas_url or "",
        has_midas_key=bool(u.midas_key),
        work_dir=u.work_dir or "",
        last_login_at=u.last_login_at,
    )


@router.get("/status")
def auth_status(db: Session = Depends(get_db)) -> dict[str, object]:
    """초기 설정 여부 확인."""
    count = db.query(User).count()
    return {"initialized": count > 0, "user_count": count}


@router.post("/register", response_model=TokenResponse)
def register(body: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """최초 1인만 직접 등록(관리자), 이후엔 /auth/request 또는 /auth/users 사용."""
    if db.query(User).count() > 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="관리자를 통해 등록해주세요"
        )
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="이미 존재하는 아이디입니다"
        )

    sid = uuid4().hex
    user = User(
        username=body.username,
        password=hash_password(body.password),
        name=body.name,
        email=str(body.email),
        role="admin",
        status="active",
        session_id=sid,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_token(user.username, user.role, sid)
    return TokenResponse(access_token=token, user=_to_info(user))


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.query(User).filter(User.username == body.username).first()
    if not user or not verify_password(body.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="아이디 또는 비밀번호가 올바르지 않습니다",
        )
    if user.status == "pending":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="가입 승인 대기 중입니다. 관리자에게 문의하세요.",
        )
    if user.status == "rejected":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="가입이 거절되었습니다."
        )

    sid = uuid4().hex
    user.session_id = sid
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    token = create_token(user.username, user.role, sid)
    return TokenResponse(access_token=token, user=_to_info(user))


@router.get("/me", response_model=UserInfo)
def get_me(user: User = Depends(get_current_user)) -> UserInfo:
    return _to_info(user)


@router.get("/me/midas")
def get_my_midas_credentials(user: User = Depends(get_current_user)) -> dict:
    """본인의 MIDAS 자격 반환 (DY_MIDAS Electron sidecar 용).

    midas_key는 일반 /me에는 노출되지 않으나 본 endpoint는 인증된 본인에게만
    자기 값을 반환. SSO 위임 패턴에서 sidecar가 사용자별 설정을 적용하는 데 사용.
    """
    return {
        "midas_url": user.midas_url or "",
        "midas_key": user.midas_key or "",
        "work_dir": user.work_dir or "",
    }


@router.put("/me", response_model=UserInfo)
def update_me(
    body: UserUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserInfo:
    if body.name is not None:
        user.name = body.name
    if body.email is not None:
        user.email = str(body.email)
    if body.password is not None:
        user.password = hash_password(body.password)
    if body.notion_user_id is not None:
        user.notion_user_id = body.notion_user_id
    if body.midas_url is not None:
        user.midas_url = body.midas_url
    if body.midas_key is not None:
        user.midas_key = body.midas_key
    if body.work_dir is not None:
        user.work_dir = body.work_dir
    db.commit()
    db.refresh(user)
    return _to_info(user)


# ── 관리자/공개 ──


@router.post("/request")
def request_join(body: RegisterRequest, db: Session = Depends(get_db)) -> dict[str, str]:
    """가입 신청 — 이메일이 직원 명부에 있으면 즉시 자동 승인 + 매칭, 아니면 pending."""
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="이미 존재하는 아이디입니다"
        )
    user = User(
        username=body.username,
        password=hash_password(body.password),
        name=body.name,
        email=str(body.email),
        role="member",
        status="pending",
    )
    db.add(user)
    db.flush()  # user.id 확보
    emp = link_user_to_employee(db, user)
    if emp is not None:
        user.status = "active"
        db.commit()
        return {
            "status": "active",
            "message": f"직원 명부에서 확인되어 자동 승인되었습니다 ({emp.team or emp.position}).",
        }
    db.commit()
    return {
        "status": "pending",
        "message": "가입 신청이 완료되었습니다. 관리자 승인을 기다려주세요.",
    }


@router.post("/users", response_model=UserInfo)
def admin_create_user(
    body: RegisterRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserInfo:
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="이미 존재하는 아이디입니다"
        )
    user = User(
        username=body.username,
        password=hash_password(body.password),
        name=body.name,
        email=str(body.email),
        role="member",
        status="active",
    )
    db.add(user)
    db.flush()
    link_user_to_employee(db, user)
    db.commit()
    db.refresh(user)
    return _to_info(user)


@router.get("/users", response_model=list[UserInfo])
def list_users(
    admin: User = Depends(require_admin), db: Session = Depends(get_db)
) -> list[UserInfo]:
    return [_to_info(u) for u in db.query(User).order_by(User.id).all()]


@router.post("/users/{user_id}/approve", response_model=UserInfo)
def approve_user(
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserInfo:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="사용자를 찾을 수 없습니다"
        )
    user.status = "active"
    # 승인 시점에 직원 매칭 재시도 (admin이 employee 이메일을 그 사이에 추가했을 수 있음)
    link_user_to_employee(db, user)
    db.commit()
    db.refresh(user)
    return _to_info(user)


class RoleUpdate(BaseModel):
    role: Literal["admin", "team_lead", "member"]


@router.patch("/users/{user_id}/role", response_model=UserInfo)
def set_user_role(
    user_id: int,
    body: RoleUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserInfo:
    """admin이 사용자 권한 변경. 자기 자신을 강등(admin → 다른 role)할 때는
    다른 admin이 최소 1명 남아 있어야 한다."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="사용자를 찾을 수 없습니다"
        )
    if body.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail="잘못된 role")
    if (
        admin.id == user.id
        and user.role == "admin"
        and body.role != "admin"
    ):
        other_admin = (
            db.query(User)
            .filter(User.role == "admin", User.id != user.id)
            .first()
        )
        if not other_admin:
            raise HTTPException(
                status_code=400, detail="마지막 관리자는 강등할 수 없습니다"
            )
    user.role = body.role
    db.commit()
    db.refresh(user)
    return _to_info(user)


@router.post("/users/{user_id}/reject")
def reject_user(
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="사용자를 찾을 수 없습니다"
        )
    user.status = "rejected"
    db.commit()
    return {"status": "rejected"}


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    if admin.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="자기 자신은 삭제할 수 없습니다"
        )
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="사용자를 찾을 수 없습니다"
        )
    db.delete(user)
    db.commit()
    return {"status": "deleted"}
