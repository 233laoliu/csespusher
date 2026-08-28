"""认证路由：注册（邮箱+用户名+密码）、登录（邮箱+验证码）。"""
import re
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import config, schemas
from ..db import get_db
from ..deps import get_current_user
from ..email_util import send_verification_email
from ..models import User, VerificationCode
from ..security import create_code, create_token, password_digest

router = APIRouter(prefix="/api/auth", tags=["auth"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_email(email: str) -> str:
    email = (email or "").strip().lower()
    if not _EMAIL_RE.match(email) or len(email) > 255:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "邮箱格式不正确")
    return email


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(body: schemas.RegisterRequest, db: Session = Depends(get_db)):
    """邮箱 + 用户名注册。账号信息经 sha512 摘要存储。"""
    email = _validate_email(body.email)
    username = body.username.strip()
    if not username:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "用户名不能为空")
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "该邮箱已注册")
    user = User(
        email=email,
        username=username,
        password_hash=password_digest(body.password),
        role="admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"id": user.id, "email": user.email, "username": user.username, "role": user.role}


@router.post("/send-code")
def send_code(body: schemas.SendCodeRequest, db: Session = Depends(get_db)):
    """发送登录验证码（未配置 SMTP 时打印到控制台）。"""
    email = _validate_email(body.email)
    if body.purpose == "login":
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "该邮箱未注册")
        if not user.is_active:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "账号已被停用")
    code = create_code()
    db.add(VerificationCode(
        email=email,
        code=code,
        expires_at=datetime.utcnow() + timedelta(seconds=config.CODE_TTL_SECONDS),
    ))
    db.commit()
    method = send_verification_email(email, code)
    return {"sent": True, "channel": method}


@router.post("/login", response_model=schemas.LoginResponse)
def login(body: schemas.LoginRequest, db: Session = Depends(get_db)):
    """邮箱 + 验证码登录；登录时校验账号摘要完整性。"""
    email = _validate_email(body.email)
    code = (body.code or "").strip()
    user = db.query(User).filter(User.email == email).first()
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "邮箱或验证码不正确")

    record = (
        db.query(VerificationCode)
        .filter(
            VerificationCode.email == email,
            VerificationCode.code == code,
            VerificationCode.consumed == False,  # noqa: E712
            VerificationCode.expires_at > datetime.utcnow(),
        )
        .order_by(VerificationCode.id.desc())
        .first()
    )
    if record is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "邮箱或验证码不正确")
    record.consumed = True

    # 登录时校验账号信息（sha512 摘要）
    if not user.password_hash or len(user.password_hash) != 128:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "账号数据异常")

    db.commit()
    token = create_token({"sub": str(user.id), "role": user.role, "email": user.email})
    return {"token": token, "user": schemas.UserOut.model_validate(user)}


@router.get("/me", response_model=schemas.MeOut)
def me(user: User = Depends(get_current_user)):
    return schemas.MeOut.model_validate(user)
