"""
Serviço de E-mail — Envio assíncrono de OTP via SMTP.

Utiliza smtplib (stdlib) para enviar e-mails transacionais
com template HTML. Projetado para ser chamado via
FastAPI BackgroundTasks (função síncrona / blocking I/O).
"""

import html
import logging
import smtplib
import urllib.parse
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

from app.config import settings

logger = logging.getLogger("uvicorn.error")

# ── Caminhos dos templates ───────────────────────────────────

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
_OTP_TEMPLATE_PATH = _TEMPLATE_DIR / "otp_template.html"
_ADVERTENCIA_TEMPLATE_PATH = _TEMPLATE_DIR / "advertencia_template.html"
_TASK_AUDITORIA_TEMPLATE_PATH = _TEMPLATE_DIR / "task_auditoria_template.html"
_TASK_ATRIBUIDA_TEMPLATE_PATH = _TEMPLATE_DIR / "task_atribuida_template.html"
_IMPEDIMENTO_TEMPLATE_PATH = _TEMPLATE_DIR / "impedimento_template.html"


def _escape_html(valor: Any, preserve_newlines: bool = False) -> str:
    """Escapa caracteres HTML especiais para prevenir HTML injection e phishing.

    Se preserve_newlines for True, converte quebras de linha literais (\\n) em tags <br />,
    após a sanitização rigorosa de caracteres especiais (&, <, >, ", ').
    """
    if valor is None:
        return ""
    texto = html.escape(str(valor), quote=True)
    if preserve_newlines:
        texto = texto.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br />\n")
    return texto


def _carregar_template_otp(codigo: str, destinatario: str) -> str:
    """Carrega o template HTML e substitui os placeholders escapando dados externos.

    Placeholders suportados:
        {{CODIGO}}              — Código OTP de 6 dígitos
        {{EXPIRE_MINUTES}}      — Tempo de expiração em minutos
        {{FROM_NAME}}           — Nome do remetente (LearningLab)
        {{VERIFY_LINK}}         — Link direto para a página de verificação
    """
    template = _OTP_TEMPLATE_PATH.read_text(encoding="utf-8")

    frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:5173").rstrip("/")
    email_encodado = urllib.parse.quote(destinatario)
    verify_link = f"{frontend_url}/verify-code?email={email_encodado}"

    return (
        template.replace("{{CODIGO}}", _escape_html(codigo))
        .replace("{{EXPIRE_MINUTES}}", _escape_html(settings.OTP_EXPIRE_MINUTES))
        .replace("{{FROM_NAME}}", _escape_html(settings.SMTP_FROM_NAME))
        .replace("{{VERIFY_LINK}}", verify_link)
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
    # Adicionamos o destinatario aqui na chamada da função
    html_body = _carregar_template_otp(codigo, destinatario)

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


def _formatar_tipo_advertencia(tipo: str) -> str:
    mapa = {
        "1a_ADVERTENCIA": "1ª Advertência",
        "2a_ADVERTENCIA": "2ª Advertência",
        "DESLIGAMENTO": "Notificação de Desligamento",
    }
    return mapa.get(tipo, tipo)


def _carregar_template_advertencia(
    nome_membro: str,
    tipo: str,
    semanas_ausentes: int,
    setor_nome: str,
    semana_referencia: str,
) -> str:
    template = _ADVERTENCIA_TEMPLATE_PATH.read_text(encoding="utf-8")
    frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:5173").rstrip("/")

    return (
        template.replace("{{FROM_NAME}}", _escape_html(settings.SMTP_FROM_NAME))
        .replace("{{NOME_MEMBRO}}", _escape_html(nome_membro))
        .replace("{{TIPO_ADVERTENCIA}}", _escape_html(_formatar_tipo_advertencia(tipo)))
        .replace("{{SEMANAS_AUSENTES}}", _escape_html(semanas_ausentes))
        .replace("{{SETOR_NOME}}", _escape_html(setor_nome))
        .replace("{{SEMANA_REFERENCIA}}", _escape_html(semana_referencia))
        .replace("{{FRONTEND_URL}}", frontend_url)
    )


def enviar_email_advertencia(
    destinatario: str,
    nome_membro: str,
    tipo: str,
    semanas_ausentes: int,
    setor_nome: str,
    semana_referencia: str,
) -> None:
    """Envia e-mail de notificação de advertência por ausência de envio de weekly.

    Se as credenciais SMTP não estiverem configuradas, registra log e retorna com segurança.
    """
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        logger.info(
            "📧 [MOCK/DEV] SMTP não configurado. Notificação de advertência (%s) para %s ignorada.",
            tipo,
            destinatario,
        )
        return

    html_body = _carregar_template_advertencia(
        nome_membro, tipo, semanas_ausentes, setor_nome, semana_referencia
    )
    tipo_formatado = _formatar_tipo_advertencia(tipo)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"⚠️ [{tipo_formatado}] Ausência de Weekly — {settings.SMTP_FROM_NAME}"
    msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
    msg["To"] = destinatario

    texto_puro = (
        f"Olá, {nome_membro}!\n\n"
        f"Identificamos a ausência no envio do seu relatório semanal de atividades (Weekly) "
        f"referente à semana {semana_referencia} no setor {setor_nome}.\n"
        f"Tipo de ocorrência: {tipo_formatado} ({semanas_ausentes} semanas consecutivas sem envio).\n\n"
        f"Acesse o sistema para regularizar suas entregas: {settings.FRONTEND_URL}/weeklies\n"
    )
    msg.attach(MIMEText(texto_puro, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            if settings.SMTP_USE_TLS:
                server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.SMTP_FROM_EMAIL, destinatario, msg.as_string())

        logger.info("📧 E-mail de advertência (%s) enviado com sucesso para %s", tipo, destinatario)
    except smtplib.SMTPException:
        logger.exception("❌ Falha ao enviar e-mail de advertência para %s", destinatario)
        raise


def _carregar_template_task_auditoria(
    titulo_task: str,
    nome_membro: str,
    setor_nome: str,
    prazo_conclusao: str,
) -> str:
    template = _TASK_AUDITORIA_TEMPLATE_PATH.read_text(encoding="utf-8")
    frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:5173").rstrip("/")

    return (
        template.replace("{{TITULO_CABECALHO}}", "⚠️ Tarefa Sob Auditoria")
        .replace("{{BADGE_TEXTO}}", "EM AUDITORIA — PRAZO EXPIRADO")
        .replace(
            "{{MENSAGEM_DETALHE}}",
            "Uma tarefa pendente ultrapassou a data limite de conclusão e foi transferida automaticamente para status de auditoria.",
        )
        .replace("{{TITULO_TASK}}", _escape_html(titulo_task))
        .replace("{{MEMBRO_NOME}}", _escape_html(nome_membro))
        .replace("{{SETOR_NOME}}", _escape_html(setor_nome))
        .replace("{{PRAZO_CONCLUSAO}}", _escape_html(prazo_conclusao))
        .replace("{{FRONTEND_URL}}", frontend_url)
        .replace("{{FROM_NAME}}", _escape_html(settings.SMTP_FROM_NAME))
    )


def enviar_email_task_auditoria(
    destinatario: str,
    titulo_task: str,
    nome_membro: str,
    setor_nome: str,
    prazo_conclusao: str,
) -> None:
    """Envia notificação para líderes e admins informando que uma task estourou o prazo e entrou em auditoria."""
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        logger.info(
            "📧 [MOCK/DEV] SMTP não configurado. Notificação de auditoria da task '%s' para %s ignorada.",
            titulo_task,
            destinatario,
        )
        return

    html_body = _carregar_template_task_auditoria(
        titulo_task=titulo_task,
        nome_membro=nome_membro,
        setor_nome=setor_nome,
        prazo_conclusao=prazo_conclusao,
    )

    msg = MIMEMultipart("alternative")
    titulo_limpo = titulo_task.replace("\r", " ").replace("\n", " ").strip()
    msg["Subject"] = f"⚠️ [Auditoria de Tasks] '{titulo_limpo}' — {settings.SMTP_FROM_NAME}"
    msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
    msg["To"] = destinatario

    texto_puro = (
        f"Aviso de Auditoria de Tarefa\n\n"
        f"A tarefa '{titulo_task}', sob responsabilidade de {nome_membro} no setor {setor_nome}, "
        f"ultrapassou o prazo limite de {prazo_conclusao} e foi marcada como EM_AUDITORIA.\n\n"
        f"Acesse o sistema para definir uma tratativa: {settings.FRONTEND_URL}/weeklies\n"
    )
    msg.attach(MIMEText(texto_puro, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            if settings.SMTP_USE_TLS:
                server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.SMTP_FROM_EMAIL, destinatario, msg.as_string())
        logger.info("📧 E-mail de auditoria enviado para %s (task: %s)", destinatario, titulo_task)
    except smtplib.SMTPException:
        logger.exception("❌ Falha ao enviar e-mail de auditoria para %s", destinatario)
        raise


def _carregar_template_escalonamento_auditoria(
    titulo_task: str,
    nome_membro: str,
    setor_nome: str,
    dias_em_auditoria: int,
) -> str:
    template = _TASK_AUDITORIA_TEMPLATE_PATH.read_text(encoding="utf-8")
    frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:5173").rstrip("/")
    dias_str = _escape_html(dias_em_auditoria)
    setor_str = _escape_html(setor_nome)

    return (
        template.replace("{{TITULO_CABECALHO}}", "🚨 Auditoria Travada — Escalonamento")
        .replace("{{BADGE_TEXTO}}", f"PARADA HÁ {dias_str} DIAS")
        .replace(
            "{{MENSAGEM_DETALHE}}",
            f"A tarefa abaixo aguarda deliberação da liderança do setor {setor_str} há {dias_str} dias sem definição. Solicitamos a intervenção da administração.",
        )
        .replace("{{TITULO_TASK}}", _escape_html(titulo_task))
        .replace("{{MEMBRO_NOME}}", _escape_html(nome_membro))
        .replace("{{SETOR_NOME}}", setor_str)
        .replace("{{PRAZO_CONCLUSAO}}", f"Em auditoria há {dias_str} dias")
        .replace("{{FRONTEND_URL}}", frontend_url)
        .replace("{{FROM_NAME}}", _escape_html(settings.SMTP_FROM_NAME))
    )


def enviar_email_escalonamento_auditoria(
    destinatario: str,
    titulo_task: str,
    nome_membro: str,
    setor_nome: str,
    dias_em_auditoria: int,
) -> None:
    """Envia notificação de escalonamento para administradores informando que a auditoria está travada há >= 7 dias."""
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        logger.info(
            "📧 [MOCK/DEV] SMTP não configurado. Escalonamento da task '%s' para %s ignorado.",
            titulo_task,
            destinatario,
        )
        return

    html_body = _carregar_template_escalonamento_auditoria(
        titulo_task=titulo_task,
        nome_membro=nome_membro,
        setor_nome=setor_nome,
        dias_em_auditoria=dias_em_auditoria,
    )

    msg = MIMEMultipart("alternative")
    titulo_limpo = titulo_task.replace("\r", " ").replace("\n", " ").strip()
    msg["Subject"] = f"🚨 [Escalonamento] Auditoria parada há {dias_em_auditoria}d: '{titulo_limpo}' — {settings.SMTP_FROM_NAME}"
    msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
    msg["To"] = destinatario

    texto_puro = (
        f"Alerta de Escalonamento de Auditoria\n\n"
        f"A tarefa '{titulo_task}', do setor {setor_nome} (responsável: {nome_membro}), "
        f"aguarda auditoria há {dias_em_auditoria} dias sem parecer da liderança.\n\n"
        f"Acesse o painel para intervir: {settings.FRONTEND_URL}/weeklies\n"
    )
    msg.attach(MIMEText(texto_puro, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            if settings.SMTP_USE_TLS:
                server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.SMTP_FROM_EMAIL, destinatario, msg.as_string())
        logger.info("📧 E-mail de escalonamento enviado para %s (task: %s)", destinatario, titulo_task)
    except smtplib.SMTPException:
        logger.exception("❌ Falha ao enviar e-mail de escalonamento para %s", destinatario)
        raise


def _carregar_template_convite_task(
    titulo_task: str,
    nome_solicitante: str,
    nome_atribuido: str,
    setor_nome: str,
    prazo_conclusao: str,
) -> str:
    template = _TASK_ATRIBUIDA_TEMPLATE_PATH.read_text(encoding="utf-8")
    frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:5173").rstrip("/")
    solicitante_str = _escape_html(nome_solicitante)
    prazo_str = _escape_html(prazo_conclusao)

    return (
        template.replace("{{TITULO_CABECALHO}}", "🤝 Convite para Tarefa")
        .replace("{{DESTINATARIO_NOME}}", _escape_html(nome_atribuido))
        .replace(
            "{{MENSAGEM_DETALHE}}",
            f"Você recebeu um convite de <strong>{solicitante_str}</strong> para colaborar na tarefa abaixo. Ao aceitar, uma cópia independente será inserida no seu planejamento semanal.",
        )
        .replace("{{BADGE_TEXTO}}", "CONVITE DE COLABORAÇÃO")
        .replace("{{TITULO_TASK}}", _escape_html(titulo_task))
        .replace("{{SETOR_NOME}}", _escape_html(setor_nome))
        .replace("{{SOLICITANTE_NOME}}", solicitante_str)
        .replace("{{CONVIDADO_NOME}}", _escape_html(nome_atribuido))
        .replace("{{INFO_EXTRA}}", f'<div class="info-row"><strong>Prazo Previsto:</strong> {prazo_str}</div>')
        .replace("{{FRONTEND_URL}}", frontend_url)
        .replace("{{FROM_NAME}}", _escape_html(settings.SMTP_FROM_NAME))
    )


def enviar_email_convite_task(
    destinatario: str,
    titulo_task: str,
    nome_solicitante: str,
    nome_atribuido: str,
    setor_nome: str,
    prazo_conclusao: str,
) -> None:
    """Envia e-mail de convite para membro convidado a colaborar em uma task."""
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        logger.info(
            "📧 [MOCK/DEV] SMTP não configurado. Convite da task '%s' para %s ignorado.",
            titulo_task,
            destinatario,
        )
        return

    html_body = _carregar_template_convite_task(
        titulo_task=titulo_task,
        nome_solicitante=nome_solicitante,
        nome_atribuido=nome_atribuido,
        setor_nome=setor_nome,
        prazo_conclusao=prazo_conclusao,
    )

    msg = MIMEMultipart("alternative")
    titulo_limpo = titulo_task.replace("\r", " ").replace("\n", " ").strip()
    msg["Subject"] = f"🤝 [Convite de Tarefa] '{titulo_limpo}' — {settings.SMTP_FROM_NAME}"
    msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
    msg["To"] = destinatario

    texto_puro = (
        f"Convite de Tarefa\n\n"
        f"Olá, {nome_atribuido}!\n"
        f"{nome_solicitante} convidou você para colaborar na tarefa '{titulo_task}' do setor {setor_nome}.\n"
        f"Prazo: {prazo_conclusao}\n\n"
        f"Acesse o sistema para aceitar ou recusar: {settings.FRONTEND_URL}/weeklies\n"
    )
    msg.attach(MIMEText(texto_puro, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            if settings.SMTP_USE_TLS:
                server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.SMTP_FROM_EMAIL, destinatario, msg.as_string())
        logger.info("📧 E-mail de convite de task enviado para %s (task: %s)", destinatario, titulo_task)
    except smtplib.SMTPException:
        logger.exception("❌ Falha ao enviar e-mail de convite de task para %s", destinatario)
        raise


def _carregar_template_resposta_convite_task(
    titulo_task: str,
    nome_solicitante: str,
    nome_atribuido: str,
    setor_nome: str,
    aceitou: bool,
) -> str:
    status_str = "Aceito" if aceitou else "Recusado"
    badge_texto = "CONVITE ACEITO" if aceitou else "CONVITE RECUSADO"
    cabecalho = "✅ Convite de Tarefa Aceito" if aceitou else "❌ Convite de Tarefa Recusado"
    atribuido_str = _escape_html(nome_atribuido)
    msg_detalhe = (
        f"<strong>{atribuido_str}</strong> aceitou seu convite para colaborar na tarefa abaixo. Uma cópia independente foi adicionada ao relatório semanal dele(a)."
        if aceitou
        else f"<strong>{atribuido_str}</strong> recusou seu convite para a tarefa abaixo."
    )

    template = _TASK_ATRIBUIDA_TEMPLATE_PATH.read_text(encoding="utf-8")
    frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:5173").rstrip("/")

    return (
        template.replace("{{TITULO_CABECALHO}}", cabecalho)
        .replace("{{DESTINATARIO_NOME}}", _escape_html(nome_solicitante))
        .replace("{{MENSAGEM_DETALHE}}", msg_detalhe)
        .replace("{{BADGE_TEXTO}}", badge_texto)
        .replace("{{TITULO_TASK}}", _escape_html(titulo_task))
        .replace("{{SETOR_NOME}}", _escape_html(setor_nome))
        .replace("{{SOLICITANTE_NOME}}", _escape_html(nome_solicitante))
        .replace("{{CONVIDADO_NOME}}", atribuido_str)
        .replace("{{INFO_EXTRA}}", f'<div class="info-row"><strong>Status do Convite:</strong> {_escape_html(status_str)}</div>')
        .replace("{{FRONTEND_URL}}", frontend_url)
        .replace("{{FROM_NAME}}", _escape_html(settings.SMTP_FROM_NAME))
    )


def enviar_email_resposta_convite_task(
    destinatario: str,
    titulo_task: str,
    nome_solicitante: str,
    nome_atribuido: str,
    setor_nome: str,
    aceitou: bool,
) -> None:
    """Notifica o solicitante sobre o aceite ou recusa do convite da task."""
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        logger.info(
            "📧 [MOCK/DEV] SMTP não configurado. Resposta de convite da task '%s' para %s ignorada.",
            titulo_task,
            destinatario,
        )
        return

    html_body = _carregar_template_resposta_convite_task(
        titulo_task=titulo_task,
        nome_solicitante=nome_solicitante,
        nome_atribuido=nome_atribuido,
        setor_nome=setor_nome,
        aceitou=aceitou,
    )

    status_str = "Aceito" if aceitou else "Recusado"
    msg = MIMEMultipart("alternative")
    titulo_limpo = titulo_task.replace("\r", " ").replace("\n", " ").strip()
    msg["Subject"] = f"[{status_str}] Convite de Tarefa: '{titulo_limpo}' — {settings.SMTP_FROM_NAME}"
    msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
    msg["To"] = destinatario

    frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:5173").rstrip("/")
    texto_puro = (
        f"Resposta ao Convite de Tarefa\n\n"
        f"Olá, {nome_solicitante}!\n"
        f"{nome_atribuido} {status_str.lower()} o convite para a tarefa '{titulo_task}' no setor {setor_nome}.\n\n"
        f"Acesse o painel: {frontend_url}/weeklies\n"
    )
    msg.attach(MIMEText(texto_puro, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            if settings.SMTP_USE_TLS:
                server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.SMTP_FROM_EMAIL, destinatario, msg.as_string())
        logger.info("📧 E-mail de resposta de convite enviado para %s (task: %s, aceitou: %s)", destinatario, titulo_task, aceitou)
    except smtplib.SMTPException:
        logger.exception("❌ Falha ao enviar e-mail de resposta de convite para %s", destinatario)
        raise


def _carregar_template_impedimento(
    titulo_task: str,
    nome_membro: str,
    setor_nome: str,
    impedimento_texto: str,
    semana_referencia: str,
) -> str:
    template = _IMPEDIMENTO_TEMPLATE_PATH.read_text(encoding="utf-8")
    frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:5173").rstrip("/")

    return (
        template.replace("{{TITULO_CABECALHO}}", "⚠️ Novo Impedimento Reportado")
        .replace("{{MEMBRO_NOME}}", _escape_html(nome_membro))
        .replace("{{SETOR_NOME}}", _escape_html(setor_nome))
        .replace("{{TITULO_TASK}}", _escape_html(titulo_task))
        .replace("{{IMPEDIMENTO_TEXTO}}", _escape_html(impedimento_texto, preserve_newlines=True))
        .replace("{{SEMANA_REFERENCIA}}", _escape_html(semana_referencia))
        .replace("{{FRONTEND_URL}}", frontend_url)
        .replace("{{FROM_NAME}}", _escape_html(settings.SMTP_FROM_NAME))
    )


def enviar_email_impedimento(
    destinatario: str,
    titulo_task: str,
    nome_membro: str,
    setor_nome: str,
    impedimento_texto: str,
    semana_referencia: str,
) -> None:
    """Envia notificação por e-mail para líderes e administradores sobre um impedimento relatado."""
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        logger.info(
            "📧 [MOCK/DEV] SMTP não configurado. Notificação de impedimento da task '%s' para %s ignorada.",
            titulo_task,
            destinatario,
        )
        return

    html_body = _carregar_template_impedimento(
        titulo_task=titulo_task,
        nome_membro=nome_membro,
        setor_nome=setor_nome,
        impedimento_texto=impedimento_texto,
        semana_referencia=semana_referencia,
    )

    frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:5173").rstrip("/")
    msg = MIMEMultipart("alternative")
    titulo_limpo = titulo_task.replace("\r", " ").replace("\n", " ").strip()
    membro_limpo = nome_membro.replace("\r", " ").replace("\n", " ").strip()
    msg["Subject"] = f"⚠️ [Impedimento] {membro_limpo} ({setor_nome}): '{titulo_limpo}' — {settings.SMTP_FROM_NAME}"
    msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
    msg["To"] = destinatario

    texto_puro = (
        f"Aviso de Impedimento\n\n"
        f"O membro {nome_membro} relatou um impedimento na tarefa '{titulo_task}' "
        f"do setor {setor_nome} (Semana: {semana_referencia}):\n\n"
        f"\"{impedimento_texto}\"\n\n"
        f"Acesse o painel: {frontend_url}/weeklies\n"
    )
    msg.attach(MIMEText(texto_puro, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            if settings.SMTP_USE_TLS:
                server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.SMTP_FROM_EMAIL, destinatario, msg.as_string())
        logger.info("📧 E-mail de impedimento enviado para %s (task: %s)", destinatario, titulo_task)
    except smtplib.SMTPException:
        logger.exception("❌ Falha ao enviar e-mail de impedimento para %s", destinatario)
        raise





