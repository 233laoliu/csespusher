"""FastAPI 依赖：从 JWT 解析当前用户 / 角色检查。"""
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .db import get_db
from .models import School, SchoolMember, User
from .security import decode_token

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or not credentials.credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "未登录")
    payload = decode_token(credentials.credentials)
    if payload is None or "sub" not in payload:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "登录已过期，请重新登录")
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "账号不可用")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role not in ("admin", "superadmin"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "需要管理员权限")
    return user


def require_superadmin(user: User = Depends(get_current_user)) -> User:
    if user.role != "superadmin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "需要超级管理员权限")
    return user


def can_edit_school(db: Session, user: User, school: School) -> None:
    """普通管理员需为创建者或协作成员；超管放行。"""
    if user.role == "superadmin":
        return
    if school.owner_id == user.id:
        return
    member = (
        db.query(SchoolMember)
        .filter(SchoolMember.school_id == school.id, SchoolMember.user_id == user.id)
        .first()
    )
    if member is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "没有该学校的编辑权限")
