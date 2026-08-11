"""
Serviço de E-mail — Envio assíncrono de OTP via SMTP.

Utiliza smtplib (stdlib) para enviar e-mails transacionais
com template HTML. Projetado para ser chamado via
FastAPI BackgroundTasks (função síncrona / blocking I/O).
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from app.config import settings

logger = logging.getLogger("uvicorn.error")

# ── Caminho do template ─────────────────────────────────────

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
_OTP_TEMPLATE_PATH = _TEMPLATE_DIR / "otp_template.html"


def _carregar_template_otp(codigo: str) -> str:
    """
    Carrega o template HTML e substitui os placeholders.

    Placeholders suportados:
        {{CODIGO}}              — Código OTP de 6 dígitos
        {{EXPIRE_MINUTES}}      — Tempo de expiração em minutos
        {{FROM_NAME}}           — Nome do remetente (LearningLab)
    """
    template = _OTP_TEMPLATE_PATH.read_text(encoding="utf-8")
    return (
        template
        .replace("{{CODIGO}}", codigo)
        .replace("{{EXPIRE_MINUTES}}", str(settings.OTP_EXPIRE_MINUTES))
        .replace("{{FROM_NAME}}", settings.SMTP_FROM_NAME)
    )


def enviar_email_otp(destinatario: str, codigo: str) -> None:
    """
    Envia o e-mail com o código OTP formatado em HTML.

    Esta função é **síncrona** (blocking I/O) e deve ser chamada
    dentro de ``BackgroundTasks`` do FastAPI para não bloquear
    o event loop.

    Raises:
        smtplib.SMTPException: em caso de falha no envio.
    """
    html_body = _carregar_template_otp(codigo)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🔐 Código de verificação — {settings.SMTP_FROM_NAME}"
    msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
    msg["To"] = destinatario

    # Fallback em texto puro para clientes que não suportam HTML
    texto_puro = (
        f"Seu código de verificação é: {codigo}\n\n"
        f"Este código expira em {settings.OTP_EXPIRE_MINUTES} minutos.\n"
        f"Se você não solicitou este código, ignore este e-mail."
    )
    msg.attach(MIMEText(texto_puro, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            if settings.SMTP_USE_TLS:
                server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.SMTP_FROM_EMAIL, destinatario, msg.as_string())

        logger.info("📧 E-mail OTP enviado com sucesso para %s", destinatario)

    except smtplib.SMTPException:
        logger.exception("❌ Falha ao enviar e-mail OTP para %s", destinatario)
        raise
