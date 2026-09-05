"""每校独立的 NTP 时间源。

背景：学校的打铃系统往往挂着一台走时不准的母钟，每天固定快/慢若干秒，
累积几周就足以让下课铃和学生软件上的课表错开好几分钟。
本模块为每所学校起一个独立的 NTP 服务端口，把「学校铃声时间」
（真实时间 + 该校累积偏移）作为权威时间广播出去，
学生机同步后即可与铃声保持一致。

两条获取途径：
1. NTP（UDP）—— 每校独占一个端口，NTP 报文本身不带任何学校标识，
   因此只能用端口区分学校；支持标准 NTP 客户端。
2. HTTP —— /api/public/ntp/{token}/time 返回该校当前时间（含偏移），
   供不支持自定义端口的客户端兜底。

偏移模型（线性漂移）：
    offset(t) = base_offset_ms + daily_offset_ms * (t - base_time) / 86400s
管理员「手动校准」时填入实测到的学校时间，系统重算 base_offset_ms
并把 base_time 推进到当下，daily_offset_ms 保持不变。
"""
import asyncio
import logging
import struct
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from . import config as app_config
from .db import SessionLocal
from .models import NtpServer, School

logger = logging.getLogger("csespusher.ntp")

# NTP 时间戳以 1900-01-01 起算，Unix 时间戳以 1970-01-01 起算
NTP_EPOCH_DELTA = 2208988800
DAY_SECONDS = 86400.0

# 回包固定字段
STRATUM = 2          # 声明有上游参考时钟，比 1（原子钟）更不容易被客户端质疑
PRECISION = -20      # 2^-20 s ≈ 0.95 µs
REF_ID = b"CESP"     # csespusher
ROOT_DELAY = 0
ROOT_DISPERSION = 0x00000100  # ≈ 0.0039 s

# 前端下拉可选时区（避免 Windows 缺 tzdata 时 zoneinfo 不可用）
TIMEZONE_CHOICES = [
    {"name": "Asia/Shanghai", "label": "北京时间 (UTC+8)", "offset_hours": 8},
    {"name": "Asia/Urumqi", "label": "新疆时间 (UTC+6)", "offset_hours": 6},
    {"name": "Asia/Hong_Kong", "label": "香港时间 (UTC+8)", "offset_hours": 8},
    {"name": "Asia/Tokyo", "label": "日本时间 (UTC+9)", "offset_hours": 9},
    {"name": "UTC", "label": "协调世界时 (UTC+0)", "offset_hours": 0},
]
DEFAULT_TIMEZONE = app_config.NTP_DEFAULT_TIMEZONE


def tz_offset_seconds(name: str, at_ts: Optional[float] = None) -> float:
    """时区名 -> 相对 UTC 的偏移秒数；优先 zoneinfo，失败回退内置表。"""
    try:
        from zoneinfo import ZoneInfo

        ts = time.time() if at_ts is None else at_ts
        dt = datetime.fromtimestamp(ts, ZoneInfo(name))
        off = dt.utcoffset()
        if off is not None:
            return off.total_seconds()
    except Exception:  # 无 tzdata / 时区名非法
        pass
    for item in TIMEZONE_CHOICES:
        if item["name"] == name:
            return item["offset_hours"] * 3600.0
    return 8 * 3600.0


def _dt_to_ts(dt: datetime) -> float:
    """模型里的 naive datetime 一律按 UTC 解释。"""
    if dt is None:
        return time.time()
    return dt.replace(tzinfo=timezone.utc).timestamp()


def _to_ntp(ts: float) -> bytes:
    """Unix 时间戳 -> NTP 64 位时间戳（32.32 定点）。"""
    ntp = ts + NTP_EPOCH_DELTA
    sec = int(ntp // 1)
    frac = int(round((ntp - sec) * (1 << 32)))
    if frac >= (1 << 32):  # 进位
        sec += 1
        frac -= 1 << 32
    return struct.pack("!II", sec & 0xFFFFFFFF, frac)


def _from_ntp(raw: bytes) -> float:
    """NTP 64 位时间戳 -> Unix 时间戳。"""
    if len(raw) < 8:
        return 0.0
    sec, frac = struct.unpack("!II", raw[:8])
    return (sec + frac / float(1 << 32)) - NTP_EPOCH_DELTA


def offset_seconds(row: NtpServer, now: Optional[float] = None) -> float:
    """某校在 now 时刻相对真实 UTC 的偏移秒数。"""
    if now is None:
        now = time.time()
    elapsed_days = (now - _dt_to_ts(row.base_time)) / DAY_SECONDS
    return row.base_offset_ms / 1000.0 + row.daily_offset_ms / 1000.0 * elapsed_days


def school_now(row: NtpServer, now: Optional[float] = None) -> Tuple[float, float, float]:
    """返回 (真实时间戳, 学校时间戳, 偏移秒数)。"""
    if now is None:
        now = time.time()
    off = offset_seconds(row, now)
    return now, now + off, off


def format_local(ts: float, tz_name: str) -> str:
    """按学校时区把时间戳格式化成本地墙钟字符串。"""
    try:
        dt = datetime.fromtimestamp(ts + tz_offset_seconds(tz_name, ts))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (OSError, OverflowError, ValueError):
        return ""


def public_host(request) -> str:
    """对外展示的主机名：优先 NTP_PUBLIC_HOST，否则取请求的 Host（去端口）。"""
    if app_config.NTP_PUBLIC_HOST:
        return app_config.NTP_PUBLIC_HOST
    host = ""
    if request is not None:
        host = (request.headers.get("host") or "").strip()
    if host.startswith("["):                 # IPv6: [::1]:5173
        return host.split("]", 1)[0] + "]"
    return host.split(":", 1)[0] or "127.0.0.1"


def public_brief(row: "NtpServer", host: str) -> dict:
    """给公开页面（班级页 / 分享页）用的时间同步摘要。"""
    real_ts, school_ts, off = school_now(row)
    return {
        "enabled": True,
        "school": row.school.name if row.school else "",
        "host": host,
        "port": row.port,
        "address": "%s:%s" % (host, row.port),
        "token": row.token,
        "http_time_url": "/api/public/ntp/%s/time" % row.token,
        "timezone": row.timezone,
        "offset_ms": round(off * 1000, 1),
        "daily_offset_ms": row.daily_offset_ms,
        "local": format_local(school_ts, row.timezone),
        "unix_ms": int(round(school_ts * 1000)),
    }


def brief_for_school(db, school_id: int, host: str) -> dict:
    row = db.query(NtpServer).filter(NtpServer.school_id == school_id).first()
    if row is None or not row.enabled:
        return {"enabled": False}
    return public_brief(row, host)


def allocate_port(db, exclude_server_id: Optional[int] = None) -> int:
    """为新的 NTP 服务挑一个未被占用的端口。"""
    query = db.query(NtpServer.port)
    if exclude_server_id is not None:
        query = query.filter(NtpServer.id != exclude_server_id)
    used = {p for (p,) in query.all()}
    start = app_config.NTP_BASE_PORT
    end = start + max(1, app_config.NTP_MAX_SERVERS)
    for port in range(start, end):
        if port not in used:
            return port
    raise RuntimeError(
        "没有可用的 NTP 端口（%s ~ %s 已占满，可调大 NTP_MAX_SERVERS）" % (start, end - 1)
    )


@dataclass
class NtpRuntime:
    """运行期快照：UDP 回调里只用它，不碰数据库。"""

    id: int
    school_id: int
    school_name: str
    token: str
    port: int
    enabled: bool
    daily_offset_ms: int
    base_offset_ms: int
    base_ts: float
    timezone: str

    def offset(self, now: float) -> float:
        elapsed_days = (now - self.base_ts) / DAY_SECONDS
        return self.base_offset_ms / 1000.0 + self.daily_offset_ms / 1000.0 * elapsed_days

    def school_ts(self, now: float) -> float:
        return now + self.offset(now)


def _runtime_of(row: NtpServer, school_name: str) -> NtpRuntime:
    return NtpRuntime(
        id=row.id,
        school_id=row.school_id,
        school_name=school_name,
        token=row.token,
        port=row.port,
        enabled=bool(row.enabled),
        daily_offset_ms=int(row.daily_offset_ms or 0),
        base_offset_ms=int(row.base_offset_ms or 0),
        base_ts=_dt_to_ts(row.base_time),
        timezone=row.timezone or DEFAULT_TIMEZONE,
    )


class _NtpServerProtocol(asyncio.DatagramProtocol):
    """单个 UDP 端口的回调。"""

    def __init__(self, service: "NtpService", port: int):
        self.service = service
        self.port = port
        self.transport: Optional[asyncio.DatagramTransport] = None

    def connection_made(self, transport):  # noqa: D102
        self.transport = transport

    def connection_lost(self, exc):  # noqa: D102
        self.transport = None

    def error_received(self, exc):  # noqa: D102
        logger.debug("NTP 端口 %s 收到 ICMP 错误：%s", self.port, exc)

    def datagram_received(self, data: bytes, addr):  # noqa: D102
        try:
            resp = self.service.handle_packet(self.port, data, addr)
        except Exception:
            logger.exception("处理 NTP 请求出错（端口 %s）", self.port)
            return
        if resp is not None and self.transport is not None:
            try:
                self.transport.sendto(resp, addr)
            except OSError as e:
                logger.debug("NTP 回包失败 %s：%s", addr, e)


class NtpService:
    """管理所有学校的 NTP 端口：配置热更新 + 请求统计。"""

    def __init__(self):
        self._servers: Dict[int, NtpRuntime] = {}       # port -> runtime
        self._transports: Dict[int, asyncio.DatagramTransport] = {}
        self._stats: Dict[int, dict] = {}               # port -> 统计
        self._failed: Dict[int, str] = {}               # port -> 监听失败原因
        self._refresh_task: Optional[asyncio.Task] = None
        # 延迟到 start() 里创建，确保绑定到真正运行的事件循环
        self._lock: Optional[asyncio.Lock] = None
        self._running = False
        self._started_at = time.time()

    # ---------------- 生命周期 ----------------

    @property
    def running(self) -> bool:
        return self._running

    @property
    def started_at(self) -> float:
        return self._started_at

    async def start(self) -> None:
        if self._running:
            return
        self._lock = asyncio.Lock()
        self._running = True
        self._started_at = time.time()
        await self.refresh()
        self._refresh_task = asyncio.create_task(self._refresh_loop())
        logger.info("NTP 服务已启动，监听 %s 个端口，基础端口 %s",
                    len(self._transports), app_config.NTP_BASE_PORT)

    async def stop(self) -> None:
        self._running = False
        if self._refresh_task is not None:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except (asyncio.CancelledError, Exception):
                pass
            self._refresh_task = None
        self._close_all()
        logger.info("NTP 服务已停止")

    def _close_all(self) -> None:
        """关闭全部端口（transport 所属的事件循环可能已失效，异常一律吞掉）。"""
        for port, transport in list(self._transports.items()):
            try:
                transport.close()
            except Exception:
                pass
            self._transports.pop(port, None)
            self._servers.pop(port, None)

    async def _refresh_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(max(5, app_config.NTP_REFRESH_SECONDS))
                await self.refresh()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("NTP 配置刷新失败")

    # ---------------- 配置同步 ----------------

    def _load_rows(self) -> List[NtpRuntime]:
        """同步查询数据库（在线程里跑，避免阻塞事件循环）。"""
        db = SessionLocal()
        try:
            rows = (
                db.query(NtpServer, School.name)
                .join(School, School.id == NtpServer.school_id)
                .all()
            )
            return [_runtime_of(row, name) for row, name in rows]
        finally:
            db.close()

    async def refresh(self) -> None:
        """按数据库最新配置重建端口监听（新增/停用/改配置都在此收敛）。"""
        # 服务没起来（NTP_ENABLED=0 或启动失败）时不要碰 socket：
        # 否则会在请求所在的事件循环上留下孤儿 transport
        if not self._running or self._lock is None:
            return
        runtimes = await asyncio.to_thread(self._load_rows)
        desired = {rt.port: rt for rt in runtimes if rt.enabled}
        loop = asyncio.get_event_loop()
        async with self._lock:
            # 只停掉不再需要的端口；仍在服务的端口原地换配置，绝不重建 socket
            # （Windows 上关闭再立刻 bind 同一 UDP 端口容易撞 WinError 10048）
            for port in list(self._transports):
                if port not in desired:
                    transport = self._transports.pop(port, None)
                    self._servers.pop(port, None)
                    self._failed.pop(port, None)
                    if transport is not None:
                        try:
                            transport.close()
                        except Exception:
                            pass
            for port, rt in desired.items():
                if port in self._transports:
                    self._servers[port] = rt
                    continue
                transport = await self._bind(loop, port)
                if transport is None:
                    continue
                self._transports[port] = transport
                self._servers[port] = rt
                self._failed.pop(port, None)
                logger.info("NTP 端口 %s 已就绪（%s）", port, rt.school_name)

    async def _bind(self, loop, port: int, retries: int = 3):
        """绑定 UDP 端口，失败重试若干次（端口刚被释放时可能短暂不可用）。"""
        last = None
        for attempt in range(retries):
            try:
                transport, _ = await loop.create_datagram_endpoint(
                    lambda p=port: _NtpServerProtocol(self, p),
                    local_addr=(app_config.NTP_HOST, port),
                )
                return transport
            except OSError as e:
                last = e
                if attempt + 1 < retries:
                    await asyncio.sleep(0.25 * (attempt + 1))
        self._failed[port] = "端口监听失败：%s" % last
        logger.warning("NTP 端口 %s 监听失败：%s", port, last)
        return None

    # ---------------- 请求处理 ----------------

    def handle_packet(self, port: int, data: bytes, addr) -> Optional[bytes]:
        rt = self._servers.get(port)
        if rt is None or not rt.enabled:
            return None
        recv_ts = time.time()
        if len(data) < 48:
            return None
        mode = data[0] & 0x07
        if mode != 3:
            # 只回应客户端请求（mode=3），避免被当作反射放大源
            return None
        version = (data[0] >> 3) & 0x07
        vn = version if version in (3, 4) else 4
        poll = data[2] or 6
        originate = data[40:48]

        tx_ts = time.time()
        pkt = bytearray(48)
        pkt[0] = (vn << 3) | 4                       # LI=0, mode=4(server)
        pkt[1] = STRATUM
        pkt[2] = poll
        struct.pack_into("!b", pkt, 3, PRECISION)
        struct.pack_into("!I", pkt, 4, ROOT_DELAY)
        struct.pack_into("!I", pkt, 8, ROOT_DISPERSION)
        pkt[12:16] = REF_ID
        pkt[16:24] = _to_ntp(rt.school_ts(self._started_at))  # 上次"校准"时刻
        pkt[24:32] = originate                                # originate
        pkt[32:40] = _to_ntp(rt.school_ts(recv_ts))           # receive
        pkt[40:48] = _to_ntp(rt.school_ts(tx_ts))             # transmit

        st = self._stats.setdefault(port, {"queries": 0, "last_seen": None,
                                           "last_client": None, "clients": set()})
        st["queries"] += 1
        st["last_seen"] = recv_ts
        st["last_client"] = addr[0] if addr else None
        if addr:
            st["clients"].add(addr[0])
        return bytes(pkt)

    # ---------------- 状态查询 ----------------

    def is_listening(self, port: int) -> bool:
        return port in self._transports

    def runtime_for_school(self, school_id: int) -> Optional[NtpRuntime]:
        for rt in self._servers.values():
            if rt.school_id == school_id:
                return rt
        return None

    def status(self, db=None) -> List[dict]:
        """所有 NTP 服务的运行状态（含未监听/失败的）。"""
        own_db = db is None
        if own_db:
            db = SessionLocal()
        try:
            rows = (
                db.query(NtpServer, School.name)
                .join(School, School.id == NtpServer.school_id)
                .order_by(NtpServer.port)
                .all()
            )
            out = []
            for row, school_name in rows:
                st = self._stats.get(row.port, {})
                now = time.time()
                real_ts, school_ts, off = school_now(row, now)
                out.append({
                    "id": row.id,
                    "school_id": row.school_id,
                    "school_name": school_name,
                    "port": row.port,
                    "enabled": bool(row.enabled),
                    "listening": row.port in self._transports,
                    "error": self._failed.get(row.port),
                    "queries": st.get("queries", 0),
                    "unique_clients": len(st.get("clients", ())),
                    "last_client": st.get("last_client"),
                    "last_seen": st.get("last_seen"),
                    "current_offset_ms": round(off * 1000, 1),
                    "daily_offset_ms": row.daily_offset_ms,
                    "school_time": format_local(school_ts, row.timezone),
                    "real_time": format_local(real_ts, row.timezone),
                    "timezone": row.timezone,
                })
            return out
        finally:
            if own_db:
                db.close()


ntp_service = NtpService()
