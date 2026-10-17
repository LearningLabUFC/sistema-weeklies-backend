"""Testes para a Fase 8: Auditoria de Tasks (Task Overdue & Escalation).

Cenários cobertos:
1. Transição automática para EM_AUDITORIA:
   - Tarefas PENDENTES com prazo de conclusão expirado (< hoje) passam para EM_AUDITORIA.
   - entrada_auditoria_em é registrado com o timestamp UTC atual.
   - Tarefas com prazo futuro continuam PENDENTES.
   - Tarefas já CONCLUIDAS ou REMOVIDAS não são alteradas.
   - Notificações por e-mail são disparadas para líderes do setor e admins.

2. Escalonamento automático para administradores:
   - Tarefas em EM_AUDITORIA há >= settings.WEEKLY_AUDIT_ESCALATION_DAYS (7 dias) sem resolução
     são escalonadas para admins por e-mail.
   - Tarefas em auditoria recente (< 7 dias) não são escalonadas.

3. Ações da liderança sobre tarefas em auditoria:
   - PATCH /tasks/{id}/prazo: prorrogar prazo com data válida no futuro restaura status para PENDENTE
     e limpa entrada_auditoria_em.
   - PATCH /tasks/{id}/concluir: líder ou admin pode concluir diretamente a tarefa em auditoria,
     marcando status como CONCLUIDA.
   - DELETE /tasks/{id}: líder ou admin pode remover a tarefa (soft delete para REMOVIDA_PELO_LIDER).

4. Permissões e restrições:
   - Membros comuns não podem acessar GET /tasks/setor/{setor_id}/auditoria (403).
   - Membros comuns não podem executar PATCH /tasks/{id}/concluir (403).
   - Apenas líderes do respectivo setor ou administradores têm permissão.

5. Integração com o APScheduler:
   - executar_verificacao_ausencias aciona a auditoria e retorna as métricas em 'auditoria'.
"""

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.core.constants import RoleID, StatusID, TestID
from app.core.security import criar_token_acesso
from app.models.sector_user import SectorUser
from app.models.task import Task
from app.models.user import User
from app.weeklies.scheduler import executar_verificacao_ausencias
from app.weeklies.service import svc_processar_auditoria_tasks
from app.weeklies.timezone_utils import get_now_fortaleza


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


def test_processar_auditoria_transicao_e_notificacoes(db_session, monkeypatch):
    """Tarefas PENDENTES vencidas devem transitar para EM_AUDITORIA com data de entrada gravada."""
    emails_enviados = []

    def mock_enviar_auditoria(destinatario, **kwargs):
        emails_enviados.append(destinatario)

    monkeypatch.setattr(
        "app.weeklies.service.enviar_email_task_auditoria",
        mock_enviar_auditoria,
    )

    membro = _criar_usuario_com_papel(db_session, "Membro Aud 1", f"A{uuid4().hex[:6]}")
    lider = _criar_usuario_com_papel(
        db_session, "Lider Aud 1", f"L{uuid4().hex[:6]}", papel="lider"
    )

    hoje = date(2026, 10, 1)
    ontem = hoje - timedelta(days=1)
    amanha = hoje + timedelta(days=1)

    # 1. Tarefa vencida pendente -> deve ir para EM_AUDITORIA
    t_vencida = Task(
        usuario_id=membro.user.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Tarefa Vencida",
        descricao="Desc",
        status="PENDENTE",
        prazo_conclusao=ontem,
    )
    # 2. Tarefa no prazo -> continua PENDENTE
    t_no_prazo = Task(
        usuario_id=membro.user.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Tarefa No Prazo",
        descricao="Desc",
        status="PENDENTE",
        prazo_conclusao=amanha,
    )
    # 3. Tarefa vencida já concluída -> não deve ir para auditoria
    t_concluida = Task(
        usuario_id=membro.user.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Tarefa Concluida",
        descricao="Desc",
        status="CONCLUIDA",
        prazo_conclusao=ontem,
    )

    db_session.add_all([t_vencida, t_no_prazo, t_concluida])
    db_session.commit()

    momento_teste = datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc)
    res = svc_processar_auditoria_tasks(db_session, momento=momento_teste)

    db_session.refresh(t_vencida)
    db_session.refresh(t_no_prazo)
    db_session.refresh(t_concluida)

    assert res["novas_em_auditoria"] == 1
    assert t_vencida.status == "EM_AUDITORIA"
    assert t_vencida.entrada_auditoria_em is not None
    assert t_no_prazo.status == "PENDENTE"
    assert t_concluida.status == "CONCLUIDA"

    # Líder do setor deve ter recebido a notificação
    assert lider.user.email in emails_enviados


def test_processar_auditoria_escalonamento_admin(db_session, monkeypatch):
    """Tarefas em auditoria há >= 7 dias devem ser escalonadas para administradores."""
    escalacoes = []

    def mock_escalonamento(destinatario, **kwargs):
        escalacoes.append(destinatario)

    monkeypatch.setattr(
        "app.weeklies.service.enviar_email_escalonamento_auditoria",
        mock_escalonamento,
    )

    admin = _criar_usuario_com_papel(
        db_session, "Admin Global", f"AD{uuid4().hex[:6]}", global_role=RoleID.ADMIN
    )
    membro = _criar_usuario_com_papel(db_session, "Membro Aud 2", f"A{uuid4().hex[:6]}")

    momento_teste = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)

    # Tarefa em auditoria há 8 dias -> escalada
    t_antiga = Task(
        usuario_id=membro.user.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Tarefa Esquecida",
        descricao="Desc",
        status="EM_AUDITORIA",
        prazo_conclusao=date(2026, 9, 30),
        entrada_auditoria_em=datetime(2026, 10, 2, 8, 0, tzinfo=timezone.utc),
    )
    # Tarefa em auditoria recente (2 dias) -> não escalada
    t_recente = Task(
        usuario_id=membro.user.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Tarefa Recente",
        descricao="Desc",
        status="EM_AUDITORIA",
        prazo_conclusao=date(2026, 10, 7),
        entrada_auditoria_em=datetime(2026, 10, 8, 8, 0, tzinfo=timezone.utc),
    )

    db_session.add_all([t_antiga, t_recente])
    db_session.commit()

    res = svc_processar_auditoria_tasks(db_session, momento=momento_teste)

    assert res["escaladas_admin"] >= 1
    escaladas_ids = [d["id"] for d in res["detalhes_escaladas"]]
    assert str(t_antiga.id) in escaladas_ids
    assert str(t_recente.id) not in escaladas_ids
    assert admin.user.email in escalacoes


def test_lider_prorrogar_prazo_restaura_status_pendente(client, db_session):
    """Quando o líder estende o prazo de uma task em EM_AUDITORIA, ela volta para PENDENTE."""
    membro = _criar_usuario_com_papel(db_session, "Membro Aud 3", f"A{uuid4().hex[:6]}")
    lider = _criar_usuario_com_papel(
        db_session, "Lider Aud 3", f"L{uuid4().hex[:6]}", papel="lider"
    )

    t = Task(
        usuario_id=membro.user.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Task Vencida para Prorrogar",
        status="EM_AUDITORIA",
        prazo_conclusao=date(2026, 9, 20),
        entrada_auditoria_em=datetime(2026, 9, 21, 10, 0, tzinfo=timezone.utc),
    )
    db_session.add(t)
    db_session.commit()

    novo_prazo = (get_now_fortaleza().date() + timedelta(days=10)).isoformat()
    resp = client.patch(
        f"/tasks/{t.id}/prazo",
        headers=lider.headers,
        json={"prazo_conclusao": novo_prazo},
    )

    assert resp.status_code == 200
    dados = resp.json()
    assert dados["status"] == "PENDENTE"
    assert dados["entrada_auditoria_em"] is None
    assert dados["prazo_conclusao"] == novo_prazo

    db_session.refresh(t)
    assert t.status == "PENDENTE"
    assert t.entrada_auditoria_em is None


def test_concluir_task_auditoria_por_lider_e_admin(client, db_session):
    """Líder ou Admin pode concluir diretamente uma tarefa em auditoria."""
    membro = _criar_usuario_com_papel(db_session, "Membro Aud 4", f"A{uuid4().hex[:6]}")
    lider = _criar_usuario_com_papel(
        db_session, "Lider Aud 4", f"L{uuid4().hex[:6]}", papel="lider"
    )

    t = Task(
        usuario_id=membro.user.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Task para Concluir na Auditoria",
        status="EM_AUDITORIA",
        prazo_conclusao=date(2026, 9, 20),
        entrada_auditoria_em=datetime(2026, 9, 21, 10, 0, tzinfo=timezone.utc),
    )
    db_session.add(t)
    db_session.commit()

    # Membro comum tentando concluir via rota de liderança -> 403
    resp_membro = client.patch(f"/tasks/{t.id}/concluir", headers=membro.headers)
    assert resp_membro.status_code == 403

    # Líder concluindo -> 200
    resp_lider = client.patch(f"/tasks/{t.id}/concluir", headers=lider.headers)
    assert resp_lider.status_code == 200
    assert resp_lider.json()["status"] == "CONCLUIDA"
    assert resp_lider.json()["entrada_auditoria_em"] is None

    db_session.refresh(t)
    assert t.status == "CONCLUIDA"
    assert t.entrada_auditoria_em is None


def test_soft_delete_task_auditoria(client, db_session):
    """Líder pode remover tarefa em auditoria via DELETE /tasks/{id}."""
    membro = _criar_usuario_com_papel(db_session, "Membro Aud 5", f"A{uuid4().hex[:6]}")
    lider = _criar_usuario_com_papel(
        db_session, "Lider Aud 5", f"L{uuid4().hex[:6]}", papel="lider"
    )

    t = Task(
        usuario_id=membro.user.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Task para Remover",
        status="EM_AUDITORIA",
        prazo_conclusao=date(2026, 9, 20),
        entrada_auditoria_em=datetime(2026, 9, 21, 10, 0, tzinfo=timezone.utc),
    )
    db_session.add(t)
    db_session.commit()

    resp = client.delete(f"/tasks/{t.id}", headers=lider.headers)
    assert resp.status_code == 200

    db_session.refresh(t)
    assert t.status == "REMOVIDA_PELO_LIDER"


def test_listar_tasks_em_auditoria_endpoint(client, db_session):
    """GET /tasks/setor/{setor_id}/auditoria lista tarefas em auditoria com permissão restrita."""
    membro = _criar_usuario_com_papel(db_session, "Membro Aud 6", f"A{uuid4().hex[:6]}")
    lider = _criar_usuario_com_papel(
        db_session, "Lider Aud 6", f"L{uuid4().hex[:6]}", papel="lider"
    )

    t_aud1 = Task(
        usuario_id=membro.user.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Audit 1",
        status="EM_AUDITORIA",
    )
    t_aud2 = Task(
        usuario_id=membro.user.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Audit 2",
        status="EM_AUDITORIA",
    )
    t_pend = Task(
        usuario_id=membro.user.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Pendente Normal",
        status="PENDENTE",
    )
    db_session.add_all([t_aud1, t_aud2, t_pend])
    db_session.commit()

    # Membro sem papel de líder -> 403
    resp_membro = client.get(
        f"/tasks/setor/{TestID.SETOR_TESTE}/auditoria", headers=membro.headers
    )
    assert resp_membro.status_code == 403

    # Líder do setor -> 200 com apenas as tarefas em auditoria
    resp_lider = client.get(
        f"/tasks/setor/{TestID.SETOR_TESTE}/auditoria", headers=lider.headers
    )
    assert resp_lider.status_code == 200
    dados = resp_lider.json()
    assert dados["total"] >= 2
    titulos = [item["titulo"] for item in dados["tasks"]]
    assert "Audit 1" in titulos
    assert "Audit 2" in titulos
    assert "Pendente Normal" not in titulos


def test_scheduler_integra_auditoria(db_session):
    """executar_verificacao_ausencias deve disparar também a auditoria de tasks."""
    res = executar_verificacao_ausencias(db_session)
    assert "auditoria" in res
    assert "novas_em_auditoria" in res["auditoria"]
    assert "escaladas_admin" in res["auditoria"]


def test_governanca_auditoria_tasks_lider(client, db_session):
    """Garante que líderes não possam auto-concluir ou auto-prorrogar suas tarefas em auditoria,
    e que tarefas de líderes em auditoria exijam resolução por Administrador.
    """
    lider_autor = _criar_usuario_com_papel(
        db_session, "Lider Autor", f"LA{uuid4().hex[:6]}", papel="lider"
    )
    lider_par = _criar_usuario_com_papel(
        db_session, "Lider Par", f"LP{uuid4().hex[:6]}", papel="lider"
    )
    admin = _criar_usuario_com_papel(
        db_session, "Admin Geral", f"AG{uuid4().hex[:6]}", global_role=RoleID.ADMIN
    )

    task_lider = Task(
        usuario_id=lider_autor.user.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Task do Líder Atrasada",
        status="EM_AUDITORIA",
        prazo_conclusao=date(2026, 9, 20),
    )
    db_session.add(task_lider)
    db_session.commit()

    # 1. Líder autor tenta concluir a própria tarefa em auditoria -> 403
    resp_auto = client.patch(
        f"/tasks/{task_lider.id}/concluir",
        headers=lider_autor.headers,
    )
    assert resp_auto.status_code == 403
    assert "Você não pode concluir a sua própria tarefa em auditoria" in resp_auto.json()["detail"]

    # 2. Co-líder tenta concluir tarefa de outro líder em auditoria -> 403
    resp_par = client.patch(
        f"/tasks/{task_lider.id}/concluir",
        headers=lider_par.headers,
    )
    assert resp_par.status_code == 403
    assert "Tarefas de líderes em auditoria só podem ser concluídas por administradores" in resp_par.json()["detail"]

    # 3. Líder autor tenta prorrogar a própria tarefa em auditoria para fugir da auditoria -> 403
    futuro = (datetime.now(timezone.utc).date() + timedelta(days=10)).isoformat()
    resp_auto_prazo = client.patch(
        f"/tasks/{task_lider.id}/prazo",
        headers=lider_autor.headers,
        json={"prazo_conclusao": futuro},
    )
    assert resp_auto_prazo.status_code == 403
    assert "Você não pode alterar o prazo da sua própria tarefa em auditoria" in resp_auto_prazo.json()["detail"]

    # 4. Admin conclui tarefa do líder em auditoria -> 200
    resp_admin = client.patch(
        f"/tasks/{task_lider.id}/concluir",
        headers=admin.headers,
    )
    assert resp_admin.status_code == 200
    assert resp_admin.json()["status"] == "CONCLUIDA"

