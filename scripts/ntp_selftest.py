"""NTP 时间源自检脚本。

不需要启动 Web 服务、不需要登录，直接驱动 NTP 引擎跑一遍：

    cd backend
    python ../scripts/ntp_selftest.py

检查项：
1. 创建临时学校 + NTP 服务，端口监听正常
2. UDP 查询返回的时间戳带有设定的偏移量
3. 修改每日偏移量后，偏移量随时间累积
4. 手动校准能把实测时间回填成正确的偏差
5. 停用后端口不再响应

脚本使用独立的临时数据库（backend/data/_ntp_selftest.db），跑完自动删除。
"""
import asyncio
import datetime as dt
import os
import struct
import sys
import tempfile
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

# 临时库放在系统临时目录，避免污染项目数据；删不掉也无妨，系统会自动清理
TMP_DB = Path(tempfile.gettempdir()) / "csespusher_ntp_selftest.db"
os.environ["DATABASE_URL"] = "sqlite:///" + TMP_DB.as_posix()
os.environ["NTP_BASE_PORT"] = os.environ.get("NTP_BASE_PORT", "11923")
os.environ.setdefault("NTP_HOST", "127.0.0.1")
os.environ.setdefault("NTP_PUBLIC_HOST", "127.0.0.1")

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.models import NtpServer, School, User  # noqa: E402
from app import ntp as ntp_util  # noqa: E402
from app.ntp import ntp_service  # noqa: E402
from app.routers.ntp import _parse_school_time, _time_payload  # noqa: E402

OK, FAIL = "  [OK]  ", "  [FAIL]"


def check(cond, msg, extra=""):
    print((OK if cond else FAIL) + " " + msg + (("  -> " + str(extra)) if extra else ""))
    if not cond:
        raise SystemExit("自检未通过：" + msg)
    return True


def build_request() -> bytes:
    """标准 NTPv4 客户端请求（mode=3）。"""
    pkt = bytearray(48)
    pkt[0] = (4 << 3) | 3
    pkt[1] = 0            # stratum
    pkt[2] = 6            # poll
    pkt[3] = 0xEC         # precision
    pkt[40:48] = ntp_util._to_ntp(time.time())
    return bytes(pkt)


async def udp_query(port: int, timeout: float = 3.0):
    """向指定端口发一次 NTP 查询，返回 (offset, delay, raw)。"""
    loop = asyncio.get_running_loop()
    future = loop.create_future()

    class Client(asyncio.DatagramProtocol):
        def connection_made(self, transport):
            self.transport = transport

        def datagram_received(self, data, addr):
            if not future.done():
                future.set_result(data)

        def error_received(self, exc):
            if not future.done():
                future.set_exception(exc)

    transport, _ = await loop.create_datagram_endpoint(
        Client, remote_addr=("127.0.0.1", port))
    try:
        req = build_request()
        transport.sendto(req)
        t4 = time.time()
        raw = await asyncio.wait_for(future, timeout)
        t1 = ntp_util._from_ntp(req[40:48])
        t2 = ntp_util._from_ntp(raw[32:40])
        t3 = ntp_util._from_ntp(raw[40:48])
        return ((t2 - t1) + (t3 - t4)) / 2.0, (t4 - t1) - (t3 - t2), raw
    finally:
        transport.close()


def unlink_quiet(path: Path) -> None:
    try:
        Path(path).unlink()
    except OSError:
        pass


def utc_naive() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


async def main():
    unlink_quiet(TMP_DB)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    user = User(email="selftest@example.com", username="selftest", role="superadmin")
    school = School(name="自检中学", province="测试省", city="测试市", owner_id=None)
    db.add(user)
    db.add(school)
    db.commit()
    db.add(NtpServer(school_id=school.id, port=ntp_util.allocate_port(db),
                     enabled=True, daily_offset_ms=10_000,  # 每天快 10 秒
                     base_offset_ms=0, timezone="Asia/Shanghai"))
    db.commit()
    row = db.query(NtpServer).filter(NtpServer.school_id == school.id).first()
    port = row.port

    print("== 1. 服务启动与端口监听 ==")
    await ntp_service.start()
    check(ntp_service.is_listening(port), "端口 %s 已监听" % port)
    check(port == int(os.environ["NTP_BASE_PORT"]), "端口从 NTP_BASE_PORT 开始分配", port)

    print("== 2. 零偏移时应与真实时间一致 ==")
    off, delay, raw = await udp_query(port)
    check(len(raw) == 48, "响应为标准 48 字节 NTP 报文", len(raw))
    check((raw[0] & 0x07) == 4, "响应 mode=4（server）", raw[0] & 0x07)
    check(abs(off) < 0.05, "测得偏移接近 0（基准刚设定）", "%.4f s" % off)

    print("== 3. 设置 +5 分钟后 NTP 返回学校时间 ==")
    row.base_offset_ms = 300_000
    row.base_time = row.base_time  # 保持基准时刻
    db.commit()
    await ntp_service.refresh()
    off, delay, _ = await udp_query(port)
    check(abs(off - 300.0) < 0.05, "测得偏移 ≈ +300 s", "%.4f s" % off)

    print("== 4. 每日偏移量按时间累积 ==")
    row.base_offset_ms = 0
    row.daily_offset_ms = 86_400_000          # 每天 +86400 s，即每秒 +1 s
    row.base_time = utc_naive()
    db.commit()
    await ntp_service.refresh()
    off1, _, _ = await udp_query(port)
    await asyncio.sleep(1.2)
    off2, _, _ = await udp_query(port)
    check(off2 - off1 > 0.9, "1 秒后偏移随之增长", "%.3f -> %.3f" % (off1, off2))

    print("== 5. HTTP 时间接口输出 ==")
    payload = _time_payload(row)
    check(payload["school"] == "自检中学", "返回学校名", payload["school"])
    check(payload["unix_ms"] > time.time() * 1000, "unix_ms 已含偏移")
    check(payload["ntp"]["port"] == port, "附带 NTP 端口", payload["ntp"]["address"])

    print("== 6. 手动校准回填 ==")
    now = time.time()
    # 管理员看到学校时钟比真实快 1234 秒，把表盘读数原样填进去
    school_tz = dt.timezone(dt.timedelta(seconds=ntp_util.tz_offset_seconds("Asia/Shanghai", now)))
    wall = dt.datetime.fromtimestamp(now + 1234.0, school_tz).strftime("%H:%M:%S")
    target = _parse_school_time(wall, "Asia/Shanghai", now)
    check(abs((target - now) - 1234.0) < 2.0, "解析墙钟时间 %s → 偏差 ≈ +1234 s" % wall,
          "%.2f s" % (target - now))
    row.base_offset_ms = int(round((target - now) * 1000))
    row.base_time = utc_naive()
    row.daily_offset_ms = 0
    db.commit()
    _, school_ts, cur = ntp_util.school_now(row)
    check(abs(cur - 1234.0) < 2.0, "校准后当前偏差 ≈ +1234 s", "%.2f s" % cur)

    print("== 7. 停用后端口不再响应 ==")
    row.enabled = False
    db.commit()
    await ntp_service.refresh()
    check(not ntp_service.is_listening(port), "端口已释放")
    try:
        await udp_query(port, timeout=1.5)
        check(False, "停用后应无响应")
    except (asyncio.TimeoutError, OSError):
        # Windows 上主机会回 ICMP 端口不可达，表现为 OSError 而非超时，都算无响应
        check(True, "停用后无响应")

    print("== 8. 运行状态统计 ==")
    row.enabled = True
    db.commit()
    await ntp_service.refresh()
    await udp_query(port)
    status = ntp_service.status(db)
    check(status and status[0]["queries"] >= 1, "查询计数已记录",
          status[0]["queries"] if status else None)
    check(status[0]["listening"], "状态显示正在监听")

    await ntp_service.stop()
    db.close()
    engine.dispose()
    print("\n全部自检通过。")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        for suffix in ("", "-journal", "-wal", "-shm"):
            unlink_quiet(Path(str(TMP_DB) + suffix))
