"""Testes para o serviço de e-mail e prevenção de HTML injection / phishing (app.core.email).

Cenários cobertos:
1. Função auxiliar _escape_html:
   - Sanitização de caracteres perigosos (<, >, &, ", ')
   - Conversão segura de quebras de linha com preserve_newlines=True
   - Tratamento de valores None e não-strings
2. Template de impedimento (_carregar_template_impedimento):
   - Eliminação de links de phishing e tags HTML no texto do impedimento
   - Escapamento de tags no título da task, nome do membro e setor
3. Template de auditoria e escalonamento (_carregar_template_task_auditoria, _carregar_template_escalonamento_auditoria):
   - Escapamento de dados de usuário e tarefa
4. Template de atribuição de tarefas (_carregar_template_convite_task, _carregar_template_resposta_convite_task):
   - Escapamento em convites e respostas
5. Template de advertência e OTP (_carregar_template_advertencia, _carregar_template_otp):
   - Escapamento de dados em notificações disciplinares e autenticação
6. Envio com SMTP mockado (enviar_email_impedimento):
   - Garante que a mensagem MIME gerada contém corpo HTML sanitizado e Subject limpo
"""

from unittest.mock import MagicMock, patch

from app.core.email import (
    _carregar_template_advertencia,
    _carregar_template_convite_task,
    _carregar_template_escalonamento_auditoria,
    _carregar_template_impedimento,
    _carregar_template_otp,
    _carregar_template_resposta_convite_task,
    _carregar_template_task_auditoria,
    _escape_html,
    enviar_email_impedimento,
)


def test_escape_html_helper():
    """Valida o escapamento de caracteres especiais e quebras de linha."""
    # Caracteres HTML perigosos
    raw = '<script>alert("xss & phishing")</script>\'test\''
    escaped = _escape_html(raw)
    assert "<script>" not in escaped
    assert "</script>" not in escaped
    assert "&lt;script&gt;" in escaped
    assert "&amp;" in escaped
    assert "&quot;" in escaped
    assert "&#x27;" in escaped

    # None e números
    assert _escape_html(None) == ""
    assert _escape_html(42) == "42"

    # Quebras de linha preservadas de forma segura
    multiline = "Linha 1\n<img src=x onerror=alert(1)>\nLinha 2"
    multiline_escaped = _escape_html(multiline, preserve_newlines=True)
    assert "<img" not in multiline_escaped
    assert "&lt;img src=x onerror=alert(1)&gt;" in multiline_escaped
    assert "<br />\n" in multiline_escaped


def test_impedimento_template_escapa_links_e_scripts():
    """Garante que tags HTML injetadas no impedimento não são renderizadas como tags no e-mail."""
    phishing_payload = '<a href="https://phishing.site/login">Clique para validar seu acesso</a>'
    task_payload = 'Refatorar módulo <b style="color:red">Urgente</b> & crítico'
    membro_payload = 'João <script>alert("pwned")</script> Silva'
    setor_payload = 'Dev & Inovação <u>Oficial</u>'

    html_result = _carregar_template_impedimento(
        titulo_task=task_payload,
        nome_membro=membro_payload,
        setor_nome=setor_payload,
        impedimento_texto=f"Aviso:\n{phishing_payload}\nEntrar em contato.",
        semana_referencia="2026-10-05",
    )

    # Nenhuma tag maliciosa crua deve existir no HTML
    assert '<a href="https://phishing.site/login">' not in html_result
    assert "<script>" not in html_result
    assert "<b style=" not in html_result
    assert "<u>" not in html_result

    # Devem estar devidamente escapadas como entidades HTML
    assert "&lt;a href=&quot;https://phishing.site/login&quot;&gt;" in html_result
    assert "&lt;script&gt;alert(&quot;pwned&quot;)&lt;/script&gt;" in html_result
    assert "&lt;b style=&quot;color:red&quot;&gt;Urgente&lt;/b&gt;" in html_result
    assert "&amp; crítico" in html_result
    assert "&amp; Inovação" in html_result
    assert "<br />\n" in html_result


def test_convite_task_template_escapa_html():
    """Garante que convites de tasks escapam dados de solicitante, convidado e tarefa."""
    html_result = _carregar_template_convite_task(
        titulo_task='Deploy <iframe src="evil.com"></iframe>',
        nome_solicitante='Líder <strong>Admin</strong>',
        nome_atribuido='Membro <script>steal()</script>',
        setor_nome='Setor & TI',
        prazo_conclusao='10/10/2026 <img src=x>',
    )

    assert "<iframe" not in html_result
    assert "&lt;iframe src=&quot;evil.com&quot;&gt;" in html_result
    assert "<script>" not in html_result
    assert "&lt;script&gt;steal()&lt;/script&gt;" in html_result
    assert "&lt;strong&gt;Admin&lt;/strong&gt;" in html_result
    assert "&lt;img src=x&gt;" in html_result


def test_resposta_convite_task_template_escapa_html():
    """Garante que a resposta ao convite escapa dados de todas as partes."""
    html_result = _carregar_template_resposta_convite_task(
        titulo_task='Task "Crítica"',
        nome_solicitante='Solicitante <script>',
        nome_atribuido='Convidado <style id="malicious">',
        setor_nome='Setor <dev>',
        aceitou=True,
    )

    assert "<script>" not in html_result
    assert '<style id="malicious">' not in html_result
    assert '&lt;style id=&quot;malicious&quot;&gt;' in html_result
    assert "<dev>" not in html_result
    assert "&quot;Crítica&quot;" in html_result


def test_auditoria_template_escapa_html():
    """Garante que os templates de auditoria e escalonamento escapam dados de entrada."""
    html_audit = _carregar_template_task_auditoria(
        titulo_task='Task com <a href="x">link</a>',
        nome_membro='Autor <script>',
        setor_nome='Setor & CIA',
        prazo_conclusao='2026-10-01',
    )
    assert '<a href="x">' not in html_audit
    assert "&lt;a href=&quot;x&quot;&gt;" in html_audit
    assert "<script>" not in html_audit
    assert "&amp; CIA" in html_audit

    html_escala = _carregar_template_escalonamento_auditoria(
        titulo_task='Task <script>alert(1)</script>',
        nome_membro='Membro <b>Nome</b>',
        setor_nome='Setor <i>Teste</i>',
        dias_em_auditoria=10,
    )
    assert "<script>" not in html_escala
    assert "<b>" not in html_escala
    assert "<i>" not in html_escala
    assert "PARADA HÁ 10 DIAS" in html_escala


def test_advertencia_e_otp_templates_escapam_html():
    """Garante que templates de advertência e OTP escapam nomes e entradas."""
    html_adv = _carregar_template_advertencia(
        nome_membro='João <svg onload=alert(1)>',
        tipo="1a_ADVERTENCIA",
        semanas_ausentes=2,
        setor_nome='Setor <Hack>',
        semana_referencia='2026-09-28',
    )
    assert "<svg" not in html_adv
    assert "&lt;svg onload=alert(1)&gt;" in html_adv
    assert "<Hack>" not in html_adv

    html_otp = _carregar_template_otp(
        codigo='<123456>',
        destinatario='teste@ufc.br',
    )
    assert "<123456>" not in html_otp
    assert "&lt;123456&gt;" in html_otp


@patch("app.core.email.settings")
@patch("app.core.email.smtplib.SMTP")
def test_enviar_email_impedimento_gera_html_escapado_e_subject_sanitizado(mock_smtp_cls, mock_settings):
    """Garante que a função enviar_email_impedimento anexa o HTML devidamente escapado na mensagem MIME."""
    import email

    mock_settings.SMTP_USER = "user@test.com"
    mock_settings.SMTP_PASSWORD = "secret_password"
    mock_settings.SMTP_HOST = "smtp.test.com"
    mock_settings.SMTP_PORT = 587
    mock_settings.SMTP_USE_TLS = False
    mock_settings.SMTP_FROM_NAME = "LearningLab"
    mock_settings.SMTP_FROM_EMAIL = "noreply@learninglab.ufc.br"
    mock_settings.FRONTEND_URL = "http://localhost:5173"

    mock_server = MagicMock()
    mock_smtp_cls.return_value.__enter__.return_value = mock_server

    phishing_link = '<a href="https://malicious.org">Atualize seu acesso</a>'
    enviar_email_impedimento(
        destinatario="lider@ufc.br",
        titulo_task="Configurar servidor\r\nCRLF",
        nome_membro="Membro <Injetor>",
        setor_nome="Infra",
        impedimento_texto=f"Erro grave:\n{phishing_link}",
        semana_referencia="2026-10-05",
    )

    # Verifica se sendmail foi chamado
    assert mock_server.sendmail.called
    args, _ = mock_server.sendmail.call_args
    assert args[0] == "noreply@learninglab.ufc.br"
    assert args[1] == "lider@ufc.br"
    raw_message = args[2]

    # Decodifica a mensagem MIME
    parsed_msg = email.message_from_string(raw_message)
    html_parts = [
        part.get_payload(decode=True).decode("utf-8")
        for part in parsed_msg.walk()
        if part.get_content_type() == "text/html"
    ]
    assert len(html_parts) == 1
    html_content = html_parts[0]

    # O corpo HTML MIME não deve conter a tag <a href= não escapada
    assert '<a href="https://malicious.org">' not in html_content
    assert "&lt;a href=&quot;https://malicious.org&quot;&gt;" in html_content

    # O Subject não deve conter quebras de linha CRLF
    subject_raw = parsed_msg.get("Subject", "")
    assert "\r" not in subject_raw
    assert "\n" not in subject_raw
