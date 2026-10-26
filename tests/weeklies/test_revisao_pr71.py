"""
Testes de regressão para os 5 problemas apontados na revisão do PR #71:
- P1: Alteração de prazo pode reativar tarefa removida ou concluída (concorrência e locks).
- P1: SMTP síncrono bloqueia o event loop (BackgroundTasks e tolerância a falhas de envio).
- P2: Weekly rejeitada continua exibindo conteúdo anterior à correção (projeção e snapshots na aprovação direta).
- P2: Aceite de convite cria tarefa em setor inativo (elegibilidade, criação e revalidação no aceite).
- P2: Dashboard inclui administradores isentos na taxa de submissão (numerador/denominador alinhados).
"""

import asyncio
import smtplib
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from unittest.mock import patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi import BackgroundTasks
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.constants import RoleID, StatusID, TestID
from app.core.exceptions import BadRequestError
from app.core.security import criar_token_acesso
from app.database import Base
from app.models.course import Course
from app.models.role import Role
from app.models.sector import Sector
from app.models.sector_user import SectorUser
from app.models.status import Status
from app.models.task import Task
from app.models.task_assignment import TaskAssignment
from app.models.user import User
from app.models.weekly import Weekly
from app.models.weekly_task import WeeklyTask
from app.weeklies.schemas import (
    CreateTaskAssignmentRequest,
    UpdateTaskPrazoRequest,
)
from app.weeklies.service import (
    svc_concluir_task_auditoria,
    svc_create_task_assignment,
    svc_delete_task,
    svc_respond_task_assignment,
)
from app.weeklies.timezone_utils import get_now_fortaleza, obter_semana_referencia

FUSO_LLAB = ZoneInfo("America/Fortaleza")


@pytest.fixture
def concurrent_sessions(db_session):
    """Schema exclusivo com commits reais e uma conexão física por sessão."""
    base_engine = db_session.get_bind().engine
    assert base_engine.dialect.name == "postgresql"
    schema = "pr71_concurrency_" + uuid4().hex
    with base_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(
        base_engine.url,
        connect_args={"options": f"-csearch_path={schema} -cstatement_timeout=10000"},
    )
    factory = sessionmaker(bind=engine, autoflush=False)
    try:
        Base.metadata.create_all(engine)
        with factory() as db:
            db.add_all([
                Role(id=RoleID.USUARIO, nome="usuario"),
                Status(id=StatusID.ATIVO, nome="ativo"),
                Course(id=TestID.CURSO_TESTE, nome="Teste"),
                Sector(id=TestID.SETOR_TESTE, nome="Teste"),
            ])
            db.commit()
        yield factory
    finally:
        engine.dispose()
        with base_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))


def _criar_user_e_token(db, email, matricula, papel="membro", global_role=RoleID.USUARIO, setor_id=TestID.SETOR_TESTE):
    user = User(
        nome_completo=f"Usuário {matricula}",
        email=email,
        senha_hash="hash",
        matricula=str(matricula),
        data_nascimento=date(2000, 1, 1),
        data_ingresso=date(2026, 1, 1),
        curso_id=TestID.CURSO_TESTE,
        status_id=StatusID.ATIVO,
        global_role=global_role,
    )
    db.add(user)
    db.flush()

    if setor_id:
        assoc = SectorUser(usuario_id=user.id, setor_id=setor_id, papel=papel)
        db.add(assoc)
    db.commit()

    token = criar_token_acesso({"sub": str(user.id)})
    headers = {"Authorization": f"Bearer {token}"}
    return user, headers


# ── P1: Alteração de Prazo e Conclusão com Lock ───────────────


@pytest.mark.parametrize(
    "primeira,segunda,status_final",
    [
        ("remover", "prazo", "REMOVIDA_PELO_LIDER"),
        ("concluir", "prazo", "CONCLUIDA"),
        ("prazo", "remover", "REMOVIDA_PELO_LIDER"),
        ("prazo", "concluir", "CONCLUIDA"),
    ],
)
def test_transicoes_concorrentes_serializadas(
    concurrent_sessions, monkeypatch, primeira, segunda, status_final
):
    from app.weeklies import service

    factory = concurrent_sessions
    hoje = get_now_fortaleza().date()
    with factory() as db:
        membro, _ = _criar_user_e_token(db, "membro@test.com", "100001")
        lider, _ = _criar_user_e_token(db, "lider@test.com", "100002", papel="lider")
        task = Task(
            usuario_id=membro.id, setor_id=TestID.SETOR_TESTE,
            titulo="Disputa real", status="EM_AUDITORIA",
            prazo_conclusao=hoje - timedelta(days=2),
        )
        db.add(task)
        db.commit()
        task_id, lider_id = task.id, lider.id

    locked = threading.Event()
    release = threading.Event()
    second_started = threading.Event()
    local = threading.local()
    pids = {}
    original_find = service.find_task_by_id

    def pause_after_lock(db, *args, **kwargs):
        result = original_find(db, *args, **kwargs)
        if getattr(local, "hold", False):
            locked.set()
            assert release.wait(8), "A primeira operação não foi liberada"
        return result

    monkeypatch.setattr(service, "find_task_by_id", pause_after_lock)

    def execute(operation, first):
        local.hold = first
        with factory() as db:
            pids[first] = db.execute(text("SELECT pg_backend_pid()")).scalar_one()
            actor = db.get(User, lider_id)
            # Mantém uma versão antiga no identity map da segunda sessão.
            cached_task = db.get(Task, task_id)
            assert cached_task.status == "EM_AUDITORIA"
            if not first:
                second_started.set()
            try:
                if operation == "prazo":
                    service.svc_update_task_prazo(
                        task_id, UpdateTaskPrazoRequest(prazo_conclusao=hoje + timedelta(days=5)), actor, db
                    )
                elif operation == "remover":
                    svc_delete_task(task_id, actor, db)
                else:
                    svc_concluir_task_auditoria(task_id, actor, db)
                return "ok"
            except BadRequestError:
                db.rollback()
                return "rejected"

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(execute, primeira, True)
        try:
            assert locked.wait(5)
            second = executor.submit(execute, segunda, False)
            assert second_started.wait(5)
            assert pids[True] != pids[False]
            # Confirma no próprio PostgreSQL que as transações realmente disputam o lock.
            deadline = time.monotonic() + 5
            with factory() as observer:
                while time.monotonic() < deadline:
                    blockers = observer.execute(
                        text("SELECT pg_blocking_pids(:pid)"), {"pid": pids[False]}
                    ).scalar_one()
                    if pids[True] in blockers:
                        break
                    time.sleep(0.01)
                else:
                    pytest.fail("A segunda conexão não aguardou o lock da primeira")
        finally:
            release.set()
        assert first.result(timeout=10) == "ok"
        assert second.result(timeout=10) == ("rejected" if segunda == "prazo" else "ok")

    with factory() as db:
        task = db.get(Task, task_id)
        assert task.status == status_final
        assert task.removida_por == (lider_id if status_final == "REMOVIDA_PELO_LIDER" else None)
        expected = hoje + timedelta(days=5) if primeira == "prazo" else hoje - timedelta(days=2)
        assert task.prazo_conclusao == expected


def test_p1_conclusao_auditoria_bloqueada_para_tarefa_removida(db_session):
    """Garante que svc_concluir_task_auditoria impede concluir uma tarefa que foi removida."""
    membro, _ = _criar_user_e_token(db_session, f"membro_{uuid4().hex[:6]}@t.com", f"M{uuid4().hex[:6]}")
    lider, _ = _criar_user_e_token(db_session, f"lider_{uuid4().hex[:6]}@t.com", f"L{uuid4().hex[:6]}", papel="lider")

    task = Task(
        usuario_id=membro.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Task Auditoria Removida",
        status="REMOVIDA_PELO_LIDER",
        removida_por=lider.id,
    )
    db_session.add(task)
    db_session.commit()

    with pytest.raises(BadRequestError, match="removida"):
        svc_concluir_task_auditoria(task.id, current_user=lider, db=db_session)


# ── P1: Envio de E-mails com BackgroundTasks ──────────────────


def test_p1_criacao_e_resposta_convite_agendam_email_em_background_tasks(db_session):
    """Garante que os serviços de convite agendam e-mail via BackgroundTasks após o commit."""
    hoje = get_now_fortaleza().date()
    membro_origem, _ = _criar_user_e_token(db_session, f"m_orig_{uuid4().hex[:6]}@t.com", f"MO{uuid4().hex[:6]}")
    membro_destino, _ = _criar_user_e_token(db_session, f"m_dest_{uuid4().hex[:6]}@t.com", f"MD{uuid4().hex[:6]}")

    task = Task(
        usuario_id=membro_origem.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Task Convite Background",
        status="PENDENTE",
        prazo_conclusao=hoje + timedelta(days=3),
    )
    db_session.add(task)
    db_session.commit()

    bg_tasks = BackgroundTasks()

    # 1. Criação do convite
    req = CreateTaskAssignmentRequest(atribuido_id=membro_destino.id)
    with patch("app.weeklies.service.enviar_email_convite_task") as mock_email:
        assignment_resp = svc_create_task_assignment(
            task.id, req, current_user=membro_origem, db=db_session, background_tasks=bg_tasks
        )
        assert assignment_resp.status == "PENDENTE"
        # O mock_email NÃO deve ter sido executado sincronicamente no thread do service
        assert mock_email.call_count == 0
        # Mas deve ter sido enfileirado nas BackgroundTasks
        assert len(bg_tasks.tasks) == 1

    # 2. Aceite do convite com BackgroundTasks
    bg_tasks_aceite = BackgroundTasks()
    with patch("app.weeklies.service.enviar_email_resposta_convite_task") as mock_email_resp:
        resp_aceite = svc_respond_task_assignment(
            assignment_resp.id,
            aceitar=True,
            current_user=membro_destino,
            db=db_session,
            background_tasks=bg_tasks_aceite,
        )
        assert resp_aceite.status == "ACEITA"
        assert mock_email_resp.call_count == 0
        assert len(bg_tasks_aceite.tasks) == 1


# ── P2: Projeção de Dados de Weekly Rejeitada e Snapshots ─────


@pytest.mark.parametrize("reenviar", [False, True])
def test_p2_weekly_rejeitada_exibe_edicoes_e_consolida_snapshot_na_aprovacao_direta(client, db_session, reenviar):
    """Correções são congeladas na aprovação direta ou no reenvio anterior à aprovação."""
    _membro, h_membro = _criar_user_e_token(db_session, f"m_rej_{uuid4().hex[:6]}@t.com", f"MR{uuid4().hex[:6]}")
    _lider, h_lider = _criar_user_e_token(db_session, f"l_rej_{uuid4().hex[:6]}@t.com", f"LR{uuid4().hex[:6]}", papel="lider")

    semana_ref = obter_semana_referencia()

    # 1. Cria weekly e tarefa
    res_w = client.post(
        "/weeklies",
        headers=h_membro,
        json={"setor_id": str(TestID.SETOR_TESTE), "semana_referencia": str(semana_ref)},
    )
    assert res_w.status_code == 201
    weekly_id = res_w.json()["id"]

    res_t = client.post(
        f"/weeklies/{weekly_id}/tasks",
        headers=h_membro,
        json={
            "titulo": "Titulo Original Antes Rejeicao",
            "descricao": "Descricao Original",
            "prazo_conclusao": str(semana_ref + timedelta(days=4)),
        },
    )
    assert res_t.status_code == 201
    task_id = res_t.json()["task_id"]

    # 2. Membro envia a weekly
    res_env = client.patch(f"/weeklies/{weekly_id}/enviar", headers=h_membro)
    assert res_env.status_code == 200
    assert res_env.json()["status"] == "ENVIADA"

    # 3. Líder rejeita a weekly
    res_aval = client.patch(
        f"/weeklies/{weekly_id}/avaliar",
        headers=h_lider,
        json={"status": "REJEITADA", "observacao_lider": "Ajuste o título para detalhar melhor o escopo."},
    )
    assert res_aval.status_code == 200
    assert res_aval.json()["status"] == "REJEITADA"

    # 4. Membro atualiza a tarefa dentro do período de carência
    res_up = client.patch(
        f"/tasks/{task_id}",
        headers=h_membro,
        json={"titulo": "Titulo Corrigido Apos Rejeicao", "descricao": "Descricao Ajustada"},
    )
    assert res_up.status_code == 200

    # 5. Consulta detalhe da weekly: DEVE mostrar os dados corrigidos da Task
    res_get = client.get(f"/weeklies/{weekly_id}", headers=h_membro)
    assert res_get.status_code == 200
    tarefas_weekly = res_get.json()["tasks"]
    assert len(tarefas_weekly) == 1
    assert tarefas_weekly[0]["titulo"] == "Titulo Corrigido Apos Rejeicao"
    assert tarefas_weekly[0]["descricao"] == "Descricao Ajustada"

    if reenviar:
        res_reenvio = client.patch(f"/weeklies/{weekly_id}/enviar", headers=h_membro)
        assert res_reenvio.status_code == 200
        assert res_reenvio.json()["tasks"][0]["titulo"] == "Titulo Corrigido Apos Rejeicao"

    # 6. Líder aprova a versão corrigida, com ou sem reenvio
    res_aprov = client.patch(
        f"/weeklies/{weekly_id}/avaliar",
        headers=h_lider,
        json={"status": "APROVADA", "observacao_lider": "Aprovado após correção."},
    )
    assert res_aprov.status_code == 200
    assert res_aprov.json()["status"] == "APROVADA"

    # 7. Verifica que o snapshot congelado no banco agora contém os dados corrigidos
    weekly_task = (
        db_session.query(WeeklyTask)
        .filter(WeeklyTask.weekly_id == weekly_id, WeeklyTask.task_id == task_id)
        .first()
    )
    assert weekly_task.snapshot_titulo == "Titulo Corrigido Apos Rejeicao"
    assert weekly_task.snapshot_descricao == "Descricao Ajustada"


# ── P2: Setores Inativos e Convites ───────────────────────────


@pytest.mark.parametrize("com_outro_setor", [False, True])
def test_p2_destinatario_com_apenas_setor_inativo_e_revalidacao_no_aceite(client, db_session, com_outro_setor):
    """Garante que setores inativos não recebem convites e revalida setor ativo no aceite."""
    hoje = get_now_fortaleza().date()
    # Cria setor inativo
    setor_inativo = Sector(id=uuid4(), nome=f"Setor Inativo {uuid4().hex[:4]}", ativo=False)
    db_session.add(setor_inativo)
    db_session.commit()

    solicitante, h_solic = _criar_user_e_token(db_session, f"solic_{uuid4().hex[:6]}@t.com", f"S{uuid4().hex[:6]}")
    convidado_inativo, _ = _criar_user_e_token(
        db_session,
        f"inativo_{uuid4().hex[:6]}@t.com",
        f"I{uuid4().hex[:6]}",
        setor_id=setor_inativo.id,
    )

    task = Task(
        usuario_id=solicitante.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Task Teste Setor Inativo",
        status="PENDENTE",
        prazo_conclusao=hoje + timedelta(days=3),
    )
    db_session.add(task)
    db_session.commit()

    # 1. Usuário com apenas setor inativo não aparece na lista de elegíveis
    res_eleg = client.get("/tasks/colaboradores-elegiveis", headers=h_solic)
    assert res_eleg.status_code == 200
    ids_elegiveis = [c["id"] for c in res_eleg.json()["colaboradores"]]
    assert str(convidado_inativo.id) not in ids_elegiveis

    # 2. Criação de convite para membro em setor inativo é bloqueada
    res_atrib = client.post(
        f"/tasks/{task.id}/atribuir",
        headers=h_solic,
        json={"atribuido_id": str(convidado_inativo.id)},
    )
    assert res_atrib.status_code == 403

    # 3. Cenário de desativação entre convite e aceite:
    # Cria um novo membro em um setor temporariamente ativo
    setor_temp = Sector(id=uuid4(), nome=f"Setor Temp {uuid4().hex[:4]}", ativo=True)
    db_session.add(setor_temp)
    db_session.commit()

    convidado_temp, h_temp = _criar_user_e_token(
        db_session, f"temp_{uuid4().hex[:6]}@t.com", f"T{uuid4().hex[:6]}", setor_id=setor_temp.id
    )

    # Convite enviado com sucesso enquanto o setor estava ativo
    res_convite = client.post(
        f"/tasks/{task.id}/atribuir",
        headers=h_solic,
        json={"atribuido_id": str(convidado_temp.id)},
    )
    assert res_convite.status_code == 201
    assignment_id = res_convite.json()["id"]

    # Desativa o setor antes do aceite
    setor_temp.ativo = False
    if com_outro_setor:
        db_session.add(SectorUser(usuario_id=convidado_temp.id, setor_id=TestID.SETOR_TESTE, papel="membro"))
    db_session.commit()

    # Tentativa de aceite: deve ser recusada e expirar o convite
    res_aceite = client.patch(
        f"/atribuicoes/{assignment_id}/aceitar",
        headers=h_temp,
    )
    assert res_aceite.status_code == (200 if com_outro_setor else 403)

    # Confirma que nenhuma tarefa foi clonada no setor inativo
    clones = db_session.query(Task).filter(Task.origem_task_id == task.id).all()
    assert len(clones) == int(com_outro_setor)
    if clones:
        assert clones[0].setor_id == TestID.SETOR_TESTE


# ── P2: Dashboard Exclui Administradores Isentos ───────────────


def test_p2_dashboard_exclui_administradores_isentos_da_taxa_de_submissao(client, db_session):
    """Setor com 1 membro, 1 líder e 1 administrador: os 2 obrigados entregam e taxa é 100%."""
    novo_setor = Sector(id=uuid4(), nome=f"Setor Dash Taxa {uuid4().hex[:4]}", ativo=True)
    db_session.add(novo_setor)
    db_session.commit()

    semana_ref = obter_semana_referencia()

    # 1 Membro comum
    _membro, h_membro = _criar_user_e_token(
        db_session, f"m_taxa_{uuid4().hex[:6]}@t.com", f"MT{uuid4().hex[:6]}", setor_id=novo_setor.id
    )
    # 1 Líder do setor
    _lider, h_lider = _criar_user_e_token(
        db_session, f"l_taxa_{uuid4().hex[:6]}@t.com", f"LT{uuid4().hex[:6]}", papel="lider", setor_id=novo_setor.id
    )
    # 1 Administrador vinculado ao setor (isento de weekly)
    _admin, _ = _criar_user_e_token(
        db_session,
        f"a_taxa_{uuid4().hex[:6]}@t.com",
        f"AT{uuid4().hex[:6]}",
        global_role=RoleID.ADMIN,
        setor_id=novo_setor.id,
    )

    # Membro cria e envia weekly
    res_wm = client.post(
        "/weeklies",
        headers=h_membro,
        json={"setor_id": str(novo_setor.id), "semana_referencia": str(semana_ref)},
    )
    wm_id = res_wm.json()["id"]
    client.post(
        f"/weeklies/{wm_id}/tasks",
        headers=h_membro,
        json={"titulo": "Task Membro", "prazo_conclusao": str(semana_ref + timedelta(days=4))},
    )
    res_env_m = client.patch(f"/weeklies/{wm_id}/enviar", headers=h_membro)
    assert res_env_m.status_code == 200

    # Líder cria e envia weekly
    res_wl = client.post(
        "/weeklies",
        headers=h_lider,
        json={"setor_id": str(novo_setor.id), "semana_referencia": str(semana_ref)},
    )
    wl_id = res_wl.json()["id"]
    client.post(
        f"/weeklies/{wl_id}/tasks",
        headers=h_lider,
        json={"titulo": "Task Lider", "prazo_conclusao": str(semana_ref + timedelta(days=4))},
    )
    res_env_l = client.patch(f"/weeklies/{wl_id}/enviar", headers=h_lider)
    assert res_env_l.status_code == 200

    # Consulta dashboard do setor
    res_dash = client.get(
        f"/dashboard/setor/{novo_setor.id}?semana_referencia={semana_ref}",
        headers=h_lider,
    )
    assert res_dash.status_code == 200
    dados = res_dash.json()

    # Denominador deve ser 2 (apenas os 2 participantes obrigados: membro + líder)
    assert dados["total_membros"] == 2
    assert dados["weeklies_enviadas"] == 2
    assert dados["taxa_submissao_percentual"] == 100.0


@pytest.mark.parametrize("prazo_original", [None, date(2026, 10, 15)])
def test_aprovacao_preserva_snapshot_do_envio(client, db_session, prazo_original):
    membro, headers = _criar_user_e_token(db_session, "snapshot-m@test.com", "123001")
    _, lider_headers = _criar_user_e_token(db_session, "snapshot-l@test.com", "123002", papel="lider")
    weekly = client.post("/weeklies", headers=headers, json={"setor_id": str(TestID.SETOR_TESTE)}).json()
    task = Task(usuario_id=membro.id, setor_id=TestID.SETOR_TESTE, titulo="Original", prazo_conclusao=prazo_original)
    db_session.add(task)
    db_session.commit()
    response = client.post(f"/weeklies/{weekly['id']}/tasks", headers=headers, json={"task_id": str(task.id)})
    assert response.status_code == 201
    assert client.patch(f"/weeklies/{weekly['id']}/enviar", headers=headers).status_code == 200
    response = client.patch(
        f"/tasks/{task.id}/prazo", headers=lider_headers, json={"prazo_conclusao": "2026-10-30"}
    )
    assert response.status_code == 200
    # Mesmo campos historicamente nulos não devem usar valores vivos como fallback.
    task.descricao = "Descrição posterior"
    db_session.commit()
    expected_date = str(prazo_original) if prazo_original else None
    for response in [
        client.get(f"/weeklies/{weekly['id']}", headers=headers),
        client.patch(f"/weeklies/{weekly['id']}/avaliar", headers=lider_headers, json={"status": "APROVADA"}),
        client.get(f"/weeklies/{weekly['id']}", headers=headers),
    ]:
        assert response.status_code == 200
        item = response.json()["tasks"][0]
        assert item["prazo_conclusao"] == expected_date
        assert item["descricao"] is None


@pytest.mark.parametrize("status_admin", [None, "RASCUNHO", "ENVIADA"])
@pytest.mark.parametrize("com_obrigados", [False, True])
def test_dashboard_ignora_relatorios_opcionais_de_admin(
    client, db_session, status_admin, com_obrigados
):
    setor = Sector(nome=f"Dashboard {uuid4().hex}")
    db_session.add(setor)
    db_session.commit()
    admin, headers = _criar_user_e_token(
        db_session, "optional-admin@test.com", "124001", global_role=RoleID.ADMIN, setor_id=setor.id
    )
    semana = obter_semana_referencia()
    if status_admin:
        db_session.add(Weekly(usuario_id=admin.id, setor_id=setor.id, semana_referencia=semana, status=status_admin))
    if com_obrigados:
        for i, status in enumerate(["ENVIADA", "RASCUNHO"]):
            membro, _ = _criar_user_e_token(db_session, f"obrigado{i}@test.com", f"12400{i+2}", setor_id=setor.id)
            db_session.add(Weekly(usuario_id=membro.id, setor_id=setor.id, semana_referencia=semana, status=status))
    db_session.commit()
    expected_members, expected_rate = (2, 50.0) if com_obrigados else (0, 0.0)
    setor_data = client.get(f"/dashboard/setor/{setor.id}?semana_referencia={semana}", headers=headers).json()
    geral_data = client.get(f"/dashboard/geral?semana_referencia={semana}", headers=headers).json()
    assert setor_data["total_membros"] == geral_data["total_membros"] == expected_members
    assert setor_data["taxa_submissao_percentual"] == geral_data["taxa_submissao_geral_percentual"] == expected_rate
    assert setor_data["weeklies_enviadas"] == int(com_obrigados)
    assert setor_data["weeklies_rascunho"] == int(com_obrigados)


@pytest.mark.parametrize("prefixo", ["/atribuicoes", "/tasks/atribuicoes"])
@pytest.mark.parametrize("acao", ["aceitar", "recusar"])
@pytest.mark.parametrize("erro", [smtplib.SMTPException, OSError])
def test_falha_smtp_nao_quebra_convite_ou_resposta(
    client, db_session, mock_weekly_smtp, caplog, prefixo, acao, erro
):
    origem, headers = _criar_user_e_token(db_session, "smtp-origem@test.com", "125001")
    destino, destino_headers = _criar_user_e_token(db_session, "smtp-destino@test.com", "125002")
    task = Task(usuario_id=origem.id, setor_id=TestID.SETOR_TESTE, titulo="SMTP indisponível")
    db_session.add(task)
    db_session.commit()
    mock_weekly_smtp.side_effect = erro("Falha simulada")
    response = client.post(f"/tasks/{task.id}/atribuir", headers=headers, json={"atribuido_id": str(destino.id)})
    assert response.status_code == 201
    assignment_id = response.json()["id"]
    response = client.patch(f"{prefixo}/{assignment_id}/{acao}", headers=destino_headers)
    assert response.status_code == 200
    assignment = db_session.query(TaskAssignment).filter(TaskAssignment.id == assignment_id).one()
    assert assignment.status == ("ACEITA" if acao == "aceitar" else "RECUSADA")
    assert db_session.query(Task).filter(Task.origem_task_id == task.id).count() == int(acao == "aceitar")
    assert mock_weekly_smtp.call_count == 2
    assert all(call.kwargs["timeout"] > 0 for call in mock_weekly_smtp.call_args_list)
    assert "Falha no envio de notificação" in caplog.text


def test_smtp_lento_nao_bloqueia_event_loop(db_session, monkeypatch):
    from app.weeklies.router import atribuir_task

    origem, _ = _criar_user_e_token(db_session, "slow-origem@test.com", "126001")
    destino, _ = _criar_user_e_token(db_session, "slow-destino@test.com", "126002")
    task = Task(usuario_id=origem.id, setor_id=TestID.SETOR_TESTE, titulo="SMTP lento")
    db_session.add(task)
    db_session.commit()
    started, release = threading.Event(), threading.Event()
    released_while_waiting = []

    def slow_email(**kwargs):
        started.set()
        released_while_waiting.append(release.wait(3))

    monkeypatch.setattr("app.weeklies.service.enviar_email_convite_task", slow_email)

    async def run():
        background = BackgroundTasks()
        response = await atribuir_task(
            task.id, CreateTaskAssignmentRequest(atribuido_id=destino.id), background, origem, db_session
        )
        assert response.status == "PENDENTE"
        assert not started.is_set()

        async def other_request():
            assert await asyncio.to_thread(started.wait, 3)
            release.set()

        await asyncio.gather(background(), other_request())

    # Não altera o loop padrão usado pelos testes de ciclo de vida do scheduler.
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(run())
    finally:
        loop.close()
    assert released_while_waiting == [True]
