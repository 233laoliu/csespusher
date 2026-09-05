"""HTML 邮件发送工具，未配置 SMTP 时回退到控制台。"""
import html
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from . import config


def send_code_email(to_addr: str, code: str, purpose: str = "register") -> str:
    title = "完成账号注册" if purpose == "register" else "重置登录密码"
    action = "注册验证码" if purpose == "register" else "密码重置验证码"
    minutes = config.CODE_TTL_SECONDS // 60
    if config.SMTP_HOST and config.SMTP_USER:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "csespusher · " + title
        msg["From"] = config.SMTP_FROM or config.SMTP_USER
        msg["To"] = to_addr
        safe_code = html.escape(code)
        text = "%s：%s（%d 分钟内有效）。如非本人操作请忽略。" % (action, code, minutes)
        body = """<div style=\"background:#f4f7fb;padding:32px;font-family:Arial,'Microsoft YaHei',sans-serif;color:#172033\">
          <div style=\"max-width:520px;margin:auto;background:#fff;border:1px solid #e5eaf2;border-radius:14px;padding:32px\">
            <div style=\"font-size:22px;font-weight:700;color:#2563eb;margin-bottom:24px\">csespusher</div>
            <h2 style=\"margin:0 0 12px\">%s</h2>
            <p style=\"color:#667085;line-height:1.7\">您的%s如下，请在 %d 分钟内完成操作。</p>
            <div style=\"font-size:32px;letter-spacing:8px;font-weight:700;color:#2563eb;background:#eff6ff;border-radius:10px;text-align:center;padding:18px;margin:24px 0\">%s</div>
            <p style=\"font-size:13px;color:#98a2b3;line-height:1.7\">如果这不是您的操作，请忽略本邮件。请勿向他人透露验证码。</p>
          </div>
        </div>""" % (title, action, minutes, safe_code)
        msg.attach(MIMEText(text, "plain", "utf-8"))
        msg.attach(MIMEText(body, "html", "utf-8"))
        server = smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, timeout=10) if config.SMTP_USE_TLS else smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=10)
        try:
            server.login(config.SMTP_USER, config.SMTP_PASS)
            server.sendmail(msg["From"], [to_addr], msg.as_string())
        finally:
            server.quit()
        return "smtp"
    print("[csespusher] %s -> %s : %s（%d 秒有效）" % (action, to_addr, code, config.CODE_TTL_SECONDS))
    return "console"


def send_verification_email(to_addr: str, code: str) -> str:
    return send_code_email(to_addr, code, "register")
