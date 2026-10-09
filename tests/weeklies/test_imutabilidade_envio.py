"""Testes para validação de imutabilidade de weeklies enviadas e fluxo de reabertura (Fase 3 / Resolução P1).

Cenários cobertos:
1. Weekly enviada bloqueia alteração de conclusão de tarefa (400).
2. Weekly enviada bloqueia edição de título/descrição de task compartilhada (400).
3. Weekly enviada bloqueia adição e remoção de tarefas (400).
4. Reabrir weekly enviada transita para RASCUNHO e permite edições e novo envio (200).
5. Tentar reabrir weekly já APROVADA é bloqueado (400).
6. Terceiro tentando reabrir weekly de outro usuário é bloqueado (403).
"""

from datetime import date, datetime
from unittest.mock import patch
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.core.constants import RoleID, StatusID, TestID
from app.core.security import criar_token_acesso
from app.models.sector_user import SectorUser
from app.models.task import Task
from app.models.user import User
from app.models.weekly import Weekly
from app.models.weekly_task import WeeklyTask

FUSO_LLAB = ZoneInfo("America/Fortaleza")


def _criar_membro_e_weekly(client, db_session, email_prefix="membro_im"):
    uid = uuid4().hex[:6]
    user = User(
        nome_completo=f"Membro {uid.upper()}",
        email=f"{email_prefix}_{uid}@test.com",
        senha_hash="hash",
        matricula=f"M{uid[:5]}",
        data_nascimento=date(2000, 1, 1),
        data_ingresso=date(2026, 1, 1),
        curso_id=TestID.CURSO_TESTE,
        status_id=StatusID.ATIVO,
        global_role=RoleID.USUARIO,
    )
    db_session.add(user)
    db_session.flush()

    assoc = SectorUser(usuario_id=user.id, setor_id=TestID.SETOR_TESTE, papel="membro")
    db_session.add(assoc)
    db_session.commit()

    token = criar_token_acesso({"sub": str(user.id)})
    headers = {"Authorization": f"Bearer {token}"}

    # Cria task e weekly
    task = Task(
        usuario_id=user.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Tarefa Inicial",
        descricao="Descrição original",
        status="PENDENTE",
        prazo_conclusao=date(2026, 10, 15),
    )
    db_session.add(task)
    db_session.flush()

    weekly = Weekly(
        usuario_id=user.id,
        setor_id=TestID.SETOR_TESTE,
        semana_referencia=date(2026, 10, 5),
        status="RASCUNHO",
    )
    db_session.add(weekly)
    db_session.flush()

    wt = WeeklyTask(
        weekly_id=weekly.id,
        task_id=task.id,
        concluida=False,
        posicao=0,
    )
    db_session.add(wt)
    db_session.commit()
    db_session.refresh(weekly)

    return user, headers, weekly, task, wt


@patch("app.weeklies.timezone_utils.get_now_fortaleza")
def test_weekly_enviada_bloqueia_edicoes_e_permite_reabertura(mock_now, client, db_session):
    mock_now.return_value = datetime(2026, 10, 2, 14, 0, tzinfo=FUSO_LLAB)

    _user, headers, weekly, task, wt = _criar_membro_e_weekly(client, db_session, "env_lock")

    # 1. Envia a weekly
    res_env = client.patch(f"/weeklies/{weekly.id}/enviar", headers=headers)
    assert res_env.status_code == 200
    assert res_env.json()["status"] == "ENVIADA"

    # 2. Tentar alterar conclusão da tarefa na weekly enviada -> 400
    res_up_task = client.patch(
        f"/weeklies/{weekly.id}/tasks/{wt.id}",
        headers=headers,
        json={"concluida": True},
    )
    assert res_up_task.status_code == 400
    assert "Não é possível alterar uma weekly com status 'ENVIADA'" in res_up_task.json()["detail"]

    # 3. Tentar editar o título da task compartilhada presente na weekly enviada -> 400
    res_edit_task = client.patch(
        f"/tasks/{task.id}",
        headers=headers,
        json={"titulo": "Novo Título Proibido"},
    )
    assert res_edit_task.status_code == 400
    assert "Não é possível editar uma task presente em uma weekly com status 'ENVIADA'" in res_edit_task.json()["detail"]

    # 4. Tentar adicionar nova tarefa na weekly enviada -> 400
    res_add_task = client.post(
        f"/weeklies/{weekly.id}/tasks",
        headers=headers,
        json={"titulo": "Nova Tarefa Proibida"},
    )
    assert res_add_task.status_code == 400
    assert "Não é possível alterar uma weekly com status 'ENVIADA'" in res_add_task.json()["detail"]

    # 5. Tentar remover tarefa da weekly enviada -> 400
    res_del_task = client.delete(
        f"/weeklies/{weekly.id}/tasks/{wt.id}",
        headers=headers,
    )
    assert res_del_task.status_code == 400
    assert "Não é possível alterar uma weekly com status 'ENVIADA'" in res_del_task.json()["detail"]

    # 6. Reabrir a weekly para RASCUNHO -> 200
    res_reabrir = client.patch(
        f"/weeklies/{weekly.id}/reabrir",
        headers=headers,
    )
    assert res_reabrir.status_code == 200
    assert res_reabrir.json()["status"] == "RASCUNHO"

    # 7. Agora em RASCUNHO, a alteração de conclusão é permitida
    res_up_ok = client.patch(
        f"/weeklies/{weekly.id}/tasks/{wt.id}",
        headers=headers,
        json={"concluida": True},
    )
    assert res_up_ok.status_code == 200
    assert res_up_ok.json()["concluida"] is True

    # 8. Agora em RASCUNHO, a edição do título da task compartilhada é permitida
    res_edit_ok = client.patch(
        f"/tasks/{task.id}",
        headers=headers,
        json={"titulo": "Novo Título Permitido"},
    )
    assert res_edit_ok.status_code == 200
    assert res_edit_ok.json()["titulo"] == "Novo Título Permitido"

    # 9. Reenvia a weekly -> 200 ENVIADA
    res_reenviar = client.patch(f"/weeklies/{weekly.id}/enviar", headers=headers)
    assert res_reenviar.status_code == 200
    assert res_reenviar.json()["status"] == "ENVIADA"


@patch("app.weeklies.timezone_utils.get_now_fortaleza")
def test_reabrir_weekly_aprovada_bloqueado(mock_now, client, db_session):
    mock_now.return_value = datetime(2026, 10, 2, 14, 0, tzinfo=FUSO_LLAB)

    _user, headers, weekly, _task, _wt = _criar_membro_e_weekly(client, db_session, "aprov_lock")

    # Envia e aprova
    weekly.status = "APROVADA"
    db_session.commit()

    res = client.patch(f"/weeklies/{weekly.id}/reabrir", headers=headers)
    assert res.status_code == 400
    assert "Não é possível reabrir uma weekly já aprovada" in res.json()["detail"]


@patch("app.weeklies.timezone_utils.get_now_fortaleza")
def test_reabrir_weekly_por_terceiro_bloqueado(mock_now, client, db_session):
    mock_now.return_value = datetime(2026, 10, 2, 14, 0, tzinfo=FUSO_LLAB)

    _user1, _headers1, weekly, _task, _wt = _criar_membro_e_weekly(client, db_session, "user1_reab")
    _user2, headers2, _w2, _t2, _wt2 = _criar_membro_e_weekly(client, db_session, "user2_reab")

    weekly.status = "ENVIADA"
    db_session.commit()

    # Usuário 2 tenta reabrir a weekly do usuário 1 -> 403
    res = client.patch(f"/weeklies/{weekly.id}/reabrir", headers=headers2)
    assert res.status_code == 403
    assert "Você não tem permissão para alterar esta weekly" in res.json()["detail"]


@patch("app.weeklies.timezone_utils.get_now_fortaleza")
def test_snapshot_preserva_prazo_historico_da_weekly_enviada(mock_now, client, db_session):
    """Garante que a alteração posterior do prazo de uma task não altera o prazo congelado
    no snapshot da weekly já enviada/aprovada.
    """
    mock_now.return_value = datetime(2026, 10, 2, 14, 0, tzinfo=FUSO_LLAB)

    _user, headers, weekly, task, _wt = _criar_membro_e_weekly(client, db_session, "snapshot_test")

    # 1. Envia a weekly com prazo original (2026-10-15)
    res_env = client.patch(f"/weeklies/{weekly.id}/enviar", headers=headers)
    assert res_env.status_code == 200
    assert res_env.json()["tasks"][0]["prazo_conclusao"] == "2026-10-15"

    # 2. Em um momento posterior, o prazo e título da task são alterados na tabela tasks
    task.prazo_conclusao = date(2026, 10, 30)
    task.titulo = "Título Alterado Posteriormente"
    db_session.commit()

    # 3. Consultar a task diretamente na listagem reflete o novo prazo e título
    res_task = client.get("/tasks/me", headers=headers)
    assert res_task.status_code == 200
    task_me = next(t for t in res_task.json()["tasks"] if t["id"] == str(task.id))
    assert task_me["prazo_conclusao"] == "2026-10-30"
    assert task_me["titulo"] == "Título Alterado Posteriormente"

    # 4. Consultar o relatório submetido preserva o snapshot histórico (2026-10-15 e Título Inicial)
    res_relatorio = client.get(f"/weeklies/{weekly.id}", headers=headers)
    assert res_relatorio.status_code == 200
    tarefa_relatorio = res_relatorio.json()["tasks"][0]
    assert tarefa_relatorio["prazo_conclusao"] == "2026-10-15"
    assert tarefa_relatorio["titulo"] == "Tarefa Inicial"

