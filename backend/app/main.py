"""FastAPI 应用入口。

启动：
    cd backend
    uvicorn app.main:app --reload --port 8000
"""
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import config as app_config
from .db import Base, SessionLocal, engine
from .models import User  # noqa: F401  确保模型注册
from .models import SchoolConfig, ExtraConfig, SchoolMember, ShareLink, NtpServer  # noqa: F401
from .ntp import ntp_service
from .routers import admin, auth, public, super as super_router
from .routers import ntp as ntp_router
from .security import password_digest


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时拉起每校独立的 NTP 服务，关闭时释放全部 UDP 端口。"""
    if app_config.NTP_ENABLED:
        try:
            await ntp_service.start()
        except Exception as e:  # 端口被占用等不应拖垮 Web 服务
            print("[csespusher] NTP 服务启动失败：%r" % (e,))
    else:
        print("[csespusher] NTP 服务已通过 NTP_ENABLED=0 关闭")
    yield
    if app_config.NTP_ENABLED:
        await ntp_service.stop()


app = FastAPI(title="csespusher", version="0.1.0",
              description="CSES / ClassIsland / ClassWidgets 课程表配置分发平台",
              lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)


def _ensure_superadmin() -> None:
    """首次启动：若配置了 SUPERADMIN_EMAIL 且尚无超管，则创建之。"""
    email = app_config.SUPERADMIN_EMAIL
    if not email:
        return
    db = SessionLocal()
    try:
        has_super = db.query(User).filter(User.role == "superadmin").first()
        if has_super is None and db.query(User).filter(User.email == email).first() is None:
            db.add(User(
                email=email,
                username=app_config.SUPERADMIN_USERNAME or "超级管理员",
                # 超管初始密码摘要 = sha512("superadmin") —— 首次登录后请自行修改流程补充
                password_hash=password_digest("superadmin"),
                role="superadmin",
            ))
            db.commit()
            print("[csespusher] 已创建超级管理员：%s（初始密码摘要基于 'superadmin'）" % email)
    finally:
        db.close()


_ensure_superadmin()

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(public.router)
app.include_router(super_router.router)
app.include_router(ntp_router.admin_router)
app.include_router(ntp_router.public_router)


@app.get("/api/health")
def health():
    return {"ok": True}


# 生产模式：托管前端构建产物（含 SPA 回退）
_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _dist.exists():
    from fastapi.responses import FileResponse

    assets_dir = _dist / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    _index = _dist / "index.html"

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str):
        # /api 路由已优先匹配；其余路径返回 index.html 交给前端路由
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404)
        # index.html 不缓存：前端每次构建产物哈希会变，必须让浏览器重新校验，
        # 否则会一直用旧的 index.html（及其引用的旧 JS），出现“改了却没生效”。
        return FileResponse(
            str(_index),
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )
