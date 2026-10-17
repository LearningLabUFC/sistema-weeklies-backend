"""Testes para a Fase 9: Atribuição de Tasks (Convite, Aceite, Recusa e Clonagem Independente).

Cenários cobertos:
1. Envio de convite:
   - Proprietário da task convida outro membro do mesmo setor (201, PENDENTE).
   - Disparo de notificação por e-mail para o membro convidado.
2. Validações e restrições de convite:
   - Convidar a si mesmo -> 400.
   - Convidar o próprio dono da task -> 400.
   - Convidado sem vínculo com o setor -> 403.
   - Task não PENDENTE (ex.: CONCLUIDA) -> 400.
   - Usuário não-proprietário e não-líder tentando convidar -> 403.
   - Convite duplicado em status PENDENTE para o mesmo membro e tarefa -> 409 Conflict.
3. Aceite de convite e clonagem independente:
   - Membro convidado aceita o convite (200, ACEITA).
   - Uma nova task independente é criada para o membro convidado com origem_task_id apontando para a original.
   - A independência é preservada (concluir a original não conclui a clonada).
   - Notificação por e-mail enviada para o solicitante.
4. Vinculação automática à weekly em rascunho:
   - Se o membro convidado já tiver weekly em RASCUNHO na semana atual, a task clonada é adicionada a ela.
5. Recusa de convite:
   - Membro convidado recusa o convite (200, RECUSADA).
   - Nenhuma tarefa nova é criada.
   - Notificação por e-mail enviada para o solicitante.
6. Permissões de resposta e idempotência:
   - Terceiros tentando aceitar/recusar o convite -> 403.
   - Tentar responder convite já respondido -> 400.
7. Consulta e listagem:
   - GET /atribuicoes/me (recebidas e enviadas, com filtros e paginação).
"""

from datetime import date, datetime
from types import SimpleNamespace
from uuid import uuid4

from app.core.constants import RoleID, StatusID, TestID
from app.core.security import criar_token_acesso
from app.models.sector_user import SectorUser
from app.models.task import Task
from app.models.task_assignment import TaskAssignment
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


def test_criar_convite_atribuicao_sucesso(client, db_session, monkeypatch):
    """Proprietário da task pode convidar outro membro do setor com sucesso."""
    emails_convite = []

    def mock_convite(destinatario, **kwargs):
        emails_convite.append(destinatario)

    monkeypatch.setattr(
        "app.weeklies.service.enviar_email_convite_task",
        mock_convite,
    )

    membro_a = _criar_usuario_com_papel(db_session, "Membro A", f"A{uuid4().hex[:6]}")
    membro_b = _criar_usuario_com_papel(db_session, "Membro B", f"B{uuid4().hex[:6]}")

    task = Task(
        usuario_id=membro_a.user.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Criar Documentação de Arquitetura",
        descricao="Detalhar módulos e integração",
        status="PENDENTE",
        prazo_conclusao=date(2026, 10, 20),
    )
    db_session.add(task)
    db_session.commit()

    resp = client.post(
        f"/tasks/{task.id}/atribuir",
        headers=membro_a.headers,
        json={"atribuido_id": str(membro_b.user.id)},
    )

    assert resp.status_code == 201
    dados = resp.json()
    assert dados["task_id"] == str(task.id)
    assert dados["solicitante_id"] == str(membro_a.user.id)
    assert dados["atribuido_id"] == str(membro_b.user.id)
    assert dados["status"] == "PENDENTE"
    assert dados["respondido_em"] is None

    # E-mail enviado para o membro convidado
    assert membro_b.user.email in emails_convite


def test_criar_convite_atribuicao_validacoes(client, db_session):
    """Valida regras de negócio ao tentar criar um convite de atribuição."""
    membro_a = _criar_usuario_com_papel(db_session, "Membro A Valid", f"A{uuid4().hex[:6]}")
    membro_b = _criar_usuario_com_papel(db_session, "Membro B Valid", f"B{uuid4().hex[:6]}")
    membro_c = _criar_usuario_com_papel(db_session, "Membro C Valid", f"C{uuid4().hex[:6]}")

    # Membro sem vínculo com SETOR_TESTE
    user_sem_vinculo = User(
        nome_completo="Membro Sem Vinculo",
        email=f"sv{uuid4().hex[:6]}@test.com",
        senha_hash="hash",
        matricula=f"SV{uuid4().hex[:5]}",
        data_nascimento=date(2000, 1, 1),
        data_ingresso=date(2026, 1, 1),
        curso_id=TestID.CURSO_TESTE,
        status_id=StatusID.ATIVO,
        global_role=RoleID.USUARIO,
    )
    db_session.add(user_sem_vinculo)
    db_session.commit()


    task = Task(
        usuario_id=membro_a.user.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Task para Validações",
        status="PENDENTE",
    )
    task_concluida = Task(
        usuario_id=membro_a.user.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Task Concluida",
        status="CONCLUIDA",
    )
    db_session.add_all([task, task_concluida])
    db_session.commit()

    # 1. Convidar a si mesmo -> 400
    resp_self = client.post(
        f"/tasks/{task.id}/atribuir",
        headers=membro_a.headers,
        json={"atribuido_id": str(membro_a.user.id)},
    )
    assert resp_self.status_code == 400
    assert "si mesmo" in resp_self.json()["detail"]

    # 2. Convidar quem já é o dono da tarefa -> 400
    lider = _criar_usuario_com_papel(
        db_session, "Lider Setor", f"L{uuid4().hex[:6]}", papel="lider"
    )
    resp_dono = client.post(
        f"/tasks/{task.id}/atribuir",
        headers=lider.headers,
        json={"atribuido_id": str(membro_a.user.id)},
    )
    assert resp_dono.status_code == 400
    assert "já pertence" in resp_dono.json()["detail"]

    # 3. Convidar Super Admin -> 403 Forbidden
    super_admin = User(
        nome_completo="Super Admin General",
        email=f"sa{uuid4().hex[:6]}@test.com",
        senha_hash="hash",
        matricula=f"SA{uuid4().hex[:4]}",
        data_nascimento=date(2000, 1, 1),
        data_ingresso=date(2026, 1, 1),
        curso_id=TestID.CURSO_TESTE,
        status_id=StatusID.ATIVO,
        global_role=RoleID.SUPER_ADMIN,
    )
    db_session.add(super_admin)
    db_session.commit()

    resp_sa = client.post(
        f"/tasks/{task.id}/atribuir",
        headers=membro_a.headers,
        json={"atribuido_id": str(super_admin.id)},
    )
    assert resp_sa.status_code == 403
    assert "super administrador" in resp_sa.json()["detail"].lower()

    # 3.1. Convidado sem vínculo prévio no setor -> 403 Forbidden
    resp_sem_vinculo = client.post(
        f"/tasks/{task.id}/atribuir",
        headers=membro_a.headers,
        json={"atribuido_id": str(user_sem_vinculo.id)},
    )
    assert resp_sem_vinculo.status_code == 403
    assert any(term in resp_sem_vinculo.json()["detail"].lower() for term in ("vinculado", "vínculo"))

    # 4. Task não PENDENTE -> 400
    resp_concl = client.post(
        f"/tasks/{task_concluida.id}/atribuir",
        headers=membro_a.headers,
        json={"atribuido_id": str(membro_b.user.id)},
    )
    assert resp_concl.status_code == 400

    # 5. Membro C (não dono, não líder) tentando convidar -> 403
    resp_terceiro = client.post(
        f"/tasks/{task.id}/atribuir",
        headers=membro_c.headers,
        json={"atribuido_id": str(membro_b.user.id)},
    )
    assert resp_terceiro.status_code == 403

    # 6. Convite duplicado pendente -> 409
    resp_ok = client.post(
        f"/tasks/{task.id}/atribuir",
        headers=membro_a.headers,
        json={"atribuido_id": str(membro_b.user.id)},
    )
    assert resp_ok.status_code == 201

    resp_dup = client.post(
        f"/tasks/{task.id}/atribuir",
        headers=membro_a.headers,
        json={"atribuido_id": str(membro_b.user.id)},
    )
    assert resp_dup.status_code == 409


def test_aceitar_convite_clona_task_independente(client, db_session, monkeypatch):
    """Ao aceitar, o convite vira ACEITA e uma nova task independente é criada."""
    emails_resposta = []

    def mock_resposta(destinatario, **kwargs):
        emails_resposta.append(destinatario)

    monkeypatch.setattr(
        "app.weeklies.service.enviar_email_resposta_convite_task",
        mock_resposta,
    )

    membro_a = _criar_usuario_com_papel(db_session, "Membro A Clone", f"A{uuid4().hex[:6]}")
    membro_b = _criar_usuario_com_papel(db_session, "Membro B Clone", f"B{uuid4().hex[:6]}")

    task = Task(
        usuario_id=membro_a.user.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Tarefa Compartilhada",
        descricao="Desc Compartilhada",
        status="PENDENTE",
        prazo_conclusao=date(2026, 11, 1),
    )
    db_session.add(task)
    db_session.commit()

    assignment = TaskAssignment(
        task_id=task.id,
        solicitante_id=membro_a.user.id,
        atribuido_id=membro_b.user.id,
        status="PENDENTE",
    )
    db_session.add(assignment)
    db_session.commit()

    resp = client.patch(
        f"/atribuicoes/{assignment.id}/aceitar",
        headers=membro_b.headers,
    )
    assert resp.status_code == 200
    dados = resp.json()
    assert dados["status"] == "ACEITA"
    assert dados["respondido_em"] is not None

    # Verifica se a nova tarefa clonada foi criada para o Membro B
    task_clonada = (
        db_session.query(Task)
        .filter(Task.usuario_id == membro_b.user.id, Task.origem_task_id == task.id)
        .first()
    )
    assert task_clonada is not None
    assert task_clonada.titulo == task.titulo
    assert task_clonada.descricao == task.descricao
    assert task_clonada.setor_id == task.setor_id
    assert task_clonada.status == "PENDENTE"
    assert task_clonada.prazo_conclusao == task.prazo_conclusao

    # Ciclo de vida independente: concluir a original não afeta a clonada
    task.status = "CONCLUIDA"
    db_session.commit()
    db_session.refresh(task_clonada)
    assert task_clonada.status == "PENDENTE"

    # Solicitante Membro A deve ter sido notificado por e-mail
    assert membro_a.user.email in emails_resposta


def test_aceitar_convite_vincula_a_weekly_em_rascunho(client, db_session):
    """Se o convidado possuir weekly em RASCUNHO na semana atual, a task clonada é vinculada a ela."""
    membro_a = _criar_usuario_com_papel(db_session, "Membro A Wk", f"A{uuid4().hex[:6]}")
    membro_b = _criar_usuario_com_papel(db_session, "Membro B Wk", f"B{uuid4().hex[:6]}")

    semana_ref = obter_semana_referencia()
    weekly_b = Weekly(
        usuario_id=membro_b.user.id,
        setor_id=TestID.SETOR_TESTE,
        semana_referencia=semana_ref,
        status="RASCUNHO",
    )
    task = Task(
        usuario_id=membro_a.user.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Task Vinculo Weekly",
        status="PENDENTE",
    )
    db_session.add_all([weekly_b, task])
    db_session.commit()

    assignment = TaskAssignment(
        task_id=task.id,
        solicitante_id=membro_a.user.id,
        atribuido_id=membro_b.user.id,
        status="PENDENTE",
    )
    db_session.add(assignment)
    db_session.commit()

    resp = client.patch(
        f"/tasks/atribuicoes/{assignment.id}/aceitar",
        headers=membro_b.headers,
    )
    assert resp.status_code == 200

    # Verifica se a WeeklyTask foi criada na weekly do Membro B
    task_clonada = (
        db_session.query(Task)
        .filter(Task.usuario_id == membro_b.user.id, Task.origem_task_id == task.id)
        .first()
    )
    assert task_clonada is not None

    weekly_item = (
        db_session.query(WeeklyTask)
        .filter(
            WeeklyTask.weekly_id == weekly_b.id,
            WeeklyTask.task_id == task_clonada.id,
        )
        .first()
    )
    assert weekly_item is not None
    assert weekly_item.origem == "NOVA"
    assert weekly_item.concluida is False


def test_recusar_convite_atribuicao(client, db_session, monkeypatch):
    """Ao recusar, o convite vira RECUSADA e nenhuma task é clonada."""
    emails_recusa = []

    def mock_recusa(destinatario, **kwargs):
        emails_recusa.append(destinatario)

    monkeypatch.setattr(
        "app.weeklies.service.enviar_email_resposta_convite_task",
        mock_recusa,
    )

    membro_a = _criar_usuario_com_papel(db_session, "Membro A Recusa", f"A{uuid4().hex[:6]}")
    membro_b = _criar_usuario_com_papel(db_session, "Membro B Recusa", f"B{uuid4().hex[:6]}")

    task = Task(
        usuario_id=membro_a.user.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Task para Recusa",
        status="PENDENTE",
    )
    db_session.add(task)
    db_session.commit()

    assignment = TaskAssignment(
        task_id=task.id,
        solicitante_id=membro_a.user.id,
        atribuido_id=membro_b.user.id,
        status="PENDENTE",
    )
    db_session.add(assignment)
    db_session.commit()

    resp = client.patch(
        f"/atribuicoes/{assignment.id}/recusar",
        headers=membro_b.headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "RECUSADA"

    # Nenhuma task criada para Membro B
    task_clonada = (
        db_session.query(Task)
        .filter(Task.usuario_id == membro_b.user.id, Task.origem_task_id == task.id)
        .first()
    )
    assert task_clonada is None
    assert membro_a.user.email in emails_recusa


def test_responder_convite_permissoes_e_idempotencia(client, db_session):
    """Apenas o membro convidado pode responder e não pode responder duas vezes."""
    membro_a = _criar_usuario_com_papel(db_session, "Membro A Idemp", f"A{uuid4().hex[:6]}")
    membro_b = _criar_usuario_com_papel(db_session, "Membro B Idemp", f"B{uuid4().hex[:6]}")
    membro_c = _criar_usuario_com_papel(db_session, "Membro C Idemp", f"C{uuid4().hex[:6]}")

    task = Task(
        usuario_id=membro_a.user.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Task Idempotencia",
        status="PENDENTE",
    )
    db_session.add(task)
    db_session.commit()

    assignment = TaskAssignment(
        task_id=task.id,
        solicitante_id=membro_a.user.id,
        atribuido_id=membro_b.user.id,
        status="PENDENTE",
    )
    db_session.add(assignment)
    db_session.commit()

    # Membro C tenta aceitar -> 403
    resp_alheio = client.patch(
        f"/atribuicoes/{assignment.id}/aceitar",
        headers=membro_c.headers,
    )
    assert resp_alheio.status_code == 403

    # Membro B aceita -> 200
    resp_ok = client.patch(
        f"/atribuicoes/{assignment.id}/aceitar",
        headers=membro_b.headers,
    )
    assert resp_ok.status_code == 200

    # Membro B tenta recusar depois de já ter aceito -> 400
    resp_segunda_vez = client.patch(
        f"/atribuicoes/{assignment.id}/recusar",
        headers=membro_b.headers,
    )
    assert resp_segunda_vez.status_code == 400


def test_listar_meus_convites_endpoint(client, db_session):
    """GET /atribuicoes/me lista convites recebidos e enviados com filtros."""
    membro_a = _criar_usuario_com_papel(db_session, "Membro A List", f"A{uuid4().hex[:6]}")
    membro_b = _criar_usuario_com_papel(db_session, "Membro B List", f"B{uuid4().hex[:6]}")

    task1 = Task(usuario_id=membro_a.user.id, setor_id=TestID.SETOR_TESTE, titulo="Task 1", status="PENDENTE")
    task2 = Task(usuario_id=membro_b.user.id, setor_id=TestID.SETOR_TESTE, titulo="Task 2", status="PENDENTE")
    db_session.add_all([task1, task2])
    db_session.commit()

    # A convidou B para Task 1
    a1 = TaskAssignment(task_id=task1.id, solicitante_id=membro_a.user.id, atribuido_id=membro_b.user.id, status="PENDENTE")
    # B convidou A para Task 2
    a2 = TaskAssignment(task_id=task2.id, solicitante_id=membro_b.user.id, atribuido_id=membro_a.user.id, status="ACEITA")
    db_session.add_all([a1, a2])
    db_session.commit()

    # Membro B consulta recebidas
    resp_b_rec = client.get("/atribuicoes/me?tipo=recebidas", headers=membro_b.headers)
    assert resp_b_rec.status_code == 200
    dados_b_rec = resp_b_rec.json()
    assert dados_b_rec["total"] >= 1
    assert any(item["id"] == str(a1.id) for item in dados_b_rec["atribuicoes"])

    # Membro B consulta enviadas
    resp_b_env = client.get("/atribuicoes/me?tipo=enviadas", headers=membro_b.headers)
    assert resp_b_env.status_code == 200
    dados_b_env = resp_b_env.json()
    assert any(item["id"] == str(a2.id) for item in dados_b_env["atribuicoes"])

    # Membro B consulta via alias /tasks/atribuicoes/me
    resp_alias = client.get("/tasks/atribuicoes/me?tipo=recebidas", headers=membro_b.headers)
    assert resp_alias.status_code == 200


# ── Testes de Revalidação de Autorização no Envio e no Aceite ──


def test_proprietario_sem_vinculo_bloqueado_ao_criar_convite(client, db_session):
    """Proprietário da task que perdeu o vínculo com o setor não pode criar convites."""
    membro_a = _criar_usuario_com_papel(db_session, "Membro A Desvinculado", f"A{uuid4().hex[:6]}")
    membro_b = _criar_usuario_com_papel(db_session, "Membro B Ativo", f"B{uuid4().hex[:6]}")

    task = Task(
        usuario_id=membro_a.user.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Task de Membro que Perdeu Vínculo",
        status="PENDENTE",
    )
    db_session.add(task)
    db_session.commit()

    # Remove vínculo do membro_a com o setor
    db_session.query(SectorUser).filter(
        SectorUser.usuario_id == membro_a.user.id,
        SectorUser.setor_id == TestID.SETOR_TESTE,
    ).delete()
    db_session.commit()

    # Tentativa de criar convite sem vínculo -> 403 Forbidden
    resp = client.post(
        f"/tasks/{task.id}/atribuir",
        headers=membro_a.headers,
        json={"atribuido_id": str(membro_b.user.id)},
    )
    assert resp.status_code == 403
    assert any(term in resp.json()["detail"].lower() for term in ("vinculado", "vínculo"))


def test_aceite_bloqueado_apos_remocao_do_destinatario_do_setor(client, db_session):
    """Destinatário que foi removido do setor após o envio do convite não pode aceitá-lo."""
    membro_a = _criar_usuario_com_papel(db_session, "Membro A Orig", f"A{uuid4().hex[:6]}")
    membro_b = _criar_usuario_com_papel(db_session, "Membro B Removido", f"B{uuid4().hex[:6]}")

    task = Task(
        usuario_id=membro_a.user.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Task para Convidado Removido",
        status="PENDENTE",
    )
    db_session.add(task)
    db_session.commit()

    assignment = TaskAssignment(
        task_id=task.id,
        solicitante_id=membro_a.user.id,
        atribuido_id=membro_b.user.id,
        status="PENDENTE",
    )
    db_session.add(assignment)
    db_session.commit()

    # Remove o destinatário do setor
    db_session.query(SectorUser).filter(
        SectorUser.usuario_id == membro_b.user.id,
        SectorUser.setor_id == TestID.SETOR_TESTE,
    ).delete()
    db_session.commit()

    resp = client.patch(
        f"/atribuicoes/{assignment.id}/aceitar",
        headers=membro_b.headers,
    )
    assert resp.status_code == 403
    assert any(term in resp.json()["detail"].lower() for term in ("vinculado", "vínculo"))

    db_session.refresh(assignment)
    assert assignment.status == "EXPIRADA"


def test_aceite_bloqueado_apos_promocao_a_admin(client, db_session):
    """Destinatário que foi promovido a admin após o envio do convite não pode aceitá-lo."""
    membro_a = _criar_usuario_com_papel(db_session, "Membro A Orig2", f"A{uuid4().hex[:6]}")
    membro_b = _criar_usuario_com_papel(db_session, "Membro B Promovido", f"B{uuid4().hex[:6]}")

    task = Task(
        usuario_id=membro_a.user.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Task para Promovido a Admin",
        status="PENDENTE",
    )
    db_session.add(task)
    db_session.commit()

    assignment = TaskAssignment(
        task_id=task.id,
        solicitante_id=membro_a.user.id,
        atribuido_id=membro_b.user.id,
        status="PENDENTE",
    )
    db_session.add(assignment)
    db_session.commit()

    # Promove o destinatário a admin global
    user_b = db_session.query(User).filter(User.id == membro_b.user.id).first()
    user_b.global_role = RoleID.ADMIN
    db_session.commit()

    resp = client.patch(
        f"/atribuicoes/{assignment.id}/aceitar",
        headers=membro_b.headers,
    )
    assert resp.status_code == 403
    assert "Administradores não podem receber atribuições" in resp.json()["detail"]

    db_session.refresh(assignment)
    assert assignment.status == "EXPIRADA"


def test_aceite_bloqueado_apos_remocao_da_task_original(client, db_session):
    """Convite para task que foi removida pelo líder antes do aceite é rejeitado."""
    membro_a = _criar_usuario_com_papel(db_session, "Membro A Orig3", f"A{uuid4().hex[:6]}")
    membro_b = _criar_usuario_com_papel(db_session, "Membro B Aceite", f"B{uuid4().hex[:6]}")

    task = Task(
        usuario_id=membro_a.user.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Task Removida pelo Líder",
        status="REMOVIDA_PELO_LIDER",
    )
    db_session.add(task)
    db_session.commit()

    assignment = TaskAssignment(
        task_id=task.id,
        solicitante_id=membro_a.user.id,
        atribuido_id=membro_b.user.id,
        status="PENDENTE",
    )
    db_session.add(assignment)
    db_session.commit()

    resp = client.patch(
        f"/atribuicoes/{assignment.id}/aceitar",
        headers=membro_b.headers,
    )
    assert resp.status_code == 400
    assert "não está mais disponível" in resp.json()["detail"]

    db_session.refresh(assignment)
    assert assignment.status == "EXPIRADA"


def test_aceite_na_terca_feira_nao_vincula_a_weekly_encerrada(client, db_session, monkeypatch):
    """Aceite fora da janela (ex: terça-feira) clona a task no banco mas NÃO a associa a rascunho de janela fechada."""
    membro_a = _criar_usuario_com_papel(db_session, "Membro A Terça", f"A{uuid4().hex[:6]}")
    membro_b = _criar_usuario_com_papel(db_session, "Membro B Terça", f"B{uuid4().hex[:6]}")

    task = Task(
        usuario_id=membro_a.user.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Task Aceita na Terça",
        status="PENDENTE",
    )
    db_session.add(task)
    db_session.commit()

    weekly_rascunho_b = Weekly(
        usuario_id=membro_b.user.id,
        setor_id=TestID.SETOR_TESTE,
        semana_referencia=date(2026, 10, 5),
        status="RASCUNHO",
    )
    db_session.add(weekly_rascunho_b)
    db_session.commit()

    assignment = TaskAssignment(
        task_id=task.id,
        solicitante_id=membro_a.user.id,
        atribuido_id=membro_b.user.id,
        status="PENDENTE",
    )
    db_session.add(assignment)
    db_session.commit()

    # Simula Terça-feira (janela encerrada)
    from zoneinfo import ZoneInfo
    terca_feira = datetime(2026, 10, 6, 10, 0, tzinfo=ZoneInfo("America/Fortaleza"))
    monkeypatch.setattr("app.weeklies.timezone_utils.get_now_fortaleza", lambda: terca_feira)
    monkeypatch.setattr("app.weeklies.service.get_now_fortaleza", lambda: terca_feira)

    resp = client.patch(
        f"/atribuicoes/{assignment.id}/aceitar",
        headers=membro_b.headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ACEITA"

    # Confere que a tarefa clonada foi criada para o membro B
    task_clonada = (
        db_session.query(Task)
        .filter(Task.usuario_id == membro_b.user.id, Task.origem_task_id == task.id)
        .first()
    )
    assert task_clonada is not None
    assert task_clonada.status == "PENDENTE"

    # Mas NÃO foi associada à weekly_rascunho_b (que pertence à janela encerrada)
    item_weekly = (
        db_session.query(WeeklyTask)
        .filter(
            WeeklyTask.weekly_id == weekly_rascunho_b.id,
            WeeklyTask.task_id == task_clonada.id,
        )
        .first()
    )
    assert item_weekly is None


def test_copias_nao_podem_originar_novos_convites(client, db_session):
    """Garante que tarefas clonadas (com origem_task_id) não podem ser atribuídas (delegação proibida)."""
    membro_a = _criar_usuario_com_papel(db_session, "Membro Orig", f"A{uuid4().hex[:6]}")
    membro_b = _criar_usuario_com_papel(db_session, "Membro Dest", f"B{uuid4().hex[:6]}")
    membro_c = _criar_usuario_com_papel(db_session, "Membro Terceiro", f"C{uuid4().hex[:6]}")
    lider = _criar_usuario_com_papel(db_session, "Lider Setor", f"L{uuid4().hex[:6]}", papel="lider")

    task_orig = Task(
        usuario_id=membro_a.user.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Task Raiz",
        status="PENDENTE",
    )
    db_session.add(task_orig)
    db_session.commit()

    # A convida B
    resp_convite = client.post(
        f"/tasks/{task_orig.id}/atribuir",
        headers=membro_a.headers,
        json={"atribuido_id": str(membro_b.user.id)},
    )
    assert resp_convite.status_code == 201
    assign_id = resp_convite.json()["id"]

    # B aceita convite -> cria cópia clonada para B
    resp_aceite = client.patch(
        f"/atribuicoes/{assign_id}/aceitar",
        headers=membro_b.headers,
    )
    assert resp_aceite.status_code == 200

    task_copia = (
        db_session.query(Task)
        .filter(Task.usuario_id == membro_b.user.id, Task.origem_task_id == task_orig.id)
        .first()
    )
    assert task_copia is not None
    assert task_copia.origem_task_id == task_orig.id

    # 1. B tenta convidar C usando a cópia clonada -> 400 BadRequestError
    resp_b_convida_c = client.post(
        f"/tasks/{task_copia.id}/atribuir",
        headers=membro_b.headers,
        json={"atribuido_id": str(membro_c.user.id)},
    )
    assert resp_b_convida_c.status_code == 400
    assert "clonadas" in resp_b_convida_c.json()["detail"].lower()

    # 2. Líder do setor tenta atribuir a cópia clonada para C -> também rejeitado (proibição absoluta)
    resp_lider_tenta = client.post(
        f"/tasks/{task_copia.id}/atribuir",
        headers=lider.headers,
        json={"atribuido_id": str(membro_c.user.id)},
    )
    assert resp_lider_tenta.status_code == 400
    assert "clonadas" in resp_lider_tenta.json()["detail"].lower()

    # 3. Mas Membro A (dono da task original) ainda pode convidar C usando a original
    resp_a_convida_c = client.post(
        f"/tasks/{task_orig.id}/atribuir",
        headers=membro_a.headers,
        json={"atribuido_id": str(membro_c.user.id)},
    )
    assert resp_a_convida_c.status_code == 201


def test_colaboracao_entre_setores_registra_copia_no_setor_do_convidado(client, db_session):
    """Membro A (Setor A) pode convidar Membro B (Setor B). A cópia da task é criada no Setor B."""
    from app.models.sector import Sector

    setor_marketing = Sector(nome=f"Setor Marketing {uuid4().hex[:6]}")
    db_session.add(setor_marketing)
    db_session.commit()

    membro_a = _criar_usuario_com_papel(db_session, "Membro Dev", f"A{uuid4().hex[:6]}")
    # membro_b pertence exclusivamente ao Setor Marketing
    membro_b = _criar_usuario_com_papel(
        db_session,
        "Membro Mkt",
        f"B{uuid4().hex[:6]}",
        setor_id=setor_marketing.id,
    )

    task_dev = Task(
        usuario_id=membro_a.user.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="API Cross-Sector",
        status="PENDENTE",
    )
    db_session.add(task_dev)
    db_session.commit()

    # 1. Membro A convida Membro B de outro setor -> Sucesso 201 (não bloqueia com 403)
    resp_convite = client.post(
        f"/tasks/{task_dev.id}/atribuir",
        headers=membro_a.headers,
        json={"atribuido_id": str(membro_b.user.id)},
    )
    assert resp_convite.status_code == 201
    assign_id = resp_convite.json()["id"]

    # 2. Membro B aceita o convite -> Sucesso 200
    resp_aceite = client.patch(
        f"/atribuicoes/{assign_id}/aceitar",
        headers=membro_b.headers,
    )
    assert resp_aceite.status_code == 200

    # 3. A cópia da tarefa é registrada no setor do próprio convidado (Setor Marketing)
    task_clonada = (
        db_session.query(Task)
        .filter(Task.usuario_id == membro_b.user.id, Task.origem_task_id == task_dev.id)
        .first()
    )
    assert task_clonada is not None
    assert task_clonada.setor_id == setor_marketing.id
    assert task_clonada.origem_task_id == task_dev.id

    # 4. Membro B continua não vinculado ao Setor Dev
    vinculo_dev = (
        db_session.query(SectorUser)
        .filter(SectorUser.usuario_id == membro_b.user.id, SectorUser.setor_id == TestID.SETOR_TESTE)
        .first()
    )
    assert vinculo_dev is None

    # 5. Membro B consegue visualizar e gerenciar a task no seu próprio setor
    resp_listar = client.get(
        f"/tasks/me?setor_id={setor_marketing.id}",
        headers=membro_b.headers,
    )
    assert resp_listar.status_code == 200
    ids_tasks = [t["id"] for t in resp_listar.json()["tasks"]]
    assert str(task_clonada.id) in ids_tasks


# ── Testes para Consulta de Colaboradores Elegíveis ───────────


def test_listar_colaboradores_elegiveis_sucesso(client, db_session):
    """Garante que a lista retorna membros ativos, exclui admins e o próprio solicitante."""
    solicitante = _criar_usuario_com_papel(db_session, "Solicitante", "SOL01")
    colega_ativo = _criar_usuario_com_papel(db_session, "Colega Ativo", "COL01")
    admin = _criar_usuario_com_papel(
        db_session, "Admin Global", "ADM01", global_role=RoleID.ADMIN
    )

    resp = client.get("/tasks/colaboradores-elegiveis", headers=solicitante.headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "colaboradores" in data
    assert data["total"] >= 1

    ids = [c["id"] for c in data["colaboradores"]]
    assert str(colega_ativo.user.id) in ids
    # Não deve incluir o próprio solicitante
    assert str(solicitante.user.id) not in ids
    # Não deve incluir administradores
    assert str(admin.user.id) not in ids

    # Verifica estrutura dos campos
    item = next(c for c in data["colaboradores"] if c["id"] == str(colega_ativo.user.id))
    assert item["nome_completo"] == "Colega Ativo"
    assert item["matricula"] == "COL01"
    assert isinstance(item["setores"], list)


def test_listar_colaboradores_elegiveis_busca(client, db_session):
    """Testa filtro por termo de busca no nome, email ou matrícula."""
    solicitante = _criar_usuario_com_papel(db_session, "Solicitante Busca", "SOL02")
    membro_alvo = _criar_usuario_com_papel(db_session, "Fulano da Silva", "SILVA99")
    membro_outro = _criar_usuario_com_papel(db_session, "Ciclano Souza", "SOUZA88")

    # Busca por parte do nome
    resp = client.get(
        "/tasks/colaboradores-elegiveis?busca=Silva",
        headers=solicitante.headers,
    )
    assert resp.status_code == 200
    ids = [c["id"] for c in resp.json()["colaboradores"]]
    assert str(membro_alvo.user.id) in ids
    assert str(membro_outro.user.id) not in ids

    # Busca por matrícula
    resp_mat = client.get(
        "/tasks/colaboradores-elegiveis?busca=SOUZA88",
        headers=solicitante.headers,
    )
    assert resp_mat.status_code == 200
    ids_mat = [c["id"] for c in resp_mat.json()["colaboradores"]]
    assert str(membro_outro.user.id) in ids_mat
    assert str(membro_alvo.user.id) not in ids_mat


def test_listar_colaboradores_elegiveis_com_task_id(client, db_session):
    """Garante que exclui dono da task e membros com atribuição pendente ou clone da task."""
    dono = _criar_usuario_com_papel(db_session, "Dono da Tarefa", "DONO01")
    convidado_pendente = _criar_usuario_com_papel(db_session, "Convidado Pendente", "PEND01")
    disponivel = _criar_usuario_com_papel(db_session, "Membro Disponivel", "DISP01")

    task = Task(
        usuario_id=dono.user.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Tarefa Teste Elegibilidade",
        status="PENDENTE",
        prazo_conclusao=date(2026, 12, 31),
    )
    db_session.add(task)
    db_session.commit()

    # Cria atribuição pendente para convidado_pendente
    assignment = TaskAssignment(
        task_id=task.id,
        solicitante_id=dono.user.id,
        atribuido_id=convidado_pendente.user.id,
        status="PENDENTE",
    )
    db_session.add(assignment)
    db_session.commit()

    # Consulta passando task_id
    resp = client.get(
        f"/tasks/colaboradores-elegiveis?task_id={task.id}",
        headers=dono.headers,
    )
    assert resp.status_code == 200
    ids = [c["id"] for c in resp.json()["colaboradores"]]
    assert str(disponivel.user.id) in ids
    # Exclui quem já tem convite pendente
    assert str(convidado_pendente.user.id) not in ids
    # Exclui o dono da tarefa
    assert str(dono.user.id) not in ids



