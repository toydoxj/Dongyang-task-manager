"""사용자 ↔ 직원 자동 매칭 (이메일 기준)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.auth import User
from app.models.employee import Employee


def link_user_to_employee(db: Session, user: User) -> Employee | None:
    """user.email로 employees 매칭. 매칭 시 양쪽 연결, name 보정.

    호출자가 db.commit() 책임. 매칭 결과 반환 (없으면 None).
    """
    if not user.email:
        return None
    emp = db.query(Employee).filter(Employee.email == user.email).first()
    if emp is None:
        return None
    emp.linked_user_id = user.id
    # 사용자가 이름을 비워두고 신청했으면 직원 명부 이름으로 보정
    if not user.name and emp.name:
        user.name = emp.name
    return emp


def link_employee_to_user(db: Session, emp: Employee) -> User | None:
    """employee.email로 users 매칭. admin이 직원 이메일을 나중에 채운 경우.

    호출자가 db.commit() 책임.
    """
    if not emp.email:
        return None
    user = db.query(User).filter(User.email == emp.email).first()
    if user is None:
        return None
    emp.linked_user_id = user.id
    return user
