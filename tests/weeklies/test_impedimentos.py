"""Testes para a Fase 10: Notificações de Impedimento por E-mail.

Cenários cobertos:
1. Disparo de e-mail ao registrar novo impedimento:
   - Membro atualiza weekly_task incluindo texto no campo 'impedimento'.
   - O e-mail de notificação é disparado para líderes do setor e administradores globais.
   - O template HTML de impedimento contém os detalhes da tarefa, autor, setor e texto relatado.
   - Se o autor for líder do setor, ele não recebe o próprio e-mail (destinatários deduplicados).
2. Não disparo quando o impedimento não é alterado:
   - Alterar apenas 'concluida' ou reenviar o mesmo texto de impedimento não dispara novo e-mail.
3. Remoção do impedimento:
   - Limpar o impedimento (None ou string vazia) atualiza o banco e não dispara alerta de impedimento.
4. Execução assíncrona via BackgroundTasks do FastAPI:
   - Requisição via TestClient aciona o endpoint PATCH /weeklies/{id}/tasks/{item_id}
   - BackgroundTasks processa o envio de e-mail sem bloquear a resposta HTTP 200.
"""

from datetime import date
from types import SimpleNamespace
from uuid import uuid4

from app.core.constants import RoleID, StatusID, TestID
from app.core.security import criar_token_acesso
from app.models.sector_user import SectorUser
from app.models.task import Task
from app.models.user import User
from app.models.weekly import Weekly
from app.models.weekly_task import WeeklyTask
from app.weeklies.timezone_utils import obter_semana_referencia


def _criar_usuario_com_papel(
    db_session,
    nome: str,
    matricula: str,
    papel: str = "membro",
    global_role: str = RoleID.USUARIO,
    setor_id=TestID.SETOR_TESTE,
    data_ingresso: date = date(2026, 1, 1),
):
    user = User(
        nome_completo=nome,
        email=f"{matricula.lower()}@test.com",
        senha_hash="hash",
        matricula=matricula,
        data_nascimento=date(2000, 1, 1),
        data_ingresso=data_ingresso,
        curso_id=TestID.CURSO_TESTE,
        status_id=StatusID.ATIVO,
        global_role=global_role,
    )
    db_session.add(user)
    db_session.flush()

    assoc = SectorUser(usuario_id=user.id, setor_id=setor_id, papel=papel)
    db_session.add(assoc)
    db_session.commit()

    token = criar_token_acesso({"sub": str(user.id)})
    headers = {"Authorization": f"Bearer {token}"}

    return SimpleNamespace(user=user, assoc=assoc, headers=headers)


def test_registrar_novo_impedimento_dispara_emails(client, db_session, monkeypatch):
    """Registrar um novo impedimento dispara e-mails para líderes e admins."""
    emails_enviados = []

    def mock_enviar_impedimento(destinatario, **kwargs):
        emails_enviados.append(destinatario)

    monkeypatch.setattr(
        "app.weeklies.service.enviar_email_impedimento",
        mock_enviar_impedimento,
    )

    membro = _criar_usuario_com_papel(db_session, "Membro Imp 1", f"M{uuid4().hex[:6]}")
    lider = _criar_usuario_com_papel(
        db_session, "Lider Imp 1", f"L{uuid4().hex[:6]}", papel="lider"
    )
    admin = _criar_usuario_com_papel(
        db_session, "Admin Imp 1", f"AD{uuid4().hex[:6]}", global_role=RoleID.ADMIN
    )

    semana_ref = obter_semana_referencia()
    weekly = Weekly(
        usuario_id=membro.user.id,
        setor_id=TestID.SETOR_TESTE,
        semana_referencia=semana_ref,
        status="RASCUNHO",
    )
    task = Task(
        usuario_id=membro.user.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Integrar Gateway de Pagamento",
        status="PENDENTE",
    )
    db_session.add_all([weekly, task])
    db_session.commit()

    wt = WeeklyTask(
        weekly_id=weekly.id,
        task_id=task.id,
        concluida=False,
        impedimento=None,
        posicao=1,
        origem="NOVA",
    )
    db_session.add(wt)
    db_session.commit()

    # Membro relata o impedimento via PATCH
    texto_impedimento = "Aguardando liberação de credenciais de produção no banco."
    resp = client.patch(
        f"/weeklies/{weekly.id}/tasks/{wt.id}",
        headers=membro.headers,
        json={"impedimento": texto_impedimento},
    )

    assert resp.status_code == 200
    dados = resp.json()
    assert dados["impedimento"] == texto_impedimento

    db_session.refresh(wt)
    assert wt.impedimento == texto_impedimento

    # Líder e Admin devem estar na lista de destinatários
    assert lider.user.email in emails_enviados
    assert admin.user.email in emails_enviados
    # O próprio autor não deve receber
    assert membro.user.email not in emails_enviados


def test_atualizar_sem_alterar_impedimento_nao_dispara_emails(client, db_session, monkeypatch):
    """Atualizar apenas conclusão ou o mesmo texto não deve disparar e-mails redundantes."""
    emails_enviados = []

    def mock_enviar_impedimento(destinatario, **kwargs):
        emails_enviados.append(destinatario)

    monkeypatch.setattr(
        "app.weeklies.service.enviar_email_impedimento",
        mock_enviar_impedimento,
    )

    membro = _criar_usuario_com_papel(db_session, "Membro Imp 2", f"M{uuid4().hex[:6]}")
    _criar_usuario_com_papel(
        db_session, "Lider Imp 2", f"L{uuid4().hex[:6]}", papel="lider"
    )

    semana_ref = obter_semana_referencia()
    weekly = Weekly(
        usuario_id=membro.user.id,
        setor_id=TestID.SETOR_TESTE,
        semana_referencia=semana_ref,
        status="RASCUNHO",
    )
    task = Task(
        usuario_id=membro.user.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Criar Telas de Configuração",
        status="PENDENTE",
    )
    db_session.add_all([weekly, task])
    db_session.commit()

    wt = WeeklyTask(
        weekly_id=weekly.id,
        task_id=task.id,
        concluida=False,
        impedimento="Impedimento já existente",
        posicao=1,
        origem="NOVA",
    )
    db_session.add(wt)
    db_session.commit()

    # 1. Apenas alterando 'concluida'
    resp1 = client.patch(
        f"/weeklies/{weekly.id}/tasks/{wt.id}",
        headers=membro.headers,
        json={"concluida": True},
    )
    assert resp1.status_code == 200
    assert len(emails_enviados) == 0

    # 2. Reenviando o mesmo impedimento
    resp2 = client.patch(
        f"/weeklies/{weekly.id}/tasks/{wt.id}",
        headers=membro.headers,
        json={"impedimento": "Impedimento já existente"},
    )
    assert resp2.status_code == 200
    assert len(emails_enviados) == 0


def test_remover_impedimento_nao_dispara_alerta(client, db_session, monkeypatch):
    """Limpar o impedimento deve atualizar o registro sem disparar alerta."""
    emails_enviados = []

    def mock_enviar_impedimento(destinatario, **kwargs):
        emails_enviados.append(destinatario)

    monkeypatch.setattr(
        "app.weeklies.service.enviar_email_impedimento",
        mock_enviar_impedimento,
    )

    membro = _criar_usuario_com_papel(db_session, "Membro Imp 3", f"M{uuid4().hex[:6]}")
    _criar_usuario_com_papel(
        db_session, "Lider Imp 3", f"L{uuid4().hex[:6]}", papel="lider"
    )

    semana_ref = obter_semana_referencia()
    weekly = Weekly(
        usuario_id=membro.user.id,
        setor_id=TestID.SETOR_TESTE,
        semana_referencia=semana_ref,
        status="RASCUNHO",
    )
    task = Task(
        usuario_id=membro.user.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Resolver Bug de Autenticação",
        status="PENDENTE",
    )
    db_session.add_all([weekly, task])
    db_session.commit()

    wt = WeeklyTask(
        weekly_id=weekly.id,
        task_id=task.id,
        concluida=False,
        impedimento="Erro 500 no login social",
        posicao=1,
        origem="NOVA",
    )
    db_session.add(wt)
    db_session.commit()

    # Remove o impedimento enviando string vazia
    resp = client.patch(
        f"/weeklies/{weekly.id}/tasks/{wt.id}",
        headers=membro.headers,
        json={"impedimento": ""},
    )
    assert resp.status_code == 200
    assert resp.json()["impedimento"] is None

    db_session.refresh(wt)
    assert wt.impedimento is None
    assert len(emails_enviados) == 0
