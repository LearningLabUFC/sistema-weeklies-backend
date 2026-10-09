"""
Testes para a Fase 4: Herança de Tarefas (Rollover de Tasks Pendentes).

Cenários cobertos:
1. Herança automática de tasks com status PENDENTE para a nova weekly com origem='HERDADA'.
2. Exclusão de tasks com status CONCLUIDA, EM_AUDITORIA ou REMOVIDA_PELO_LIDER do rollover.
3. Isolamento por setor: tarefas de um setor não vazam para a weekly de outro setor.
4. Ciclo completo multissemanal: tarefas concluídas e aprovadas na semana 1 não são herdadas na semana 2.
5. Adição manual de tasks não-pendentes (ex: CONCLUIDA, EM_AUDITORIA) é rejeitada com 400.
"""

from datetime import date, datetime

from app.core.constants import RoleID, StatusID, TestID
from app.core.security import criar_token_acesso
from app.models.sector import Sector
from app.models.sector_user import SectorUser
from app.models.task import Task
from app.models.user import User
from app.weeklies.timezone_utils import FUSO_LLAB


def _criar_usuario_com_setor(db_session, email, matricula, papel="membro", global_role=RoleID.USUARIO, setor_id=TestID.SETOR_TESTE):
    user = User(
        nome_completo=f"Usuário {matricula}",
        email=email,
        senha_hash="unused",
        matricula=str(matricula),
        data_nascimento=date(2000, 1, 1),
        data_ingresso=date(2026, 1, 1),
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
    return user, headers


def test_rollover_herda_tasks_pendentes_automaticamente(client, db_session):
    _membro, h_membro = _criar_usuario_com_setor(db_session, "rollover1@test.com", "881001")

    # 1. Cria 2 tasks avulsas no setor (ambas PENDENTE)
    res_t1 = client.post(
        "/tasks",
        headers=h_membro,
        json={"setor_id": str(TestID.SETOR_TESTE), "titulo": "Task Rollover 1", "descricao": "D1"},
    )
    assert res_t1.status_code == 201
    t1_id = res_t1.json()["id"]

    res_t2 = client.post(
        "/tasks",
        headers=h_membro,
        json={"setor_id": str(TestID.SETOR_TESTE), "titulo": "Task Rollover 2", "descricao": "D2"},
    )
    assert res_t2.status_code == 201
    t2_id = res_t2.json()["id"]

    # 2. Cria ou obtém a weekly da semana atual
    res_w = client.get(
        f"/weeklies/me/atual?setor_id={TestID.SETOR_TESTE}",
        headers=h_membro,
    )
    assert res_w.status_code == 200
    weekly = res_w.json()
    assert weekly["status"] == "RASCUNHO"
    assert len(weekly["tasks"]) == 2

    # Verifica que ambas vieram com origem='HERDADA' e concluida=False
    tasks_ids = [t["task_id"] for t in weekly["tasks"]]
    assert t1_id in tasks_ids
    assert t2_id in tasks_ids

    for t in weekly["tasks"]:
        assert t["origem"] == "HERDADA"
        assert t["concluida"] is False
        assert t["status_task"] == "PENDENTE"

    # 3. Adicionar uma nova tarefa inline na weekly deve vir com origem='NOVA'
    res_inline = client.post(
        f"/weeklies/{weekly['id']}/tasks",
        headers=h_membro,
        json={"titulo": "Task Criada Nesta Semana"},
    )
    assert res_inline.status_code == 201
    assert res_inline.json()["origem"] == "NOVA"
    assert res_inline.json()["posicao"] == 3


def test_rollover_nao_herda_concluidas_auditoria_ou_removidas(client, db_session):
    membro, h_membro = _criar_usuario_com_setor(db_session, "rollover2@test.com", "882001")

    # 1. Cria tarefa PENDENTE
    t_pendente = Task(
        usuario_id=membro.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Task Ativa",
        status="PENDENTE",
    )
    # 2. Cria tarefa CONCLUIDA
    t_concluida = Task(
        usuario_id=membro.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Task Finalizada",
        status="CONCLUIDA",
    )
    # 3. Cria tarefa EM_AUDITORIA
    t_auditoria = Task(
        usuario_id=membro.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Task Sob Auditoria",
        status="EM_AUDITORIA",
    )
    # 4. Cria tarefa REMOVIDA_PELO_LIDER
    t_removida = Task(
        usuario_id=membro.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Task Descartada",
        status="REMOVIDA_PELO_LIDER",
    )
    db_session.add_all([t_pendente, t_concluida, t_auditoria, t_removida])
    db_session.commit()

    # Cria weekly
    res_w = client.post(
        "/weeklies",
        headers=h_membro,
        json={"setor_id": str(TestID.SETOR_TESTE), "semana_referencia": "2026-10-05"},
    )
    assert res_w.status_code == 201
    weekly = res_w.json()

    # Apenas a task PENDENTE deve ter sido herdada
    assert len(weekly["tasks"]) == 1
    assert weekly["tasks"][0]["task_id"] == str(t_pendente.id)
    assert weekly["tasks"][0]["titulo"] == "Task Ativa"
    assert weekly["tasks"][0]["origem"] == "HERDADA"


def test_rollover_isolamento_por_setor(client, db_session):
    membro, h_membro = _criar_usuario_com_setor(db_session, "rollover3@test.com", "883001")

    # Cria um segundo setor
    setor_b = Sector(nome="Setor Secundário", descricao="Segundo setor")
    db_session.add(setor_b)
    db_session.flush()

    assoc_b = SectorUser(usuario_id=membro.id, setor_id=setor_b.id, papel="membro")
    db_session.add(assoc_b)

    # Cria task no Setor Teste e task no Setor B
    t_a = Task(usuario_id=membro.id, setor_id=TestID.SETOR_TESTE, titulo="Task Setor A", status="PENDENTE")
    t_b = Task(usuario_id=membro.id, setor_id=setor_b.id, titulo="Task Setor B", status="PENDENTE")
    db_session.add_all([t_a, t_b])
    db_session.commit()

    # Cria weekly para o Setor A
    res_wa = client.post(
        "/weeklies",
        headers=h_membro,
        json={"setor_id": str(TestID.SETOR_TESTE), "semana_referencia": "2026-10-05"},
    )
    assert res_wa.status_code == 201
    assert len(res_wa.json()["tasks"]) == 1
    assert res_wa.json()["tasks"][0]["task_id"] == str(t_a.id)

    # Cria weekly para o Setor B
    res_wb = client.post(
        "/weeklies",
        headers=h_membro,
        json={"setor_id": str(setor_b.id), "semana_referencia": "2026-10-05"},
    )
    assert res_wb.status_code == 201
    assert len(res_wb.json()["tasks"]) == 1
    assert res_wb.json()["tasks"][0]["task_id"] == str(t_b.id)


def test_rollover_fluxo_multissemanal_completo(client, db_session, monkeypatch):
    _membro, h_membro = _criar_usuario_com_setor(db_session, "rollover4@test.com", "884001")
    _lider, h_lider = _criar_usuario_com_setor(db_session, "lider4@test.com", "884002", papel="lider")

    # ── SEMANA 1 (05/10/2026) ─────────────────────────────────
    now_sem1 = datetime(2026, 10, 2, 12, tzinfo=FUSO_LLAB)
    monkeypatch.setattr("app.weeklies.timezone_utils.get_now_fortaleza", lambda: now_sem1)
    monkeypatch.setattr("app.weeklies.service.get_now_fortaleza", lambda: now_sem1)

    # Cria 2 tasks na Semana 1
    res_t1 = client.post("/tasks", headers=h_membro, json={"setor_id": str(TestID.SETOR_TESTE), "titulo": "Task A"})
    t1_id = res_t1.json()["id"]
    res_t2 = client.post("/tasks", headers=h_membro, json={"setor_id": str(TestID.SETOR_TESTE), "titulo": "Task B"})
    t2_id = res_t2.json()["id"]

    # Abre weekly semana 1 (ambas herdadas)
    res_w1 = client.get(f"/weeklies/me/atual?setor_id={TestID.SETOR_TESTE}", headers=h_membro)
    w1_id = res_w1.json()["id"]
    assert len(res_w1.json()["tasks"]) == 2

    wt1_item_id = next(t["id"] for t in res_w1.json()["tasks"] if t["task_id"] == t1_id)

    # Marca Task A como concluída na weekly 1
    client.patch(f"/weeklies/{w1_id}/tasks/{wt1_item_id}", headers=h_membro, json={"concluida": True})

    # Envia weekly 1
    client.patch(f"/weeklies/{w1_id}/enviar", headers=h_membro)

    # Líder aprova weekly 1 -> Task A passa para CONCLUIDA! Task B continua PENDENTE!
    client.patch(f"/weeklies/{w1_id}/avaliar", headers=h_lider, json={"status": "APROVADA"})

    # ── SEMANA 2 (12/10/2026) ─────────────────────────────────
    now_sem2 = datetime(2026, 10, 9, 12, tzinfo=FUSO_LLAB)  # Sexta seguinte
    monkeypatch.setattr("app.weeklies.timezone_utils.get_now_fortaleza", lambda: now_sem2)
    monkeypatch.setattr("app.weeklies.service.get_now_fortaleza", lambda: now_sem2)

    # Abre weekly semana 2
    res_w2 = client.get(f"/weeklies/me/atual?setor_id={TestID.SETOR_TESTE}", headers=h_membro)
    assert res_w2.status_code == 200
    w2 = res_w2.json()
    assert w2["semana_referencia"] == "2026-10-12"

    # Task B DEVE ter sido herdada, mas Task A (concluída) NÃO DEVE!
    assert len(w2["tasks"]) == 1
    assert w2["tasks"][0]["task_id"] == t2_id
    assert w2["tasks"][0]["origem"] == "HERDADA"
    assert w2["tasks"][0]["concluida"] is False


def test_adicao_manual_de_task_nao_pendente_bloqueada(client, db_session):
    membro, h_membro = _criar_usuario_com_setor(db_session, "rollover5@test.com", "885001")

    # Cria weekly
    res_w = client.post(
        "/weeklies",
        headers=h_membro,
        json={"setor_id": str(TestID.SETOR_TESTE), "semana_referencia": "2026-10-05"},
    )
    weekly_id = res_w.json()["id"]

    # Cria tarefa já CONCLUIDA no banco
    t_concl = Task(usuario_id=membro.id, setor_id=TestID.SETOR_TESTE, titulo="Já Feita", status="CONCLUIDA")
    # Cria tarefa EM_AUDITORIA no banco
    t_audit = Task(usuario_id=membro.id, setor_id=TestID.SETOR_TESTE, titulo="Em Auditoria", status="EM_AUDITORIA")
    db_session.add_all([t_concl, t_audit])
    db_session.commit()

    # Tenta adicionar a tarefa CONCLUIDA manualmente à weekly -> 400
    res1 = client.post(
        f"/weeklies/{weekly_id}/tasks",
        headers=h_membro,
        json={"task_id": str(t_concl.id)},
    )
    assert res1.status_code == 400
    assert "Apenas tasks com status 'PENDENTE' podem ser adicionadas" in res1.text

    # Tenta adicionar a tarefa EM_AUDITORIA manualmente à weekly -> 400
    res2 = client.post(
        f"/weeklies/{weekly_id}/tasks",
        headers=h_membro,
        json={"task_id": str(t_audit.id)},
    )
    assert res2.status_code == 400
    assert "Apenas tasks com status 'PENDENTE' podem ser adicionadas" in res2.text
