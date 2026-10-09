"""Testes de casos de borda e regras de negócio adicionais (Itens 1 e 2).

Cobre:
- Rejeição de títulos em branco / apenas espaços em CreateTask, UpdateTask e AddWeeklyTask.
- Bloqueio de alteração de prazo ou remoção de tasks já concluídas pelo líder.
- Limpeza de impedimento ao enviar null no payload da weekly_task.
- Prevenção de re-envio de weekly já em status ENVIADA.
"""

from datetime import date, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.constants import RoleID, StatusID, TestID
from app.core.security import criar_token_acesso
from app.models.sector_user import SectorUser
from app.models.task import Task
from app.models.user import User
from app.models.weekly import Weekly
from app.models.weekly_task import WeeklyTask

REFERENCE = date(2026, 10, 5)


@pytest.fixture
def edge_case_context(db_session):
    # Membro
    membro = User(
        nome_completo="Membro Edge Case",
        email=f"membro-{uuid4().hex[:6]}@example.com",
        senha_hash="hash",
        matricula=f"M{uuid4().hex[:6]}",
        data_nascimento=date(2000, 1, 1),
        data_ingresso=date(2026, 1, 1),
        curso_id=TestID.CURSO_TESTE,
        status_id=StatusID.ATIVO,
        global_role=RoleID.USUARIO,
    )
    # Líder
    lider = User(
        nome_completo="Lider Edge Case",
        email=f"lider-{uuid4().hex[:6]}@example.com",
        senha_hash="hash",
        matricula=f"L{uuid4().hex[:6]}",
        data_nascimento=date(1995, 1, 1),
        data_ingresso=date(2025, 1, 1),
        curso_id=TestID.CURSO_TESTE,
        status_id=StatusID.ATIVO,
        global_role=RoleID.USUARIO,
    )
    db_session.add_all([membro, lider])
    db_session.flush()

    assoc_membro = SectorUser(
        usuario_id=membro.id, setor_id=TestID.SETOR_TESTE, papel="membro"
    )
    assoc_lider = SectorUser(
        usuario_id=lider.id, setor_id=TestID.SETOR_TESTE, papel="lider"
    )
    db_session.add_all([assoc_membro, assoc_lider])
    db_session.commit()

    token_membro = criar_token_acesso({"sub": str(membro.id)})
    token_lider = criar_token_acesso({"sub": str(lider.id)})

    return SimpleNamespace(
        membro=membro,
        lider=lider,
        headers_membro={"Authorization": f"Bearer {token_membro}"},
        headers_lider={"Authorization": f"Bearer {token_lider}"},
    )


def test_rejeicao_titulo_em_branco_create_task(client, edge_case_context):
    """Garante que títulos com apenas espaços são rejeitados no POST /tasks."""
    resp = client.post(
        "/tasks",
        headers=edge_case_context.headers_membro,
        json={
            "setor_id": str(TestID.SETOR_TESTE),
            "titulo": "   \t \n ",
        },
    )
    assert resp.status_code == 422
    assert "título da task não pode ser vazio" in resp.text


def test_rejeicao_titulo_em_branco_update_task(client, edge_case_context, db_session):
    """Garante que títulos com apenas espaços são rejeitados no PATCH /tasks/{id}."""
    task = Task(
        usuario_id=edge_case_context.membro.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Task Válida",
        status="PENDENTE",
    )
    db_session.add(task)
    db_session.commit()

    resp = client.patch(
        f"/tasks/{task.id}",
        headers=edge_case_context.headers_membro,
        json={"titulo": "    "},
    )
    assert resp.status_code == 422
    assert "título da task não pode ser vazio" in resp.text


def test_rejeicao_titulo_em_branco_add_weekly_task_inline(
    client, edge_case_context, db_session
):
    """Garante que criação inline com título apenas em espaços é rejeitada."""
    weekly = Weekly(
        usuario_id=edge_case_context.membro.id,
        setor_id=TestID.SETOR_TESTE,
        semana_referencia=REFERENCE,
        status="RASCUNHO",
    )
    db_session.add(weekly)
    db_session.commit()

    resp = client.post(
        f"/weeklies/{weekly.id}/tasks",
        headers=edge_case_context.headers_membro,
        json={"titulo": "   "},
    )
    assert resp.status_code == 422
    assert "título da task não pode ser vazio" in resp.text


def test_bloqueio_lider_alterar_prazo_task_concluida(
    client, edge_case_context, db_session
):
    """Líder não pode alterar prazo de task concluída."""
    task = Task(
        usuario_id=edge_case_context.membro.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Task Já Concluída",
        status="CONCLUIDA",
        prazo_conclusao=REFERENCE + timedelta(days=7),
    )
    db_session.add(task)
    db_session.commit()

    novo_prazo = str(REFERENCE + timedelta(days=14))
    resp = client.patch(
        f"/tasks/{task.id}/prazo",
        headers=edge_case_context.headers_lider,
        json={"prazo_conclusao": novo_prazo},
    )
    assert resp.status_code == 400
    assert "Não é possível alterar o prazo de uma task já concluída" in resp.json()["detail"]


def test_bloqueio_lider_remover_task_concluida(
    client, edge_case_context, db_session
):
    """Líder não pode soft-deletar task já concluída."""
    task = Task(
        usuario_id=edge_case_context.membro.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Task Concluída Histórica",
        status="CONCLUIDA",
    )
    db_session.add(task)
    db_session.commit()

    resp = client.delete(
        f"/tasks/{task.id}",
        headers=edge_case_context.headers_lider,
    )
    assert resp.status_code == 400
    assert "Não é possível remover uma task já concluída" in resp.json()["detail"]


def test_limpeza_impedimento_com_null(client, edge_case_context, db_session):
    """Permite limpar o impedimento de uma tarefa na weekly enviando null."""
    task = Task(
        usuario_id=edge_case_context.membro.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Task com Impedimento",
        status="PENDENTE",
    )
    weekly = Weekly(
        usuario_id=edge_case_context.membro.id,
        setor_id=TestID.SETOR_TESTE,
        semana_referencia=REFERENCE,
        status="RASCUNHO",
    )
    db_session.add_all([task, weekly])
    db_session.flush()

    wt = WeeklyTask(
        weekly_id=weekly.id,
        task_id=task.id,
        concluida=False,
        impedimento="Falta de acesso à API",
        posicao=0,
    )
    db_session.add(wt)
    db_session.commit()

    # 1. Enviar null no campo impedimento
    resp = client.patch(
        f"/weeklies/{weekly.id}/tasks/{wt.id}",
        headers=edge_case_context.headers_membro,
        json={"impedimento": None},
    )
    assert resp.status_code == 200
    assert resp.json()["impedimento"] is None

    # Verificar persistência no banco
    db_session.refresh(wt)
    assert wt.impedimento is None


def test_bloqueio_reenvio_weekly_ja_enviada(client, edge_case_context, db_session):
    """Tentar enviar uma weekly com status ENVIADA deve retornar 400."""
    task = Task(
        usuario_id=edge_case_context.membro.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Task Pronta",
        status="PENDENTE",
    )
    weekly = Weekly(
        usuario_id=edge_case_context.membro.id,
        setor_id=TestID.SETOR_TESTE,
        semana_referencia=REFERENCE,
        status="RASCUNHO",
    )
    db_session.add_all([task, weekly])
    db_session.flush()

    wt = WeeklyTask(
        weekly_id=weekly.id,
        task_id=task.id,
        concluida=False,
        posicao=0,
    )
    db_session.add(wt)
    db_session.commit()

    # Primeiro envio: sucesso
    resp1 = client.patch(
        f"/weeklies/{weekly.id}/enviar",
        headers=edge_case_context.headers_membro,
    )
    assert resp1.status_code == 200
    assert resp1.json()["status"] == "ENVIADA"

    # Segundo envio: bloqueado
    resp2 = client.patch(
        f"/weeklies/{weekly.id}/enviar",
        headers=edge_case_context.headers_membro,
    )
    assert resp2.status_code == 400
    assert "Esta weekly já foi enviada" in resp2.json()["detail"]
