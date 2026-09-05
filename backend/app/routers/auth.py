"""认证路由：注册验证码、邮箱密码登录、密码找回。"""
import re
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import config, schemas
from ..db import get_db
from ..deps import get_current_user
from ..email_util import send_code_email
from ..models import User, VerificationCode
from ..security import create_code, create_token, password_digest, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_email(email: str) -> str:
    email = (email or "").strip().lower()
    if not _EMAIL_RE.match(email) or len(email) > 255:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "邮箱格式不正确")
    return email


def _issue_code(db: Session, email: str, purpose: str) -> str:
    code = create_code()
    db.add(VerificationCode(email=email, code=code,
                            expires_at=datetime.utcnow() + timedelta(seconds=config.CODE_TTL_SECONDS)))
    db.commit()
    send_code_email(email, code, purpose)
    return code


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(body: schemas.RegisterRequest, db: Session = Depends(get_db)):
    email = _validate_email(body.email)
    username = body.username.strip()
    if not username:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "用户名不能为空")
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "该邮箱已注册")
    user = User(email=email, username=username, password_hash=password_digest(body.password), role="admin")
    db.add(user)
    db.commit()
    db.refresh(user)
    _issue_code(db, email, "register")
    return {"id": user.id, "email": user.email, "username": user.username, "role": user.role}


@router.post("/send-code")
def send_code(body: schemas.SendCodeRequest, db: Session = Depends(get_db)):
    email = _validate_email(body.email)
    purpose = body.purpose if body.purpose in ("register", "reset") else "register"
    user = db.query(User).filter(User.email == email).first()
    if purpose == "register" and user is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "该邮箱已注册，请直接登录或找回密码")
    if purpose == "reset" and (user is None or not user.is_active):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "该邮箱未注册")
    _issue_code(db, email, purpose)
    return {"sent": True, "channel": "smtp" if config.SMTP_HOST and config.SMTP_USER else "console"}


@router.post("/login", response_model=schemas.LoginResponse)
def login(body: schemas.LoginRequest, db: Session = Depends(get_db)):
    email = _validate_email(body.email)
    user = db.query(User).filter(User.email == email).first()
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "邮箱或密码不正确")
    token = create_token({"sub": str(user.id), "role": user.role, "email": user.email})
    return {"token": token, "user": schemas.UserOut.model_validate(user)}


@router.post("/reset-password")
def reset_password(body: schemas.ResetPasswordRequest, db: Session = Depends(get_db)):
    email = _validate_email(body.email)
    user = db.query(User).filter(User.email == email).first()
    record = db.query(VerificationCode).filter(
        VerificationCode.email == email, VerificationCode.code == body.code.strip(),
        VerificationCode.consumed == False, VerificationCode.expires_at > datetime.utcnow(),
    ).order_by(VerificationCode.id.desc()).first()
    if user is None or record is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "邮箱或验证码不正确")
    user.password_hash = password_digest(body.password)
    record.consumed = True
    db.commit()
    return {"reset": True}


@router.get("/me", response_model=schemas.MeOut)
def me(user: User = Depends(get_current_user)):
    return schemas.MeOut.model_validate(user)
