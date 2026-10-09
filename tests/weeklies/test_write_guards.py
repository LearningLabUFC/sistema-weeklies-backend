"""Regressões de janela, preservação de relatórios e revogação de vínculo."""

from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.config import settings
from app.core.constants import RoleID, StatusID, TestID
from app.core.exceptions import BadRequestError
from app.core.security import criar_token_acesso
from app.models.sector import Sector
from app.models.sector_user import SectorUser
from app.models.task import Task
from app.models.user import User
from app.models.weekly import Weekly
from app.models.weekly_task import WeeklyTask
from app.weeklies.timezone_utils import (
    FUSO_LLAB,
    validar_janela_submissao,
)

REFERENCE = date(2026, 10, 5)


@pytest.fixture
def member_weekly(db_session):
    member = User(
        nome_completo="Membro Teste",
        email="write-guards@example.com",
        senha_hash="unused",
        matricula="889901",
        data_nascimento=date(2000, 1, 1),
        data_ingresso=date(2026, 1, 1),
        curso_id=TestID.CURSO_TESTE,
        status_id=StatusID.ATIVO,
        global_role=RoleID.USUARIO,
    )
    db_session.add(member)
    db_session.flush()
    association = SectorUser(
        usuario_id=member.id, setor_id=TestID.SETOR_TESTE, papel="membro"
    )
    task = Task(
        usuario_id=member.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Texto original",
        descricao="Descrição original",
    )
    weekly = Weekly(
        usuario_id=member.id,
        setor_id=TestID.SETOR_TESTE,
        semana_referencia=REFERENCE,
        status="RASCUNHO",
    )
    db_session.add_all([association, task, weekly])
    db_session.flush()
    item = WeeklyTask(weekly_id=weekly.id, task_id=task.id)
    db_session.add(item)
    db_session.commit()
    token = criar_token_acesso({"sub": str(member.id)})
    return SimpleNamespace(
        member=member,
        association=association,
        task=task,
        weekly=weekly,
        item=item,
        headers={"Authorization": f"Bearer {token}"},
    )


def request_operation(client, context, action):
    weekly_path = f"/weeklies/{context.weekly.id}"
    task_path = f"{weekly_path}/tasks/{context.item.id}"
    operations = {
        "add": ("POST", f"{weekly_path}/tasks", {"titulo": "Nova tarefa"}),
        "link": ("POST", f"{weekly_path}/tasks", {"task_id": str(context.task.id)}),
        "update": ("PATCH", task_path, {"concluida": True}),
        "remove": ("DELETE", task_path, None),
        "send": ("PATCH", f"{weekly_path}/enviar", None),
        "edit_task": ("PATCH", f"/tasks/{context.task.id}", {"titulo": "Alterado"}),
        "create_task": ("POST", "/tasks", {"setor_id": str(TestID.SETOR_TESTE), "titulo": "Nova"}),
        "create_weekly": ("POST", "/weeklies", {"setor_id": str(TestID.SETOR_TESTE)}),
        "get_current": ("GET", f"/weeklies/me/atual?setor_id={TestID.SETOR_TESTE}", None),
    }
    method, path, body = operations[action]
    return client.request(method, path, headers=context.headers, json=body)


@pytest.mark.parametrize(
    ("timestamp", "allowed"),
    [
        ("2026-10-02T02:59:59.999999+00:00", False),
        ("2026-10-02T03:00:00+00:00", True),
        ("2026-10-06T02:59:59.999999+00:00", True),
        ("2026-10-06T03:00:00+00:00", False),
        ("2026-10-09T03:00:00+00:00", False),
    ],
)
def test_janela_do_relatorio_limites_e_proxima_sexta(timestamp, allowed):
    now = datetime.fromisoformat(timestamp)
    if allowed:
        validar_janela_submissao(now, semana_referencia=REFERENCE)
    else:
        with pytest.raises(BadRequestError):
            validar_janela_submissao(now, semana_referencia=REFERENCE)


@pytest.mark.parametrize("reference", ["2026-09-28", "2026-10-12", "2026-10-06"])
def test_criacao_recusa_semana_passada_futura_ou_nao_segunda(
    reference, client, db_session, member_weekly
):
    response = client.post(
        "/weeklies",
        headers=member_weekly.headers,
        json={"setor_id": str(TestID.SETOR_TESTE), "semana_referencia": reference},
    )
    assert response.status_code == 400
    assert db_session.query(Weekly).count() == 1


@pytest.mark.parametrize("reference", [date(2026, 9, 28), date(2026, 10, 12)])
@pytest.mark.parametrize("action", ["add", "update", "remove", "send"])
def test_escrita_recusa_relatorio_de_outra_janela(
    reference, action, client, db_session, member_weekly
):
    member_weekly.weekly.semana_referencia = reference
    db_session.commit()
    response = request_operation(client, member_weekly, action)
    assert response.status_code == 400
    db_session.expire_all()
    assert member_weekly.weekly.status == "RASCUNHO"
    assert member_weekly.weekly.enviada_em is None
    assert member_weekly.item.concluida is False
    assert db_session.query(WeeklyTask).count() == 1
    assert db_session.query(Task).count() == 1


@pytest.mark.parametrize("action", ["create_task", "edit_task", "add", "update", "remove", "send"])
def test_escrita_fora_da_janela_bloqueada(
    action, client, monkeypatch, member_weekly
):
    now = datetime(2026, 10, 6, 0, tzinfo=FUSO_LLAB)
    monkeypatch.setattr("app.weeklies.timezone_utils.get_now_fortaleza", lambda: now)
    response = request_operation(client, member_weekly, action)
    assert response.status_code == 400


@pytest.mark.parametrize(
    ("status", "reference"),
    [("APROVADA", REFERENCE), ("ENVIADA", date(2026, 9, 28)), ("RASCUNHO", date(2026, 9, 28))],
)
def test_editar_task_nao_reescreve_relatorio_aprovado_ou_encerrado(
    status, reference, client, db_session, member_weekly
):
    member_weekly.weekly.status = status
    member_weekly.weekly.semana_referencia = reference
    db_session.commit()
    response = client.patch(
        f"/tasks/{member_weekly.task.id}",
        headers=member_weekly.headers,
        json={"titulo": "Texto posterior", "descricao": "Descrição posterior"},
    )
    assert response.status_code == 400
    detail = client.get(f"/weeklies/{member_weekly.weekly.id}", headers=member_weekly.headers)
    assert detail.status_code == 200
    assert detail.json()["status"] == status
    assert detail.json()["tasks"][0]["titulo"] == "Texto original"
    assert detail.json()["tasks"][0]["descricao"] == "Descrição original"


def test_task_compartilhada_com_weekly_antiga_preserva_historico(
    client, db_session, member_weekly
):
    old = Weekly(
        usuario_id=member_weekly.member.id,
        setor_id=TestID.SETOR_TESTE,
        semana_referencia=date(2026, 9, 28),
        status="ENVIADA",
    )
    db_session.add(old)
    db_session.flush()
    db_session.add(WeeklyTask(weekly_id=old.id, task_id=member_weekly.task.id))
    db_session.commit()
    assert request_operation(client, member_weekly, "edit_task").status_code == 400


def test_edicao_de_task_na_weekly_atual_continua_permitida(client, member_weekly):
    response = request_operation(client, member_weekly, "edit_task")
    assert response.status_code == 200
    detail = client.get(f"/weeklies/{member_weekly.weekly.id}", headers=member_weekly.headers)
    assert detail.json()["tasks"][0]["titulo"] == "Alterado"


@pytest.mark.parametrize(
    "action", ["add", "link", "update", "remove", "send", "edit_task", "create_task", "create_weekly", "get_current"]
)
def test_remocao_do_vinculo_revoga_escrita(
    action, client, db_session, member_weekly
):
    db_session.delete(member_weekly.association)
    db_session.commit()
    response = request_operation(client, member_weekly, action)
    assert response.status_code == 403
    db_session.expire_all()
    assert member_weekly.weekly.status == "RASCUNHO"
    assert member_weekly.weekly.enviada_em is None
    assert member_weekly.task.titulo == "Texto original"
    assert member_weekly.item.concluida is False
    assert db_session.query(Task).count() == 1
    assert db_session.query(WeeklyTask).count() == 1


def test_membro_removido_pode_consultar_seu_historico(client, db_session, member_weekly):
    db_session.delete(member_weekly.association)
    db_session.commit()
    response = client.get(f"/weeklies/{member_weekly.weekly.id}", headers=member_weekly.headers)
    assert response.status_code == 200


def test_setor_inativo_rejeita_escrita_manual(client, db_session, member_weekly):
    """Garante que operações manuais de escrita são bloqueadas com 400 se o setor estiver desativado."""
    setor = db_session.query(Sector).filter(Sector.id == TestID.SETOR_TESTE).first()
    setor.ativo = False
    db_session.commit()

    try:
        # 1. Criar task no setor inativo -> 400
        res_task = client.post(
            "/tasks",
            headers=member_weekly.headers,
            json={"setor_id": str(TestID.SETOR_TESTE), "titulo": "Task em setor inativo"},
        )
        assert res_task.status_code == 400
        assert "inativo" in res_task.json()["detail"].lower()

        # 2. Alterar weekly de setor inativo -> 400
        res_weekly = client.patch(
            f"/weeklies/{member_weekly.weekly.id}/tasks/{member_weekly.item.id}",
            headers=member_weekly.headers,
            json={"concluida": True},
        )
        assert res_weekly.status_code == 400
        assert "inativo" in res_weekly.json()["detail"].lower()
    finally:
        setor.ativo = True
        db_session.commit()


def test_membro_nao_pode_remover_tarefa_herdada_mas_lider_pode(client, db_session, member_weekly):
    """Garante que membros não podem remover tarefas herdadas (rollover) de seus relatórios,
    mas a liderança pode intervir e remover.
    """
    member_weekly.item.origem = "HERDADA"
    db_session.commit()

    # Membro tenta remover tarefa herdada -> 403 Forbidden
    res_membro = client.delete(
        f"/weeklies/{member_weekly.weekly.id}/tasks/{member_weekly.item.id}",
        headers=member_weekly.headers,
    )
    assert res_membro.status_code == 403
    assert "herdadas" in res_membro.json()["detail"].lower()

    # Cria um líder para o setor
    lider = User(
        nome_completo="Líder Intervenção",
        email="lider-intervencao@example.com",
        senha_hash="unused",
        matricula="889902",
        data_nascimento=date(1995, 1, 1),
        data_ingresso=date(2025, 1, 1),
        curso_id=TestID.CURSO_TESTE,
        status_id=StatusID.ATIVO,
        global_role=RoleID.USUARIO,
    )
    db_session.add(lider)
    db_session.flush()
    assoc_lider = SectorUser(
        usuario_id=lider.id, setor_id=TestID.SETOR_TESTE, papel="lider"
    )
    db_session.add(assoc_lider)
    db_session.commit()
    token_lider = criar_token_acesso({"sub": str(lider.id)})
    headers_lider = {"Authorization": f"Bearer {token_lider}"}

    # Líder intervém e remove a tarefa herdada -> 200 OK
    res_lider = client.delete(
        f"/weeklies/{member_weekly.weekly.id}/tasks/{member_weekly.item.id}",
        headers=headers_lider,
    )
    assert res_lider.status_code == 200
    assert "removida" in res_lider.json()["mensagem"].lower()


def test_membro_pode_remover_tarefa_nova_em_rascunho(client, db_session, member_weekly):
    """Membro pode remover livremente uma tarefa de origem NOVA em sua weekly em rascunho."""
    member_weekly.item.origem = "NOVA"
    db_session.commit()

    res = client.delete(
        f"/weeklies/{member_weekly.weekly.id}/tasks/{member_weekly.item.id}",
        headers=member_weekly.headers,
    )
    assert res.status_code == 200
    assert "removida" in res.json()["mensagem"].lower()


def test_prazo_padrao_respeita_configuracao(client, member_weekly, monkeypatch):
    """Garante que a task criada sem prazo explícito usa settings.WEEKLY_TASK_DEFAULT_DEADLINE_DAYS."""
    monkeypatch.setattr(settings, "WEEKLY_TASK_DEFAULT_DEADLINE_DAYS", 21)

    from app.weeklies import timezone_utils

    hoje = timezone_utils.get_now_fortaleza().date()
    prazo_esperado = hoje + timedelta(days=21)

    res = client.post(
        "/tasks",
        headers=member_weekly.headers,
        json={"setor_id": str(TestID.SETOR_TESTE), "titulo": "Task Prazo Configurado"},
    )
    assert res.status_code == 201
    dados = res.json()
    assert dados["prazo_conclusao"] == prazo_esperado.isoformat()

