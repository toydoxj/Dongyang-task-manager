"""인증 라우터 — 회원가입(최초 관리자/승인 신청), 로그인, 사용자 관리."""
from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

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

router = APIRouter(prefix="/auth", tags=["auth"])


def _to_info(u: User) -> UserInfo:
    return UserInfo.model_validate(u)


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
    db.commit()
    token = create_token(user.username, user.role, sid)
    return TokenResponse(access_token=token, user=_to_info(user))


@router.get("/me", response_model=UserInfo)
def get_me(user: User = Depends(get_current_user)) -> UserInfo:
    return _to_info(user)


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
    db.commit()
    db.refresh(user)
    return _to_info(user)


# ── 관리자/공개 ──


@router.post("/request")
def request_join(body: RegisterRequest, db: Session = Depends(get_db)) -> dict[str, str]:
    """가입 신청 — pending 상태로 저장."""
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="이미 존재하는 아이디입니다"
        )
    user = User(
        username=body.username,
        password=hash_password(body.password),
        name=body.name,
        email=str(body.email),
        role="user",
        status="pending",
    )
    db.add(user)
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
        role="user",
        status="active",
    )
    db.add(user)
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
