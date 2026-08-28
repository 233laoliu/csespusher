"""超管路由：用户管理 + 平台运行状态。"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import schemas
from ..db import get_db
from ..deps import require_superadmin
from ..models import School, ShareLink, User, VerificationCode

router = APIRouter(prefix="/api/super", tags=["super"])


@router.get("/stats")
def platform_stats(db: Session = Depends(get_db), user: User = Depends(require_superadmin)):
    """平台运行状态概览。"""
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)
    return {
        "users_total": db.query(func.count(User.id)).scalar(),
        "schools_total": db.query(func.count(School.id)).scalar(),
        "shares_total": db.query(func.count(ShareLink.id)).scalar(),
        "shares_week": db.query(func.count(ShareLink.id))
        .filter(ShareLink.created_at >= week_ago).scalar(),
        "codes_sent_24h": db.query(func.count(VerificationCode.id))
        .filter(VerificationCode.created_at >= now - timedelta(hours=24)).scalar(),
    }


@router.get("/users")
def list_users(db: Session = Depends(get_db), user: User = Depends(require_superadmin)):
    users = db.query(User).order_by(User.id).all()
    out = []
    for u in users:
        out.append({
            **schemas.UserOut.model_validate(u).model_dump(),
            "schools_count": db.query(func.count(School.id))
            .filter(School.owner_id == u.id).scalar(),
        })
    return out


class UserPatch(BaseModel):
    role: str = None  # admin | superadmin
    is_active: bool = None
    username: str = None


@router.put("/users/{user_id}")
def patch_user(user_id: int, body: UserPatch, db: Session = Depends(get_db),
               user: User = Depends(require_superadmin)):
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")
    if body.role is not None:
        if body.role not in ("admin", "superadmin"):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "role 必须是 admin 或 superadmin")
        if target.id == user.id and body.role != "superadmin":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "不能降级自己")
        target.role = body.role
    if body.is_active is not None:
        if target.id == user.id and not body.is_active:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "不能停用自己")
        target.is_active = body.is_active
    if body.username is not None and body.username.strip():
        target.username = body.username.strip()
    db.commit()
    return schemas.UserOut.model_validate(target)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, db: Session = Depends(get_db),
                user: User = Depends(require_superadmin)):
    if user_id == user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "不能删除自己")
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")
    # 移交其名下学校给超管
    for school in db.query(School).filter(School.owner_id == user_id).all():
        school.owner_id = user.id
    db.delete(target)
    db.commit()
