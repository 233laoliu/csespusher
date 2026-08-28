"""邮件发送：配置了 SMTP 走邮件，否则验证码打印到控制台。"""
import smtplib
from email.mime.text import MIMEText

from . import config


def send_verification_email(to_addr: str, code: str) -> str:
    """返回发送方式说明（'smtp' 或 'console'）。"""
    if config.SMTP_HOST and config.SMTP_USER:
        msg = MIMEText(
            "您的验证码是：%s（%d 分钟内有效）。\n如非本人操作请忽略本邮件。\n—— csespusher"
            % (code, config.CODE_TTL_SECONDS // 60),
            "plain",
            "utf-8",
        )
        msg["Subject"] = "csespusher 验证码"
        msg["From"] = config.SMTP_FROM or config.SMTP_USER
        msg["To"] = to_addr
        if config.SMTP_USE_TLS:
            server = smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, timeout=10)
        else:
            server = smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=10)
        try:
            server.login(config.SMTP_USER, config.SMTP_PASS)
            server.sendmail(msg["From"], [to_addr], msg.as_string())
        finally:
            server.quit()
        return "smtp"

    # 开发模式：控制台输出
    print("[csespusher] 验证码 -> %s : %s （%d 秒有效）" % (to_addr, code, config.CODE_TTL_SECONDS))
    return "console"
