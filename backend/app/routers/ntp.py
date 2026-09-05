"""NTP 时间同步：管理员配置接口 + 公开时间接口。

每所学校一个 UDP 端口（NTP 报文本身无法区分学校，只能用端口区分），
另配一个 HTTP 时间接口作为不支持自定义端口的客户端的兜底方案。
"""
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from .. import config as app_config
from .. import ntp as ntp_util
from .. import schemas
from ..db import get_db
from ..deps import can_edit_school, require_admin
from ..models import NtpServer, School, SchoolMember, User
from ..ntp import ntp_service

admin_router = APIRouter(prefix="/api/admin", tags=["ntp"])
public_router = APIRouter(prefix="/api/public", tags=["ntp-public"])


# ---------------- 工具 ----------------


def _get_school(db: Session, school_id: int) -> School:
    school = db.get(School, school_id)
    if school is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "学校不存在")
    return school


def _public_host(request: Optional[Request]) -> str:
    """对外展示用的主机名（实现在 app/ntp.py，避免与 app.config 耦合）。"""
    return ntp_util.public_host(request)


def _ntp_out(row: NtpServer, request: Optional[Request] = None) -> dict:
    now = time.time()
    real_ts, school_ts, off = ntp_util.school_now(row, now)
    host = _public_host(request)
    return {
        "id": row.id,
        "school_id": row.school_id,
        "token": row.token,
        "enabled": bool(row.enabled),
        "port": row.port,
        "host": host,
        "ntp_address": "%s:%s" % (host, row.port),
        "http_time_url": "/api/public/ntp/%s/time" % row.token,
        "daily_offset_ms": row.daily_offset_ms,
        "base_offset_ms": row.base_offset_ms,
        "base_time": row.base_time,
        "timezone": row.timezone,
        "note": row.note,
        "current_offset_ms": round(off * 1000, 1),
        "real_time": ntp_util.format_local(real_ts, row.timezone),
        "school_time": ntp_util.format_local(school_ts, row.timezone),
        "school_unix_ms": int(round(school_ts * 1000)),
        "listening": ntp_service.is_listening(row.port),
        "service_enabled": app_config.NTP_ENABLED,
        "updated_at": row.updated_at,
    }


def _draft_out(db: Session, school: School, request: Optional[Request] = None) -> dict:
    """尚未创建 NTP 服务时的草稿（不落库）。"""
    try:
        port = ntp_util.allocate_port(db)
    except RuntimeError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    return {
        "exists": False,
        "suggested_port": port,
        "timezone": app_config.NTP_DEFAULT_TIMEZONE,
        "host": _public_host(request),
        "service_enabled": app_config.NTP_ENABLED,
        "base_port": app_config.NTP_BASE_PORT,
        "timezones": ntp_util.TIMEZONE_CHOICES,
    }


def _parse_school_time(text: str, tz_name: str, now: float) -> float:
    """把管理员填的学校墙钟时间解析成 UTC 时间戳。

    支持 "HH:MM:SS"（按学校时区的今天）与 "YYYY-MM-DD HH:MM:SS"。
    与真实时间相差超过 12 小时时自动向前/向后借一天，避免跨零点填错日期。
    """
    raw = (text or "").strip().replace("T", " ")
    if not raw:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "请填写学校时钟当前显示的时间")
    tz_off = ntp_util.tz_offset_seconds(tz_name, now)
    school_tz = timezone(timedelta(seconds=tz_off))
    try:
        if "-" in raw:
            naive = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
        else:
            today = datetime.fromtimestamp(now + tz_off).strftime("%Y-%m-%d")
            naive = datetime.strptime("%s %s" % (today, raw), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:  # 允许只填到分钟
            if "-" in raw:
                naive = datetime.strptime(raw, "%Y-%m-%d %H:%M")
            else:
                today = datetime.fromtimestamp(now + tz_off).strftime("%Y-%m-%d")
                naive = datetime.strptime("%s %s" % (today, raw), "%Y-%m-%d %H:%M")
        except ValueError:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "时间格式应为 HH:MM:SS 或 YYYY-MM-DD HH:MM:SS")
    target = naive.replace(tzinfo=school_tz).timestamp()
    if target - now > 12 * 3600:
        target -= 24 * 3600
    elif now - target > 12 * 3600:
        target += 24 * 3600
    return target


# ---------------- 管理接口 ----------------


@admin_router.get("/schools/{school_id}/ntp")
def get_ntp(school_id: int, request: Request, db: Session = Depends(get_db),
            user: User = Depends(require_admin)):
    school = _get_school(db, school_id)
    can_edit_school(db, user, school)
    row = db.query(NtpServer).filter(NtpServer.school_id == school_id).first()
    if row is None:
        return _draft_out(db, school, request)
    out = _ntp_out(row, request)
    out["exists"] = True
    out["timezones"] = ntp_util.TIMEZONE_CHOICES
    out["base_port"] = app_config.NTP_BASE_PORT
    return out


@admin_router.put("/schools/{school_id}/ntp")
async def save_ntp(school_id: int, body: schemas.NtpServerUpdate, request: Request,
                   db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """创建或更新学校 NTP 服务；首次调用即创建（自动分配端口与 token）。"""
    school = _get_school(db, school_id)
    can_edit_school(db, user, school)
    row = db.query(NtpServer).filter(NtpServer.school_id == school_id).first()
    created = row is None
    if created:
        row = NtpServer(school_id=school_id, port=ntp_util.allocate_port(db),
                        timezone=app_config.NTP_DEFAULT_TIMEZONE)
        db.add(row)
        db.flush()

    if body.enabled is not None:
        row.enabled = bool(body.enabled)
    if body.daily_offset_ms is not None:
        if abs(body.daily_offset_ms) > 24 * 3600 * 1000:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "每日偏移量过大（单日不得超过 24 小时）")
        row.daily_offset_ms = int(body.daily_offset_ms)
    if body.timezone is not None:
        row.timezone = body.timezone.strip() or app_config.NTP_DEFAULT_TIMEZONE
    if body.note is not None:
        row.note = body.note[:2000]
    if body.port is not None and body.port != row.port:
        other = db.query(NtpServer).filter(
            NtpServer.port == body.port, NtpServer.id != row.id).first()
        if other is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "端口 %s 已被其它学校占用" % body.port)
        row.port = body.port
    row.updated_by = user.id
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)

    if app_config.NTP_ENABLED:
        await ntp_service.refresh()
    out = _ntp_out(row, request)
    out["exists"] = True
    out["created"] = created
    out["timezones"] = ntp_util.TIMEZONE_CHOICES
    return out


@admin_router.delete("/schools/{school_id}/ntp", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ntp(school_id: int, db: Session = Depends(get_db),
                     user: User = Depends(require_admin)):
    """删除学校 NTP 服务（释放端口）。"""
    school = _get_school(db, school_id)
    can_edit_school(db, user, school)
    row = db.query(NtpServer).filter(NtpServer.school_id == school_id).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "该校尚未创建 NTP 服务")
    db.delete(row)
    db.commit()
    if app_config.NTP_ENABLED:
        await ntp_service.refresh()


@admin_router.post("/schools/{school_id}/ntp/calibrate")
async def calibrate_ntp(school_id: int, body: schemas.NtpCalibrateRequest, request: Request,
                        db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """手动校准：填入学校时钟此刻的读数，立即把偏差抹平。

    做法是把当前累积误差整体吸收进 base_offset_ms，并把 base_time 推进到当下；
    daily_offset_ms 保持不变（除非 keep_daily_offset=False，则一并按实测值反推）。
    """
    school = _get_school(db, school_id)
    can_edit_school(db, user, school)
    row = db.query(NtpServer).filter(NtpServer.school_id == school_id).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "该校尚未创建 NTP 服务")

    now = time.time()
    target = _parse_school_time(body.school_time, row.timezone, now)
    delta_ms = int(round((target - now) * 1000))
    if abs(delta_ms) > 7 * 24 * 3600 * 1000:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "校准偏差过大，请确认填写的时间")

    if not body.keep_daily_offset:
        # 用「已运行天数」反推日均偏移：base 归零，全部偏差由 daily 承担
        elapsed_days = max(1.0, (now - ntp_util._dt_to_ts(row.base_time)) / 86400.0)
        row.daily_offset_ms = int(round(delta_ms / elapsed_days))
        row.base_offset_ms = 0
    else:
        row.base_offset_ms = delta_ms
    row.base_time = datetime.utcnow()  # 基准推进到当下，误差已被吸收
    row.updated_by = user.id
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    if app_config.NTP_ENABLED:
        await ntp_service.refresh()
    out = _ntp_out(row, request)
    out["exists"] = True
    out["applied_offset_ms"] = delta_ms
    return out


@admin_router.post("/schools/{school_id}/ntp/reset")
async def reset_ntp(school_id: int, request: Request, db: Session = Depends(get_db),
                    user: User = Depends(require_admin)):
    """清零：取消当前偏差，并可选择同时清空每日偏移量。"""
    school = _get_school(db, school_id)
    can_edit_school(db, user, school)
    row = db.query(NtpServer).filter(NtpServer.school_id == school_id).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "该校尚未创建 NTP 服务")
    row.base_offset_ms = 0
    row.base_time = datetime.utcnow()
    row.updated_by = user.id
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    if app_config.NTP_ENABLED:
        await ntp_service.refresh()
    out = _ntp_out(row, request)
    out["exists"] = True
    return out


@admin_router.get("/ntp/status")
def ntp_status(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """NTP 服务运行状态：普通管理员只看自己的学校，超管看全部。"""
    items = ntp_service.status(db)
    if user.role != "superadmin":
        mine = {m.school_id for m in
                db.query(SchoolMember).filter(SchoolMember.user_id == user.id).all()}
        mine |= {s.id for s in db.query(School).filter(School.owner_id == user.id).all()}
        items = [i for i in items if i["school_id"] in mine]
    return {
        "service_enabled": app_config.NTP_ENABLED,
        "running": ntp_service.running,
        "host": app_config.NTP_PUBLIC_HOST or "",
        "base_port": app_config.NTP_BASE_PORT,
        "started_at": ntp_service.started_at,
        "servers": items,
    }


# ---------------- 公开时间接口 ----------------


def _json(payload: dict) -> JSONResponse:
    """统一加 CORS 与禁用缓存头。"""
    return JSONResponse(content=payload, headers={
        "Access-Control-Allow-Origin": "*",
        "Cache-Control": "no-store, no-cache, must-revalidate",
    })


def _time_payload(row: NtpServer, request: Optional[Request] = None) -> dict:
    now = time.time()
    real_ts, school_ts, off = ntp_util.school_now(row, now)
    host = _public_host(request)
    return {
        "school_id": row.school_id,
        "school": row.school.name,
        "timezone": row.timezone,
        # 学校时间（已含偏移）的 Unix 毫秒时间戳，客户端据此校表
        "unix_ms": int(round(school_ts * 1000)),
        "unix": school_ts,
        "local": ntp_util.format_local(school_ts, row.timezone),
        "utc": datetime.fromtimestamp(school_ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.")
        + "%03dZ" % (int(round(school_ts * 1000)) % 1000),
        "real_unix_ms": int(round(real_ts * 1000)),
        "offset_ms": round(off * 1000, 1),
        "daily_offset_ms": row.daily_offset_ms,
        "stratum": ntp_util.STRATUM,
        "ntp": {"host": host, "port": row.port, "address": "%s:%s" % (host, row.port)},
    }


@public_router.get("/ntp/{token}")
def public_ntp_info(token: str, request: Request, db: Session = Depends(get_db)):
    """该校 NTP 服务的公开信息（名称、端口、当前偏移）。"""
    row = db.query(NtpServer).filter(NtpServer.token == token).first()
    if row is None or not row.enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "该校未启用时间同步服务")
    return _json(_time_payload(row, request))


@public_router.get("/ntp/{token}/time")
def public_ntp_time(token: str, request: Request, db: Session = Depends(get_db)):
    """该校当前时间（含累积偏移），供软件通过 HTTP 校表。

    建议客户端记录往返：t0=发出前、t1=收到后，取 (t0+t1)/2 作为取样时刻。
    """
    row = db.query(NtpServer).filter(NtpServer.token == token).first()
    if row is None or not row.enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "该校未启用时间同步服务")
    return _json(_time_payload(row, request))


@public_router.get("/schools/{school_id}/ntp")
def public_school_ntp(school_id: int, request: Request, db: Session = Depends(get_db)):
    """按学校 id 查询时间同步信息（未启用时返回 null，便于班级页判断是否展示）。"""
    school = db.get(School, school_id)
    if school is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "学校不存在")
    row = db.query(NtpServer).filter(NtpServer.school_id == school_id).first()
    if row is None or not row.enabled:
        return _json({"enabled": False})
    payload = _time_payload(row, request)
    payload["enabled"] = True
    payload["token"] = row.token
    payload["http_time_url"] = "/api/public/ntp/%s/time" % row.token
    return _json(payload)
