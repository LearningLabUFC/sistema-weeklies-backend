"""Testes de concorrência e integridade transacional de Weeklies.

Cenários cobertos:
1. Edição de WeeklyTask concorrente à aprovação: a aprovação serializa e impede
   que uma alteração posterior sobrescreva a weekly aprovada.
2. Aprovação não sobrescreve remoção de Task (soft delete): tasks com status diferente
   de PENDENTE não são consolidadas como CONCLUIDA.
3. Aprovação recusa weekly sem tarefas (protege contra relatórios vazios).
4. Reenvio de weekly limpa metadados da avaliação anterior (avaliada_em, avaliada_por, observacao_lider).
5. Criação simultânea da weekly atual trata IntegrityError e retorna o registro vencedor sem erro 500.
"""

import threading
from datetime import date, datetime
from unittest.mock import patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.core.constants import RoleID, StatusID, TestID
from app.core.exceptions import BadRequestError, ConflictError
from app.models.sector_user import SectorUser
from app.models.task import Task
from app.models.task_assignment import TaskAssignment
from app.models.user import User
from app.models.weekly import Weekly
from app.models.weekly_task import WeeklyTask
from app.models.weekly_warning import WeeklyWarning
from app.weeklies.scheduler import _executar_com_advisory_lock
from app.weeklies.schemas import (
    EvaluateWeeklyRequest,
    UpdateTaskRequest,
    UpdateWeeklyTaskRequest,
)
from app.weeklies.service import (
    svc_evaluate_weekly,
    svc_obter_ou_criar_weekly_atual,
    svc_processar_advertencias_ausencias,
    svc_processar_auditoria_tasks,
    svc_processar_expiracao_weeklies,
    svc_respond_task_assignment,
    svc_send_weekly,
    svc_update_task,
    svc_update_weekly_task,
)

FUSO_LLAB = ZoneInfo("America/Fortaleza")


def _get_session_factory(db_session):
    return sessionmaker(autocommit=False, autoflush=False, bind=db_session.get_bind())


def _criar_usuario(db, email, matricula, papel="membro", global_role=RoleID.USUARIO):
    user = User(
        nome_completo=f"Usuário Concorrência {matricula}",
        email=email,
        senha_hash="hash_placeholder",
        matricula=str(matricula),
        data_nascimento=date(2000, 1, 1),
        data_ingresso=date(2026, 1, 1),
        curso_id=TestID.CURSO_TESTE,
        status_id=StatusID.ATIVO,
        global_role=global_role,
    )
    db.add(user)
    db.flush()

    assoc = SectorUser(usuario_id=user.id, setor_id=TestID.SETOR_TESTE, papel=papel)
    db.add(assoc)
    db.commit()
    db.refresh(user)
    return user


@patch("app.weeklies.timezone_utils.get_now_fortaleza")
def test_edicao_apos_aprovacao_bloqueada_por_lock(mock_now, db_session):
    """Garante que uma alteração tentada após a aprovação é rejeitada sem divergir os status."""
    mock_now.return_value = datetime(2026, 10, 2, 14, 0, tzinfo=FUSO_LLAB)

    SessionFactory = _get_session_factory(db_session)
    s_setup = SessionFactory()
    membro = _criar_usuario(s_setup, "conc_membro1@ufc.br", "881001", papel="membro")
    admin = _criar_usuario(s_setup, "conc_admin1@ufc.br", "881002", papel="lider", global_role=RoleID.ADMIN)

    task = Task(
        usuario_id=membro.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Tarefa Crítica Concorrência",
        status="PENDENTE",
    )
    s_setup.add(task)
    s_setup.flush()

    weekly = Weekly(
        usuario_id=membro.id,
        setor_id=TestID.SETOR_TESTE,
        semana_referencia=date(2026, 10, 5),
        status="ENVIADA",
        enviada_em=datetime.now(ZoneInfo("UTC")),
    )
    s_setup.add(weekly)
    s_setup.flush()

    wt = WeeklyTask(
        weekly_id=weekly.id,
        task_id=task.id,
        concluida=True,
        posicao=0,
    )
    s_setup.add(wt)
    s_setup.commit()

    admin_id = admin.id
    membro_id = membro.id
    weekly_id = weekly.id
    wt_id = wt.id
    task_id = task.id
    s_setup.close()

    # Sessão 1 (Líder/Admin): Avalia e aprova
    s_lider = SessionFactory()
    admin_user = s_lider.query(User).filter(User.id == admin_id).first()
    body_eval = EvaluateWeeklyRequest(status="APROVADA")
    svc_evaluate_weekly(weekly_id, body_eval, admin_user, s_lider)
    s_lider.close()

    # Sessão 2 (Membro): Tenta alterar a conclusão para False
    s_membro = SessionFactory()
    membro_user = s_membro.query(User).filter(User.id == membro_id).first()
    body_update = UpdateWeeklyTaskRequest(concluida=False)

    with pytest.raises(BadRequestError) as exc_info:
        svc_update_weekly_task(weekly_id, wt_id, body_update, membro_user, s_membro)

    assert "Não é possível alterar uma weekly com status 'APROVADA'" in str(exc_info.value)
    s_membro.close()

    # Validação no banco final: status mantidos íntegros
    s_check = SessionFactory()
    wt_final = s_check.query(WeeklyTask).filter(WeeklyTask.id == wt_id).first()
    task_final = s_check.query(Task).filter(Task.id == task_id).first()
    weekly_final = s_check.query(Weekly).filter(Weekly.id == weekly_id).first()

    assert weekly_final.status == "APROVADA"
    assert wt_final.concluida is True
    assert task_final.status == "CONCLUIDA"
    s_check.close()


@patch("app.weeklies.timezone_utils.get_now_fortaleza")
def test_aprovacao_nao_sobrescreve_soft_delete_de_task(mock_now, db_session):
    """Garante que uma task que foi soft-deleted pelo líder não seja sobrescrita para CONCLUIDA na aprovação."""
    mock_now.return_value = datetime(2026, 10, 2, 14, 0, tzinfo=FUSO_LLAB)

    SessionFactory = _get_session_factory(db_session)
    db = SessionFactory()
    membro = _criar_usuario(db, "conc_membro2@ufc.br", "882001", papel="membro")
    admin = _criar_usuario(db, "conc_admin2@ufc.br", "882002", papel="lider", global_role=RoleID.ADMIN)

    task = Task(
        usuario_id=membro.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Tarefa Soft Deleted",
        status="REMOVIDA_PELO_LIDER",  # Soft deleted antes do commit da aprovação
        removida_por=admin.id,
    )
    db.add(task)
    db.flush()

    weekly = Weekly(
        usuario_id=membro.id,
        setor_id=TestID.SETOR_TESTE,
        semana_referencia=date(2026, 10, 5),
        status="ENVIADA",
        enviada_em=datetime.now(ZoneInfo("UTC")),
    )
    db.add(weekly)
    db.flush()

    wt = WeeklyTask(
        weekly_id=weekly.id,
        task_id=task.id,
        concluida=True,
        posicao=0,
    )
    db.add(wt)
    db.commit()

    # Admin aprova a weekly
    admin_user = db.query(User).filter(User.id == admin.id).first()
    body_eval = EvaluateWeeklyRequest(status="APROVADA")
    svc_evaluate_weekly(weekly.id, body_eval, admin_user, db)

    # Confere que o status da task permanece REMOVIDA_PELO_LIDER e não CONCLUIDA
    db.refresh(task)
    assert task.status == "REMOVIDA_PELO_LIDER"
    assert task.removida_por == admin.id
    db.close()


@patch("app.weeklies.timezone_utils.get_now_fortaleza")
def test_aprovacao_rejeita_weekly_vazia(mock_now, db_session):
    """Garante que a aprovação de uma weekly sem tarefas seja rejeitada com erro 400."""
    mock_now.return_value = datetime(2026, 10, 2, 14, 0, tzinfo=FUSO_LLAB)

    SessionFactory = _get_session_factory(db_session)
    db = SessionFactory()
    membro = _criar_usuario(db, "conc_membro3@ufc.br", "883001", papel="membro")
    admin = _criar_usuario(db, "conc_admin3@ufc.br", "883002", papel="lider", global_role=RoleID.ADMIN)

    weekly = Weekly(
        usuario_id=membro.id,
        setor_id=TestID.SETOR_TESTE,
        semana_referencia=date(2026, 10, 5),
        status="ENVIADA",
        enviada_em=datetime.now(ZoneInfo("UTC")),
    )
    db.add(weekly)
    db.commit()

    admin_user = db.query(User).filter(User.id == admin.id).first()
    body_eval = EvaluateWeeklyRequest(status="APROVADA")

    with pytest.raises(BadRequestError) as exc_info:
        svc_evaluate_weekly(weekly.id, body_eval, admin_user, db)

    assert "Não é possível aprovar uma weekly que não contém nenhuma tarefa" in str(exc_info.value)
    db.close()


@patch("app.weeklies.timezone_utils.get_now_fortaleza")
def test_reenvio_limpa_campos_avaliacao_anterior(mock_now, db_session):
    """Garante que ao reenviar uma weekly rejeitada, os campos da avaliação anterior sejam limpos."""
    mock_now.return_value = datetime(2026, 10, 2, 14, 0, tzinfo=FUSO_LLAB)

    SessionFactory = _get_session_factory(db_session)
    db = SessionFactory()
    membro = _criar_usuario(db, "conc_membro4@ufc.br", "884001", papel="membro")
    admin = _criar_usuario(db, "conc_admin4@ufc.br", "884002", papel="lider", global_role=RoleID.ADMIN)

    task = Task(
        usuario_id=membro.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Tarefa de Reenvio",
        status="PENDENTE",
    )
    db.add(task)
    db.flush()

    weekly = Weekly(
        usuario_id=membro.id,
        setor_id=TestID.SETOR_TESTE,
        semana_referencia=date(2026, 10, 5),
        status="REJEITADA",
        avaliada_em=datetime.now(ZoneInfo("UTC")),
        avaliada_por=admin.id,
        observacao_lider="Ajustar tarefas",
    )
    db.add(weekly)
    db.flush()

    wt = WeeklyTask(
        weekly_id=weekly.id,
        task_id=task.id,
        concluida=False,
        posicao=0,
    )
    db.add(wt)
    db.commit()

    membro_user = db.query(User).filter(User.id == membro.id).first()
    resp = svc_send_weekly(weekly.id, membro_user, db)

    assert resp.status == "ENVIADA"
    assert resp.avaliada_em is None
    assert resp.avaliada_por is None
    assert resp.observacao_lider is None

    db.refresh(weekly)
    assert weekly.status == "ENVIADA"
    assert weekly.avaliada_em is None
    assert weekly.avaliada_por is None
    assert weekly.observacao_lider is None
    db.close()


@patch("app.weeklies.timezone_utils.get_now_fortaleza")
def test_criacao_simultanea_weekly_atual_recupera_existente(mock_now, db_session):
    """Simula conflito de unicidade (IntegrityError) em chamadas concorrentes ao obter/criar."""
    mock_now.return_value = datetime(2026, 10, 2, 14, 0, tzinfo=FUSO_LLAB)

    SessionFactory = _get_session_factory(db_session)
    db = SessionFactory()
    membro = _criar_usuario(db, "conc_membro5@ufc.br", "885001", papel="membro")

    with patch("app.weeklies.service.criar_weekly_com_rollover") as mock_criar:
        mock_criar.side_effect = IntegrityError("statement", "params", "orig")

        # Cria uma weekly previamente no banco simulando que a outra sessão inseriu primeiro
        weekly_vencedora = Weekly(
            usuario_id=membro.id,
            setor_id=TestID.SETOR_TESTE,
            semana_referencia=date(2026, 10, 5),
            status="RASCUNHO",
        )
        db.add(weekly_vencedora)
        db.commit()

        membro_user = db.query(User).filter(User.id == membro.id).first()
        # Não deve lançar erro 500, deve recuperar a weekly vencedora
        res = svc_obter_ou_criar_weekly_atual(TestID.SETOR_TESTE, membro_user, db)
        assert res.id == weekly_vencedora.id
        assert res.status == "RASCUNHO"

    db.close()


@patch("app.weeklies.timezone_utils.get_now_fortaleza")
def test_edicao_texto_task_bloqueada_em_weekly_aprovada(mock_now, db_session):
    """Garante que a edição do texto de uma task presente em weekly aprovada seja bloqueada."""
    mock_now.return_value = datetime(2026, 10, 2, 14, 0, tzinfo=FUSO_LLAB)

    SessionFactory = _get_session_factory(db_session)
    db = SessionFactory()
    membro = _criar_usuario(db, "conc_membro6@ufc.br", "886001", papel="membro")

    task = Task(
        usuario_id=membro.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Tarefa em Relatório Aprovado",
        descricao="Descrição original",
        status="PENDENTE",
    )
    db.add(task)
    db.flush()

    weekly = Weekly(
        usuario_id=membro.id,
        setor_id=TestID.SETOR_TESTE,
        semana_referencia=date(2026, 10, 5),
        status="APROVADA",
    )
    db.add(weekly)
    db.flush()

    wt = WeeklyTask(
        weekly_id=weekly.id,
        task_id=task.id,
        concluida=True,
        posicao=0,
    )
    db.add(wt)
    db.commit()

    membro_user = db.query(User).filter(User.id == membro.id).first()
    body_up = UpdateTaskRequest(titulo="Tentando Mudar Título")

    with pytest.raises(BadRequestError) as exc_info:
        svc_update_task(task.id, body_up, membro_user, db)

    assert "Não é possível editar uma task presente em uma weekly com status 'APROVADA'" in str(exc_info.value)
    db.close()


@patch("app.weeklies.timezone_utils.get_now_fortaleza")
def test_patch_descricao_null_remove_descricao(mock_now, db_session):
    """Garante que enviar {'descricao': None} remove a descrição opcional da task."""
    mock_now.return_value = datetime(2026, 10, 2, 14, 0, tzinfo=FUSO_LLAB)

    SessionFactory = _get_session_factory(db_session)
    db = SessionFactory()
    membro = _criar_usuario(db, "conc_membro7@ufc.br", "887001", papel="membro")

    task = Task(
        usuario_id=membro.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Tarefa com Descrição",
        descricao="Descrição que será removida",
        status="PENDENTE",
    )
    db.add(task)
    db.commit()

    membro_user = db.query(User).filter(User.id == membro.id).first()
    # model_fields_set conterá 'descricao'
    body_up = UpdateTaskRequest.model_validate({"descricao": None})
    assert "descricao" in body_up.model_fields_set

    res = svc_update_task(task.id, body_up, membro_user, db)
    assert res.descricao is None

    db.refresh(task)
    assert task.descricao is None
    db.close()


@patch("app.weeklies.timezone_utils.get_now_fortaleza")
def test_aceites_concorrentes_nao_duplicam_task(mock_now, db_session):
    """Garante que duas sessões concorrentes aceitando o mesmo convite geram exatamente UMA cópia da tarefa."""
    mock_now.return_value = datetime(2026, 10, 2, 14, 0, tzinfo=FUSO_LLAB)

    SessionFactory = _get_session_factory(db_session)
    db = SessionFactory()

    membro_a = _criar_usuario(db, "conc_solic@ufc.br", "991001", papel="membro")
    membro_b = _criar_usuario(db, "conc_atrib@ufc.br", "991002", papel="membro")

    task = Task(
        usuario_id=membro_a.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Task Origem Concorrente",
        status="PENDENTE",
    )
    db.add(task)
    db.commit()

    assignment = TaskAssignment(
        task_id=task.id,
        solicitante_id=membro_a.id,
        atribuido_id=membro_b.id,
        status="PENDENTE",
    )
    db.add(assignment)
    db.commit()
    assignment_id = assignment.id
    task_id = task.id
    membro_b_id = membro_b.id
    db.close()

    barrier = threading.Barrier(2)
    results = []
    errors = []

    def worker():
        local_db = SessionFactory()
        try:
            user_b = local_db.query(User).filter(User.id == membro_b_id).first()
            barrier.wait()
            resp = svc_respond_task_assignment(
                assignment_id=assignment_id,
                aceitar=True,
                current_user=user_b,
                db=local_db,
            )
            results.append(resp)
        except Exception as e:  # noqa: BLE001
            errors.append(e)
        finally:
            local_db.close()

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # Exatamente um deve ter sucesso e o outro deve falhar
    assert len(results) == 1, f"Esperado 1 sucesso, obtido {len(results)}"
    assert len(errors) == 1, f"Esperado 1 erro, obtido {len(errors)}"
    assert isinstance(errors[0], (BadRequestError, ConflictError))

    # Valida no banco de dados que existe RIGOROSAMENTE UMA cópia da tarefa
    check_db = SessionFactory()
    clones = (
        check_db.query(Task)
        .filter(
            Task.usuario_id == membro_b_id,
            Task.origem_task_id == task_id,
        )
        .all()
    )
    assert len(clones) == 1, f"Esperado exatamente 1 clone no banco, encontrados {len(clones)}"

    # Convite está ACEITA
    assign_final = check_db.query(TaskAssignment).filter(TaskAssignment.id == assignment_id).first()
    assert assign_final.status == "ACEITA"
    check_db.close()


def test_advertencias_concorrencia_savepoint_idempotente(db_session):
    """Garante que execuções concorrentes de processamento de advertências
    tratam a colisão de chave única (uq_warning_usuario_setor_semana) via savepoint,
    evitando erro 500, inserção duplicada e envio duplicado de e-mail.
    """
    engine = db_session.get_bind().engine
    SessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    s_setup = SessionFactory()

    sem_ref2 = date(2026, 9, 21)

    membro = _criar_usuario(
        s_setup,
        f"conc_adv_{uuid4().hex[:6]}@ufc.br",
        f"ADV{uuid4().hex[:5]}",
        papel="membro",
    )
    assoc = (
        s_setup.query(SectorUser)
        .filter(SectorUser.usuario_id == membro.id, SectorUser.setor_id == TestID.SETOR_TESTE)
        .first()
    )
    assoc.data_ingresso = date(2026, 9, 14)
    s_setup.commit()
    membro_id = membro.id
    s_setup.close()

    barrier = threading.Barrier(2)
    results = []
    errors = []

    try:
        with patch("app.weeklies.service.enviar_email_advertencia") as mock_email:
            def worker():
                local_db = SessionFactory()
                try:
                    barrier.wait()
                    res = svc_processar_advertencias_ausencias(local_db, semana_referencia=sem_ref2)
                    results.append(res)
                except Exception as e:  # noqa: BLE001
                    errors.append(e)
                finally:
                    local_db.close()

            t1 = threading.Thread(target=worker)
            t2 = threading.Thread(target=worker)
            t1.start()
            t2.start()
            t1.join()
            t2.join()

            assert len(errors) == 0, f"Erros inesperados nas threads: {errors}"
            assert len(results) == 2

            # Validação no banco de dados: RIGOROSAMENTE UMA advertência gravada
            check_db = SessionFactory()
            adverts = (
                check_db.query(WeeklyWarning)
                .filter(
                    WeeklyWarning.usuario_id == membro_id,
                    WeeklyWarning.setor_id == TestID.SETOR_TESTE,
                    WeeklyWarning.semana_referencia == sem_ref2,
                )
                .all()
            )
            assert len(adverts) == 1
            assert adverts[0].tipo == "1a_ADVERTENCIA"
            assert adverts[0].semanas_ausentes == 2
            check_db.close()

            # Notificação por e-mail deve ter ocorrido exatamente 1 vez
            assert mock_email.call_count == 1
    finally:
        clean_db = SessionFactory()
        clean_db.query(WeeklyWarning).filter(WeeklyWarning.usuario_id == membro_id).delete()
        clean_db.query(SectorUser).filter(SectorUser.usuario_id == membro_id).delete()
        clean_db.query(User).filter(User.id == membro_id).delete()
        clean_db.commit()
        clean_db.close()


def test_advertencias_concorrencia_simulada_com_conflito_savepoint(db_session):
    """Simula o caso de corrida estrita onde ambas as requisições passaram pela verificação
    SELECT existente, mas a segunda colide na constraint do PostgreSQL.
    Valida que o savepoint (db.begin_nested()) absorve a colisão sem quebrar a sessão.
    """
    SessionFactory = _get_session_factory(db_session)
    s1 = SessionFactory()
    s2 = SessionFactory()

    sem_ref2 = date(2026, 9, 21)

    membro = _criar_usuario(
        s1,
        f"conc_adv_sim_{uuid4().hex[:6]}@ufc.br",
        f"ADVS{uuid4().hex[:5]}",
        papel="membro",
    )
    assoc = (
        s1.query(SectorUser)
        .filter(SectorUser.usuario_id == membro.id, SectorUser.setor_id == TestID.SETOR_TESTE)
        .first()
    )
    assoc.data_ingresso = date(2026, 9, 1)
    s1.commit()
    membro_id = membro.id

    with patch("app.weeklies.service.enviar_email_advertencia") as mock_email:
        # Sessão 1 processa e insere a advertência
        res1 = svc_processar_advertencias_ausencias(s1, semana_referencia=sem_ref2)
        assert res1["advertencias_geradas"] == 1
        advs_res1 = [a for a in res1.get("detalhes", []) if a["usuario_id"] == str(membro_id)]
        assert len(advs_res1) == 1
        assert mock_email.call_count == 1

        # Sessão 2 tenta processar a mesma semana simulando race condition (find_warning retornou None)
        with patch("app.weeklies.service.find_warning_by_user_sector_semana", return_value=None):
            res2 = svc_processar_advertencias_ausencias(s2, semana_referencia=sem_ref2)
            assert res2["advertencias_geradas"] == 0
            advs_res2 = [a for a in res2.get("detalhes", []) if a["usuario_id"] == str(membro_id)]
            # Não deve ter inserido nem gerado advertência na sessão perdedora
            assert len(advs_res2) == 0
            # E-mail não deve ter sido reenviado
            assert mock_email.call_count == 1

    s1.close()
    s2.close()

    # Confirma que no banco há apenas 1 advertência
    check_db = SessionFactory()
    count = (
        check_db.query(WeeklyWarning)
        .filter(
            WeeklyWarning.usuario_id == membro_id,
            WeeklyWarning.setor_id == TestID.SETOR_TESTE,
            WeeklyWarning.semana_referencia == sem_ref2,
        )
        .count()
    )
    assert count == 1
    check_db.close()


def test_scheduler_advisory_lock_coordenacao_concorrente(db_session):
    """Valida que o PostgreSQL Advisory Lock impede que duas instâncias/réplicas
    executem o mesmo job cron simultaneamente.
    """
    bind = db_session.get_bind()
    if bind.dialect.name != "postgresql":
        pytest.skip("Advisory locks só são testáveis no PostgreSQL")

    test_lock_id = 889901
    engine = bind.engine
    SessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # 1. Conexão externa adquire o lock primeiro (simulando a Réplica A executando)
    conn_externa = engine.connect()
    adquiriu_externo = conn_externa.execute(
        text("SELECT pg_try_advisory_lock(:lock_id)"), {"lock_id": test_lock_id}
    ).scalar()
    assert adquiriu_externo is True

    try:
        # Patch SessionLocal e engine dentro de scheduler para usar a mesma base de teste
        with patch("app.weeklies.scheduler.SessionLocal", SessionFactory), patch("app.weeklies.scheduler.engine", engine):
            funcao_executada = False

            def dummy_job(db):
                nonlocal funcao_executada
                funcao_executada = True
                return {"executado": True}

            # 2. Réplica B tenta executar com o mesmo lock_id enquanto A ainda está com ele
            resultado = _executar_com_advisory_lock(test_lock_id, dummy_job)

            # Deve ignorar sem rodar a função
            assert resultado["executado"] is False
            assert resultado["motivo"] == "lock_concorrente_adquirido_por_outra_instancia"
            assert funcao_executada is False

    finally:
        # 3. Réplica A finaliza seu job e libera o lock
        conn_externa.execute(
            text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": test_lock_id}
        )
        conn_externa.close()

    # 4. Agora que o lock está livre, uma nova tentativa deve adquirir e executar normalmente
    with patch("app.weeklies.scheduler.SessionLocal", SessionFactory), patch("app.weeklies.scheduler.engine", engine):
        funcao_executada = False

        def dummy_job_2(db):
            nonlocal funcao_executada
            funcao_executada = True
            return {"sucesso": True}

        resultado_livre = _executar_com_advisory_lock(test_lock_id, dummy_job_2)
        assert resultado_livre == {"sucesso": True}
        assert funcao_executada is True


def test_job_expiracao_nao_desfaz_aprovacao_concorrente(db_session, monkeypatch):
    """
    Garante que atualizações condicionais atômicas no job de expiração impedem
    que uma weekly aprovada concorrentemente seja sobrescrita para EXPIRADA.
    """
    agora_sexta = datetime(2026, 10, 9, 0, 5, tzinfo=FUSO_LLAB)
    monkeypatch.setattr("app.weeklies.timezone_utils.get_now_fortaleza", lambda: agora_sexta)
    monkeypatch.setattr("app.weeklies.service.get_now_fortaleza", lambda: agora_sexta)

    SessionFactory = _get_session_factory(db_session)
    s_setup = SessionFactory()
    membro = _criar_usuario(s_setup, "conc_exp_membro@ufc.br", "882001", papel="membro")
    lider = _criar_usuario(s_setup, "conc_exp_lider@ufc.br", "882002", papel="lider", global_role=RoleID.ADMIN)

    task = Task(
        usuario_id=membro.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Task da Weekly Aprovada",
        status="PENDENTE",
    )
    s_setup.add(task)
    s_setup.flush()

    sem_ref = date(2026, 10, 5)
    weekly = Weekly(
        usuario_id=membro.id,
        setor_id=TestID.SETOR_TESTE,
        semana_referencia=sem_ref,
        status="ENVIADA",
        enviada_em=datetime(2026, 10, 5, 12, 0, tzinfo=FUSO_LLAB),
    )
    s_setup.add(weekly)
    s_setup.flush()

    w_task = WeeklyTask(
        weekly_id=weekly.id,
        task_id=task.id,
        origem="NOVA",
        concluida=True,
    )
    s_setup.add(w_task)
    s_setup.commit()

    weekly_id = weekly.id
    lider_id = lider.id
    s_setup.close()

    # Sessão A simula o job de expiração
    s_job = SessionFactory()

    # Sessão B simula a aprovação do líder enquanto o job está rodando
    s_lider = SessionFactory()
    weekly_b = s_lider.query(Weekly).filter(Weekly.id == weekly_id).first()
    weekly_b.status = "APROVADA"
    weekly_b.avaliada_em = datetime(2026, 10, 8, 23, 50, tzinfo=FUSO_LLAB)
    weekly_b.avaliada_por = lider_id
    s_lider.commit()
    s_lider.close()

    # O job de expiração executa a varredura
    res = svc_processar_expiracao_weeklies(s_job, semana_referencia=sem_ref)
    s_job.close()

    # Verifica que o job NÃO expirou a weekly aprovada
    assert res["total_expiradas"] == 0
    assert res["expiradas_omissao_lideranca"] == 0

    # Verifica o estado no banco de dados
    s_verificacao = SessionFactory()
    w_final = s_verificacao.query(Weekly).filter(Weekly.id == weekly_id).first()
    assert w_final.status == "APROVADA"
    assert w_final.motivo_expiracao is None
    s_verificacao.close()


def test_job_auditoria_nao_desfaz_conclusao_concorrente(db_session, monkeypatch):
    """
    Garante que atualizações condicionais atômicas no job de auditoria impedem
    que uma tarefa concluída concorrentemente retorne para EM_AUDITORIA.
    """
    momento_teste = datetime(2026, 10, 8, 10, 0, tzinfo=FUSO_LLAB)
    monkeypatch.setattr("app.weeklies.timezone_utils.get_now_fortaleza", lambda: momento_teste)
    monkeypatch.setattr("app.weeklies.service.get_now_fortaleza", lambda: momento_teste)

    SessionFactory = _get_session_factory(db_session)
    s_setup = SessionFactory()
    membro = _criar_usuario(s_setup, "conc_audit_membro@ufc.br", "883001", papel="membro")

    # Tarefa com prazo ontem (vencida)
    ontem = date(2026, 10, 7)
    task = Task(
        usuario_id=membro.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Tarefa Concluída Antes da Auditoria",
        status="PENDENTE",
        prazo_conclusao=ontem,
    )
    s_setup.add(task)
    s_setup.commit()
    task_id = task.id
    s_setup.close()

    # Sessão B simula o usuário/líder concluindo a tarefa concorrentemente
    s_concluir = SessionFactory()
    task_b = s_concluir.query(Task).filter(Task.id == task_id).first()
    task_b.status = "CONCLUIDA"
    s_concluir.commit()
    s_concluir.close()

    # Sessão A executa o job de auditoria
    s_job = SessionFactory()
    res = svc_processar_auditoria_tasks(s_job, momento=momento_teste)
    s_job.close()

    # A tarefa concluída não deve ter sido transicionada para EM_AUDITORIA
    assert res["novas_em_auditoria"] == 0

    # Verifica no banco que a tarefa continua CONCLUIDA
    s_verificacao = SessionFactory()
    t_final = s_verificacao.query(Task).filter(Task.id == task_id).first()
    assert t_final.status == "CONCLUIDA"
    assert t_final.entrada_auditoria_em is None
    s_verificacao.close()


@patch("app.weeklies.timezone_utils.get_now_fortaleza")
def test_aceite_convite_nao_adiciona_tarefa_a_weekly_ja_aprovada(mock_now, db_session):
    """
    Garante que o aceite de um convite de colaboração não vincula tarefa a uma weekly
    que já foi APROVADA (ou ENVIADA/REJEITADA/EXPIRADA), mantendo a tarefa avulsa.
    """
    # Segunda-feira dentro da janela regular
    segunda = datetime(2026, 10, 5, 14, 0, tzinfo=FUSO_LLAB)
    mock_now.return_value = segunda

    SessionFactory = _get_session_factory(db_session)
    s_setup = SessionFactory()
    solicitante = _criar_usuario(s_setup, "conc_solic@ufc.br", "884001", papel="membro")
    destinatario = _criar_usuario(s_setup, "conc_dest@ufc.br", "884002", papel="membro")

    task_orig = Task(
        usuario_id=solicitante.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Tarefa Original do Solicitante",
        status="PENDENTE",
    )
    s_setup.add(task_orig)
    s_setup.flush()

    # Destinatário já tem uma weekly APROVADA na semana de referência atual
    sem_ref = date(2026, 10, 5)
    weekly_aprovada = Weekly(
        usuario_id=destinatario.id,
        setor_id=TestID.SETOR_TESTE,
        semana_referencia=sem_ref,
        status="APROVADA",
        enviada_em=datetime(2026, 10, 5, 10, 0, tzinfo=FUSO_LLAB),
        avaliada_em=datetime(2026, 10, 5, 11, 0, tzinfo=FUSO_LLAB),
    )
    s_setup.add(weekly_aprovada)
    s_setup.flush()

    # Tarefa preexistente da weekly aprovada
    task_antiga = Task(
        usuario_id=destinatario.id,
        setor_id=TestID.SETOR_TESTE,
        titulo="Tarefa Antiga Aprovada",
        status="CONCLUIDA",
    )
    s_setup.add(task_antiga)
    s_setup.flush()

    w_item = WeeklyTask(
        weekly_id=weekly_aprovada.id,
        task_id=task_antiga.id,
        origem="NOVA",
        concluida=True,
    )
    s_setup.add(w_item)

    # Convite de tarefa
    assignment = TaskAssignment(
        task_id=task_orig.id,
        solicitante_id=solicitante.id,
        atribuido_id=destinatario.id,
        status="PENDENTE",
    )
    s_setup.add(assignment)
    s_setup.commit()

    assignment_id = assignment.id
    dest_id = destinatario.id
    weekly_id = weekly_aprovada.id
    task_orig_id = task_orig.id
    task_antiga_id = task_antiga.id
    s_setup.close()

    # Destinatário aceita o convite
    s_aceite = SessionFactory()
    user_dest = s_aceite.query(User).filter(User.id == dest_id).first()
    with patch("app.weeklies.service.enviar_email_resposta_convite_task"):
        svc_respond_task_assignment(assignment_id, True, user_dest, s_aceite)
    s_aceite.close()

    # Verificação:
    # 1. A nova tarefa foi criada no banco como PENDENTE para o destinatário
    s_check = SessionFactory()
    nova_copia = (
        s_check.query(Task)
        .filter(Task.usuario_id == dest_id, Task.origem_task_id == task_orig_id)
        .first()
    )
    assert nova_copia is not None
    assert nova_copia.status == "PENDENTE"

    # 2. A weekly APROVADA NÃO teve a nova tarefa vinculada (permanece com 1 tarefa apenas)
    itens_weekly = (
        s_check.query(WeeklyTask)
        .filter(WeeklyTask.weekly_id == weekly_id)
        .all()
    )
    assert len(itens_weekly) == 1
    assert itens_weekly[0].task_id == task_antiga_id
    s_check.close()





