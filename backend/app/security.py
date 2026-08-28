"""安全工具：密码摘要、验证码、JWT。"""
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional

import jwt

from . import config

ALGORITHM = "HS256"


def password_digest(password: str) -> str:
    """sha512 摘要，与 SECRET_KEY 绑定（对应 plan：账号信息经过 sha512 处理）。"""
    inner = hashlib.sha512(password.encode("utf-8")).hexdigest()
    return hashlib.sha512((inner + config.SECRET_KEY).encode("utf-8")).hexdigest()


def verify_password(password: str, expected_digest: Optional[str]) -> bool:
    if not expected_digest:
        return False
    return secrets.compare_digest(password_digest(password), expected_digest)


def create_code() -> str:
    return "%06d" % secrets.randbelow(1_000_000)


def create_token(payload: dict, days: Optional[int] = None) -> str:
    expire = datetime.utcnow() + timedelta(days=days or config.JWT_TTL_DAYS)
    data = dict(payload)
    data["exp"] = expire
    return jwt.encode(data, config.SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, config.SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
