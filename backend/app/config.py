"""集中读取环境变量配置（支持 .env 文件）。"""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

BASE_DIR = Path(__file__).resolve().parent.parent
_data_dir = BASE_DIR / "data"
_data_dir.mkdir(exist_ok=True)

_env_file = BASE_DIR / ".env"
if _env_file.exists() and load_dotenv is not None:
    load_dotenv(_env_file)


def _get(key: str, default: str = "") -> str:
    value = os.environ.get(key)
    return default if value is None else value


def _get_int(key: str, default: int) -> int:
    raw = os.environ.get(key)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


SECRET_KEY = _get("SECRET_KEY", "dev-secret-change-me")
DATABASE_URL = _get("DATABASE_URL", "sqlite:///" + (_data_dir / "app.db").as_posix())

SMTP_HOST = _get("SMTP_HOST")
SMTP_PORT = _get_int("SMTP_PORT", 465)
SMTP_USER = _get("SMTP_USER")
SMTP_PASS = _get("SMTP_PASS")
SMTP_FROM = _get("SMTP_FROM", SMTP_USER)
SMTP_USE_TLS = _get("SMTP_USE_TLS", "1") == "1"

CODE_TTL_SECONDS = _get_int("CODE_TTL_SECONDS", 300)
JWT_TTL_DAYS = _get_int("JWT_TTL_DAYS", 7)

SUPERADMIN_EMAIL = _get("SUPERADMIN_EMAIL").strip().lower()
SUPERADMIN_USERNAME = _get("SUPERADMIN_USERNAME", "超级管理员")

CONTACT_EMAIL = _get("CONTACT_EMAIL")
GITHUB_URL = _get("GITHUB_URL", "https://github.com/SmartTeachCN/CSES")
CLASSISLAND_RELEASE_URL = _get(
    "CLASSISLAND_RELEASE_URL", "https://github.com/ClassIsland/ClassIsland/releases/latest"
)
CLASSWIDGETS_RELEASE_URL = _get(
    "CLASSWIDGETS_RELEASE_URL",
    "https://github.com/Class-Widgets/Class-Widgets/releases/latest",
)
