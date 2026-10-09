"""
Testes de regressão cobrindo as 4 pendências da revisão:
1. Conclusão da tarefa consolidada no momento da aprovação da weekly.
2. Avaliação aceita apenas status válidos (APROVADA / REJEITADA) e rejeição exige observação com texto.
3. Impedir que uma weekly enviada fique vazia ao remover sua última tarefa.
4. Criação inline de tarefa atômica (rollback de Task em caso de falha no vínculo).
"""

from datetime import date, datetime
from unittest.mock import patch

import pytest

from app.core.constants import RoleID, StatusID, TestID
from app.core.security import criar_token_acesso
from app.models.sector_user import SectorUser
from app.models.task import Task
from app.models.user import User
from app.weeklies.timezone_utils import FUSO_LLAB


def _criar_usuario_com_setor(db_session, email, matricula, papel="membro", global_role=RoleID.USUARIO):
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

    assoc = SectorUser(usuario_id=user.id, setor_id=TestID.SETOR_TESTE, papel=papel)
    db_session.add(assoc)
    db_session.commit()

    token = criar_token_acesso({"sub": str(user.id)})
    headers = {"Authorization": f"Bearer {token}"}
    return user, headers


# ── Pendência 1: Consolidação da Conclusão de Tarefas ─────────


def test_conclusao_de_tarefa_consolidada_apenas_na_aprovacao(client, db_session):
    _membro, h_membro = _criar_usuario_com_setor(db_session, "membro1@test.com", "771001")
    _lider, h_lider = _criar_usuario_com_setor(db_session, "lider1@test.com", "771002", papel="lider")

    # 1. Cria weekly vazia
    res_w = client.post(
        "/weeklies",
        headers=h_membro,
        json={"setor_id": str(TestID.SETOR_TESTE), "semana_referencia": "2026-10-05"},
    )
    assert res_w.status_code == 201
    weekly_id = res_w.json()["id"]

    # 2. Cria task PENDENTE e adiciona à weekly
    res_task = client.post(
        "/tasks",
        headers=h_membro,
        json={"setor_id": str(TestID.SETOR_TESTE), "titulo": "Tarefa para aprovar"},
    )
    assert res_task.status_code == 201
    task_id = res_task.json()["id"]

    res_add = client.post(
        f"/weeklies/{weekly_id}/tasks",
        headers=h_membro,
        json={"task_id": task_id},
    )
    assert res_add.status_code == 201
    wt_id = res_add.json()["id"]

    # 3. Marca concluida=True na weekly
    res_up = client.patch(
        f"/weeklies/{weekly_id}/tasks/{wt_id}",
        headers=h_membro,
        json={"concluida": True},
    )
    assert res_up.status_code == 200

    # 4. Verifica que no rascunho a Task global continua PENDENTE
    t_db = db_session.query(Task).filter(Task.id == task_id).first()
    assert t_db.status == "PENDENTE"

    # 5. Envia a weekly
    res_send = client.patch(f"/weeklies/{weekly_id}/enviar", headers=h_membro)
    assert res_send.status_code == 200

    # Task global ainda deve ser PENDENTE enquanto apenas ENVIADA
    db_session.expire_all()
    t_db = db_session.query(Task).filter(Task.id == task_id).first()
    assert t_db.status == "PENDENTE"

    # 6. Líder rejeita com feedback
    res_rej = client.patch(
        f"/weeklies/{weekly_id}/avaliar",
        headers=h_lider,
        json={"status": "REJEITADA", "observacao_lider": "Ajuste os commits"},
    )
    assert res_rej.status_code == 200
    db_session.expire_all()
    t_db = db_session.query(Task).filter(Task.id == task_id).first()
    assert t_db.status == "PENDENTE"

    # 7. Membro reenvia e líder aprova
    client.patch(f"/weeklies/{weekly_id}/enviar", headers=h_membro)
    res_aprov = client.patch(
        f"/weeklies/{weekly_id}/avaliar",
        headers=h_lider,
        json={"status": "APROVADA", "observacao_lider": "Excelente!"},
    )
    assert res_aprov.status_code == 200

    # 8. Agora a Task global DEVE estar CONCLUIDA
    db_session.expire_all()
    t_db = db_session.query(Task).filter(Task.id == task_id).first()
    assert t_db.status == "CONCLUIDA"

    # 9. Listagem /tasks/me?status=PENDENTE não deve mais retornar esta task
    res_pendentes = client.get("/tasks/me?status=PENDENTE", headers=h_membro)
    assert res_pendentes.status_code == 200
    assert not any(t["id"] == task_id for t in res_pendentes.json()["tasks"])

    # 10. Listagem /tasks/me?status=CONCLUIDA deve retornar esta task
    res_concluidas = client.get("/tasks/me?status=CONCLUIDA", headers=h_membro)
    assert res_concluidas.status_code == 200
    assert any(t["id"] == task_id for t in res_concluidas.json()["tasks"])


# ── Pendência 2: Restrição de Status de Avaliação e Observação ─


def test_avaliacao_recusa_status_invalido_ou_arbitrario(client, db_session):
    _membro, h_membro = _criar_usuario_com_setor(db_session, "membro2@test.com", "772001")
    _lider, h_lider = _criar_usuario_com_setor(db_session, "lider2@test.com", "772002", papel="lider")

    res_w = client.post(
        "/weeklies",
        headers=h_membro,
        json={"setor_id": str(TestID.SETOR_TESTE), "semana_referencia": "2026-10-05"},
    )
    weekly_id = res_w.json()["id"]
    client.post(
        f"/weeklies/{weekly_id}/tasks",
        headers=h_membro,
        json={"titulo": "Tarefa inline"},
    )
    client.patch(f"/weeklies/{weekly_id}/enviar", headers=h_membro)

    # Status arbitrário (ex: BANANA) é recusado (422)
    res_banana = client.patch(
        f"/weeklies/{weekly_id}/avaliar",
        headers=h_lider,
        json={"status": "BANANA"},
    )
    assert res_banana.status_code == 422

    # Transição para RASCUNHO ou ENVIADA pela rota de avaliação é recusada (422)
    res_rascunho = client.patch(
        f"/weeklies/{weekly_id}/avaliar",
        headers=h_lider,
        json={"status": "RASCUNHO"},
    )
    assert res_rascunho.status_code == 422


def test_avaliacao_rejeicao_exige_observacao_nao_vazia(client, db_session):
    _membro, h_membro = _criar_usuario_com_setor(db_session, "membro3@test.com", "773001")
    _lider, h_lider = _criar_usuario_com_setor(db_session, "lider3@test.com", "773002", papel="lider")

    res_w = client.post(
        "/weeklies",
        headers=h_membro,
        json={"setor_id": str(TestID.SETOR_TESTE), "semana_referencia": "2026-10-05"},
    )
    weekly_id = res_w.json()["id"]
    client.post(f"/weeklies/{weekly_id}/tasks", headers=h_membro, json={"titulo": "T1"})
    client.patch(f"/weeklies/{weekly_id}/enviar", headers=h_membro)

    # Rejeição sem observação
    res1 = client.patch(
        f"/weeklies/{weekly_id}/avaliar",
        headers=h_lider,
        json={"status": "REJEITADA"},
    )
    assert res1.status_code == 400

    # Rejeição apenas com espaços em branco
    res2 = client.patch(
        f"/weeklies/{weekly_id}/avaliar",
        headers=h_lider,
        json={"status": "REJEITADA", "observacao_lider": "   \n  \t  "},
    )
    assert res2.status_code == 400

    # Rejeição com feedback válido funciona e remove espaços das bordas
    res3 = client.patch(
        f"/weeklies/{weekly_id}/avaliar",
        headers=h_lider,
        json={"status": "REJEITADA", "observacao_lider": "  Faltou relatório de testes  "},
    )
    assert res3.status_code == 200
    assert res3.json()["observacao_lider"] == "Faltou relatório de testes"


# ── Pendência 3: Impedir que Weekly Enviada Fique Vazia ────────


def test_bloqueia_remover_ultima_tarefa_de_weekly_enviada(client, db_session):
    _membro, h_membro = _criar_usuario_com_setor(db_session, "membro4@test.com", "774001")

    res_w = client.post(
        "/weeklies",
        headers=h_membro,
        json={"setor_id": str(TestID.SETOR_TESTE), "semana_referencia": "2026-10-05"},
    )
    weekly_id = res_w.json()["id"]

    res_t1 = client.post(
        f"/weeklies/{weekly_id}/tasks",
        headers=h_membro,
        json={"titulo": "Tarefa Única"},
    )
    t1_id = res_t1.json()["id"]

    # Envia a weekly com 1 tarefa
    client.patch(f"/weeklies/{weekly_id}/enviar", headers=h_membro)

    # 1. Tentar remover tarefa de weekly enviada -> 400 (bloqueada contra alterações)
    res_del_enviada = client.delete(
        f"/weeklies/{weekly_id}/tasks/{t1_id}",
        headers=h_membro,
    )
    assert res_del_enviada.status_code == 400
    assert "Não é possível alterar uma weekly com status 'ENVIADA'" in res_del_enviada.text

    # 2. Tentar adicionar tarefa em weekly enviada -> 400
    res_add_enviada = client.post(
        f"/weeklies/{weekly_id}/tasks",
        headers=h_membro,
        json={"titulo": "Segunda Tarefa"},
    )
    assert res_add_enviada.status_code == 400
    assert "Não é possível alterar uma weekly com status 'ENVIADA'" in res_add_enviada.text

    # 3. Reabre a weekly para rascunho
    res_reabrir = client.patch(
        f"/weeklies/{weekly_id}/reabrir",
        headers=h_membro,
    )
    assert res_reabrir.status_code == 200
    assert res_reabrir.json()["status"] == "RASCUNHO"

    # 4. Agora em rascunho, a adição de uma segunda tarefa funciona
    res_t2 = client.post(
        f"/weeklies/{weekly_id}/tasks",
        headers=h_membro,
        json={"titulo": "Segunda Tarefa"},
    )
    assert res_t2.status_code == 201

    # 5. Remoção de uma das tarefas em rascunho funciona
    res_del_t1 = client.delete(
        f"/weeklies/{weekly_id}/tasks/{t1_id}",
        headers=h_membro,
    )
    assert res_del_t1.status_code == 200


def test_permite_remover_todas_as_tarefas_de_rascunho(client, db_session):
    _membro, h_membro = _criar_usuario_com_setor(db_session, "membro5@test.com", "775001")

    res_w = client.post(
        "/weeklies",
        headers=h_membro,
        json={"setor_id": str(TestID.SETOR_TESTE), "semana_referencia": "2026-10-05"},
    )
    weekly_id = res_w.json()["id"]

    res_t1 = client.post(
        f"/weeklies/{weekly_id}/tasks",
        headers=h_membro,
        json={"titulo": "Tarefa Rascunho"},
    )
    t1_id = res_t1.json()["id"]

    # Em RASCUNHO, remover a última tarefa é permitido
    res_del = client.delete(
        f"/weeklies/{weekly_id}/tasks/{t1_id}",
        headers=h_membro,
    )
    assert res_del.status_code == 200
    w_detail = client.get(f"/weeklies/{weekly_id}", headers=h_membro).json()
    assert len(w_detail["tasks"]) == 0


# ── Pendência 4: Atomicidade na Criação Inline de Tarefa ───────


def test_criacao_inline_com_falha_faz_rollback_sem_deixar_task_orfa(client, db_session):
    _membro, h_membro = _criar_usuario_com_setor(db_session, "membro6@test.com", "776001")

    res_w = client.post(
        "/weeklies",
        headers=h_membro,
        json={"setor_id": str(TestID.SETOR_TESTE), "semana_referencia": "2026-10-05"},
    )
    weekly_id = res_w.json()["id"]

    total_tasks_antes = db_session.query(Task).count()

    # Simula falha ao persistir a WeeklyTask após o flush da Task
    with patch("app.weeklies.service.add_task_to_weekly", side_effect=RuntimeError("Erro simulado no vínculo")), pytest.raises(RuntimeError):
        client.post(
            f"/weeklies/{weekly_id}/tasks",
            headers=h_membro,
            json={"titulo": "Task Atômica Falha"},
        )

    # Nenhuma Task deve ter sido commitada!
    db_session.rollback()
    total_tasks_depois = db_session.query(Task).count()
    assert total_tasks_depois == total_tasks_antes


# ── Pendência 5: Proteção Contra Aprovação de Weekly Rejeitada Vazia ────


def test_rejeitada_nao_pode_ter_ultima_tarefa_removida_nem_ser_aprovada_vazia(client, db_session):
    """
    Item 9:
    1. Membro envia weekly com 1 tarefa -> líder rejeita.
    2. Membro tenta remover a última tarefa da weekly rejeitada -> 400 (bloqueado).
    3. Se adicionar uma segunda tarefa, remover uma das tarefas funciona (resta 1).
    4. Tentar remover a tarefa restante -> 400 (bloqueado).
    5. Weekly com tarefas rejeitada -> aprovação pelo líder -> 200 (APROVADA).
    """
    _membro, h_membro = _criar_usuario_com_setor(db_session, "membro9_rej@test.com", "779001")
    _lider, h_lider = _criar_usuario_com_setor(db_session, "lider9_rej@test.com", "779002", papel="lider")

    # 1. Cria weekly e adiciona 1 tarefa
    res_w = client.post(
        "/weeklies",
        headers=h_membro,
        json={"setor_id": str(TestID.SETOR_TESTE), "semana_referencia": "2026-10-05"},
    )
    weekly_id = res_w.json()["id"]

    res_t1 = client.post(
        f"/weeklies/{weekly_id}/tasks",
        headers=h_membro,
        json={"titulo": "Tarefa Única"},
    )
    t1_id = res_t1.json()["id"]

    # 2. Envia a weekly
    res_envio = client.patch(f"/weeklies/{weekly_id}/enviar", headers=h_membro)
    assert res_envio.status_code == 200

    # 3. Líder rejeita a weekly
    res_rej = client.patch(
        f"/weeklies/{weekly_id}/avaliar",
        headers=h_lider,
        json={"status": "REJEITADA", "observacao_lider": "Ajuste o conteúdo"},
    )
    assert res_rej.status_code == 200
    assert res_rej.json()["status"] == "REJEITADA"

    # 4. Membro tenta remover a última tarefa da weekly rejeitada -> 400
    res_del_last = client.delete(f"/weeklies/{weekly_id}/tasks/{t1_id}", headers=h_membro)
    assert res_del_last.status_code == 400
    assert "Não é possível remover a última tarefa de uma weekly rejeitada" in res_del_last.text

    # 5. Membro adiciona uma segunda tarefa
    res_t2 = client.post(
        f"/weeklies/{weekly_id}/tasks",
        headers=h_membro,
        json={"titulo": "Segunda Tarefa"},
    )
    assert res_t2.status_code == 201
    t2_id = res_t2.json()["id"]

    # 6. Agora tendo 2 tarefas, remoção de t1 é permitida (resta t2)
    res_del_t1 = client.delete(f"/weeklies/{weekly_id}/tasks/{t1_id}", headers=h_membro)
    assert res_del_t1.status_code == 200

    # 7. Tentar remover t2 (agora a última restante) -> 400
    res_del_t2 = client.delete(f"/weeklies/{weekly_id}/tasks/{t2_id}", headers=h_membro)
    assert res_del_t2.status_code == 400
    assert "Não é possível remover a última tarefa de uma weekly rejeitada" in res_del_t2.text

    # 8. Aprovação direta da weekly rejeitada que contém tarefas -> 200
    res_aprov = client.patch(
        f"/weeklies/{weekly_id}/avaliar",
        headers=h_lider,
        json={"status": "APROVADA"},
    )
    assert res_aprov.status_code == 200
    assert res_aprov.json()["status"] == "APROVADA"


def test_bloqueia_aprovacao_de_weekly_rejeitada_ou_enviada_vazia(client, db_session):
    """
    Garante que mesmo que por manipulação de dados ou concorrência uma weekly
    rejeitada ou enviada fique sem tarefas, a aprovação falha no banco sob o lock transacional.
    """
    _membro, h_membro = _criar_usuario_com_setor(db_session, "membro9_empty@test.com", "779011")
    _lider, h_lider = _criar_usuario_com_setor(db_session, "lider9_empty@test.com", "779012", papel="lider")

    res_w = client.post(
        "/weeklies",
        headers=h_membro,
        json={"setor_id": str(TestID.SETOR_TESTE), "semana_referencia": "2026-10-05"},
    )
    weekly_id = res_w.json()["id"]

    # Adiciona task, envia e rejeita
    res_t = client.post(f"/weeklies/{weekly_id}/tasks", headers=h_membro, json={"titulo": "Task Teste"})
    t_id = res_t.json()["id"]
    client.patch(f"/weeklies/{weekly_id}/enviar", headers=h_membro)
    client.patch(
        f"/weeklies/{weekly_id}/avaliar",
        headers=h_lider,
        json={"status": "REJEITADA", "observacao_lider": "Ajustar"},
    )

    # Força remoção direta no banco para simular weekly rejeitada sem tarefas
    from app.models.weekly_task import WeeklyTask
    db_session.query(WeeklyTask).filter(WeeklyTask.id == t_id).delete()
    db_session.commit()

    # Tentativa de aprovar a weekly vazia -> 400
    res_aprov = client.patch(
        f"/weeklies/{weekly_id}/avaliar",
        headers=h_lider,
        json={"status": "APROVADA"},
    )
    assert res_aprov.status_code == 400
    assert "Não é possível aprovar uma weekly que não contém nenhuma tarefa" in res_aprov.text


def test_weekly_rejeitada_pode_ser_ajustada_e_reenviada_fora_da_janela(client, db_session, monkeypatch):
    """
    Garante que quando uma weekly for REJEITADA pelo líder/admin, o membro consegue:
    1. Editar o título/descrição da tarefa mesmo fora da janela (ex: Terça-feira).
    2. Adicionar novas tarefas inline à weekly rejeitada fora da janela.
    3. Atualizar conclusões/impedimentos na weekly rejeitada fora da janela.
    4. Reenviar a weekly (transitando para ENVIADA) fora da janela.
    5. O líder consegue então aprovar a weekly reenviada.
    6. Enquanto isso, weeklies em RASCUNHO continuam estritamente bloqueadas fora da janela.
    """
    _membro, h_membro = _criar_usuario_com_setor(db_session, "membro_rej_out@test.com", "779901")
    _lider, h_lider = _criar_usuario_com_setor(db_session, "lider_rej_out@test.com", "779902", papel="lider")

    # 1. Dentro da janela (sexta-feira): cria weekly e tarefa
    res_w = client.post(
        "/weeklies",
        headers=h_membro,
        json={"setor_id": str(TestID.SETOR_TESTE), "semana_referencia": "2026-10-05"},
    )
    weekly_id = res_w.json()["id"]

    res_t1 = client.post(
        f"/weeklies/{weekly_id}/tasks",
        headers=h_membro,
        json={"titulo": "Título Original Vago"},
    )
    t1_json = res_t1.json()
    wt1_id = t1_json["id"]
    task1_id = t1_json["task_id"]

    # Envia a weekly dentro da janela
    res_env = client.patch(f"/weeklies/{weekly_id}/enviar", headers=h_membro)
    assert res_env.status_code == 200

    # 2. Líder rejeita a weekly (na terça-feira, fora da janela)
    terca_feira = datetime(2026, 10, 6, 10, 0, tzinfo=FUSO_LLAB)  # Terça-feira (weekday=1, janela fechada)
    monkeypatch.setattr("app.weeklies.timezone_utils.get_now_fortaleza", lambda: terca_feira)
    monkeypatch.setattr("app.weeklies.service.get_now_fortaleza", lambda: terca_feira)

    res_rej = client.patch(
        f"/weeklies/{weekly_id}/avaliar",
        headers=h_lider,
        json={"status": "REJEITADA", "observacao_lider": "Melhore o título e adicione a tarefa secundária."},
    )
    assert res_rej.status_code == 200
    assert res_rej.json()["status"] == "REJEITADA"

    # 3. Na terça-feira (fora da janela), membro ajusta o título da Task
    res_up_task = client.patch(
        f"/tasks/{task1_id}",
        headers=h_membro,
        json={"titulo": "Título Corrigido e Específico"},
    )
    assert res_up_task.status_code == 200
    assert res_up_task.json()["titulo"] == "Título Corrigido e Específico"

    # 4. Membro adiciona segunda tarefa inline à weekly rejeitada fora da janela
    res_add_t2 = client.post(
        f"/weeklies/{weekly_id}/tasks",
        headers=h_membro,
        json={"titulo": "Tarefa Secundária Solicitada"},
    )
    assert res_add_t2.status_code == 201

    # 5. Membro atualiza impedimento da tarefa na weekly rejeitada fora da janela
    res_up_wt = client.patch(
        f"/weeklies/{weekly_id}/tasks/{wt1_id}",
        headers=h_membro,
        json={"impedimento": "Aguardando homologação"},
    )
    assert res_up_wt.status_code == 200
    assert res_up_wt.json()["impedimento"] == "Aguardando homologação"

    # 6. Membro reenvia a weekly rejeitada fora da janela
    res_reenvio = client.patch(f"/weeklies/{weekly_id}/enviar", headers=h_membro)
    assert res_reenvio.status_code == 200
    assert res_reenvio.json()["status"] == "ENVIADA"
    assert res_reenvio.json()["observacao_lider"] is None

    # 7. Líder aprova a weekly reavaliada
    res_aprov = client.patch(
        f"/weeklies/{weekly_id}/avaliar",
        headers=h_lider,
        json={"status": "APROVADA"},
    )
    assert res_aprov.status_code == 200
    assert res_aprov.json()["status"] == "APROVADA"

    # 8. Garante que para uma weekly em RASCUNHO, edição fora da janela CONTINUA bloqueada
    _membro_rasc, h_membro_rasc = _criar_usuario_com_setor(db_session, "membro_rasc@test.com", "779903")
    sexta_feira = datetime(2026, 10, 2, 12, 0, tzinfo=FUSO_LLAB)
    monkeypatch.setattr("app.weeklies.timezone_utils.get_now_fortaleza", lambda: sexta_feira)
    monkeypatch.setattr("app.weeklies.service.get_now_fortaleza", lambda: sexta_feira)

    res_w_rasc = client.post(
        "/weeklies",
        headers=h_membro_rasc,
        json={"setor_id": str(TestID.SETOR_TESTE), "semana_referencia": "2026-10-05"},
    )
    assert res_w_rasc.status_code == 201
    w_rasc_id = res_w_rasc.json()["id"]

    # Agora avança para terça (fora da janela) e tenta adicionar tarefa no rascunho
    monkeypatch.setattr("app.weeklies.timezone_utils.get_now_fortaleza", lambda: terca_feira)
    monkeypatch.setattr("app.weeklies.service.get_now_fortaleza", lambda: terca_feira)

    res_block = client.post(
        f"/weeklies/{w_rasc_id}/tasks",
        headers=h_membro_rasc,
        json={"titulo": "Não Deve Passar"},
    )
    assert res_block.status_code == 400
    assert "Fora da janela de submissão" in res_block.text


