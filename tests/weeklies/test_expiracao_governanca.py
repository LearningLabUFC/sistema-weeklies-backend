"""
Testes de Governança e Expiração de Weeklies:
1. Bloqueio de Rejeição pelo Líder após Quarta-feira às 23:59:59.
2. Permissão de Aprovação pelo Líder após Quarta-feira (Quinta/Sexta).
3. Prazo de Carência de 24h para Membro Corrigir Weekly Rejeitada (fora da janela padrão).
4. Bloqueio de Edição e Reenvio pelo Membro após Expirar o Prazo de Carência de 24h.
5. Processamento Automático de Expiração por Omissão da Liderança (ENVIADA sem avaliação até Quinta 23:59).
6. Processamento Automático de Expiração por Falta de Correção do Membro (REJEITADA sem reenvio após 24h).
7. Rollover Automático de Tarefas Pendentes de Weeklies Expiradas na Criação em Lote.
8. Dashboards Setorial e Geral Contabilizam Weeklies Expiradas.
9. Weeklies Expiradas Não São Consideradas Ausências Não Justificadas.
"""

from datetime import date, datetime

from app.core.constants import RoleID, StatusID, TestID
from app.core.security import criar_token_acesso
from app.models.sector_user import SectorUser
from app.models.task import Task
from app.models.user import User
from app.models.weekly import Weekly
from app.models.weekly_task import WeeklyTask
from app.weeklies.scheduler import executar_criacao_weeklies_lote
from app.weeklies.service import (
    svc_get_global_dashboard,
    svc_get_sector_dashboard,
    svc_processar_advertencias_ausencias,
    svc_processar_expiracao_weeklies,
)
from app.weeklies.timezone_utils import FUSO_LLAB


def _criar_usuario_com_setor(
    db_session,
    email: str,
    matricula: str,
    papel: str = "membro",
    global_role: int = RoleID.USUARIO,
    setor_id=TestID.SETOR_TESTE,
):
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


# ── 1 e 2: Janela de Rejeição da Liderança (Quarta 23:59:59) ─


def test_lider_rejeicao_bloqueada_apos_quarta_feira(client, db_session, monkeypatch):
    """
    Líder não pode rejeitar uma weekly após quarta-feira às 23:59:59 da semana de referência.
    Porém, ainda pode aprová-la.
    """
    _membro, h_membro = _criar_usuario_com_setor(db_session, "exp_m1@test.com", "891001")
    _lider, h_lider = _criar_usuario_com_setor(db_session, "exp_l1@test.com", "891002", papel="lider")

    # Segunda-feira da janela: 2026-10-05
    segunda_envio = datetime(2026, 10, 5, 14, 0, tzinfo=FUSO_LLAB)
    monkeypatch.setattr("app.weeklies.timezone_utils.get_now_fortaleza", lambda: segunda_envio)
    monkeypatch.setattr("app.weeklies.service.get_now_fortaleza", lambda: segunda_envio)

    res_w = client.post(
        "/weeklies",
        headers=h_membro,
        json={"setor_id": str(TestID.SETOR_TESTE), "semana_referencia": "2026-10-05"},
    )
    assert res_w.status_code == 201
    weekly_id = res_w.json()["id"]

    client.post(
        f"/weeklies/{weekly_id}/tasks",
        headers=h_membro,
        json={"titulo": "Tarefa para validação de prazo"},
    )
    res_send = client.patch(f"/weeklies/{weekly_id}/enviar", headers=h_membro)
    assert res_send.status_code == 200

    # Avança para quinta-feira 08:00 (após quarta 23:59:59)
    quinta_feira = datetime(2026, 10, 8, 8, 0, tzinfo=FUSO_LLAB)
    monkeypatch.setattr("app.weeklies.timezone_utils.get_now_fortaleza", lambda: quinta_feira)
    monkeypatch.setattr("app.weeklies.service.get_now_fortaleza", lambda: quinta_feira)

    # 1. Tentar rejeitar na quinta-feira deve falhar com 400
    res_rej = client.patch(
        f"/weeklies/{weekly_id}/avaliar",
        headers=h_lider,
        json={"status": "REJEITADA", "observacao_lider": "Rejeição tardia"},
    )
    assert res_rej.status_code == 400
    assert "quarta-feira às 23:59" in res_rej.json()["detail"]

    # 2. Aprovar na quinta-feira deve funcionar normalmente
    res_aprov = client.patch(
        f"/weeklies/{weekly_id}/avaliar",
        headers=h_lider,
        json={"status": "APROVADA", "observacao_lider": "Aprovado com ressalvas verbais"},
    )
    assert res_aprov.status_code == 200
    assert res_aprov.json()["status"] == "APROVADA"


# ── 3 e 4: Carência de 24h para Correção do Membro ───────────


def test_membro_bloqueado_apos_carencia_24h_expirar(client, db_session, monkeypatch):
    """
    Quando o líder rejeita a weekly dentro do prazo permitido (ex: terça-feira),
    o membro tem exatamente 24 horas de carência (a partir de avaliada_em) para corrigir e reenviar.
    Após 24 horas, qualquer tentativa de alterar tasks ou reenviar deve retornar 400.
    """
    _membro, h_membro = _criar_usuario_com_setor(db_session, "exp_m2@test.com", "892001")
    _lider, h_lider = _criar_usuario_com_setor(db_session, "exp_l2@test.com", "892002", papel="lider")

    # Segunda-feira: membro envia weekly
    segunda_envio = datetime(2026, 10, 5, 20, 0, tzinfo=FUSO_LLAB)
    monkeypatch.setattr("app.weeklies.timezone_utils.get_now_fortaleza", lambda: segunda_envio)
    monkeypatch.setattr("app.weeklies.service.get_now_fortaleza", lambda: segunda_envio)

    res_w = client.post(
        "/weeklies",
        headers=h_membro,
        json={"setor_id": str(TestID.SETOR_TESTE), "semana_referencia": "2026-10-05"},
    )
    assert res_w.status_code == 201
    weekly_id = res_w.json()["id"]

    res_task = client.post(
        f"/weeklies/{weekly_id}/tasks",
        headers=h_membro,
        json={"titulo": "Tarefa Inicial"},
    )
    assert res_task.status_code == 201
    task_id = res_task.json()["task_id"]
    wt_id = res_task.json()["id"]

    client.patch(f"/weeklies/{weekly_id}/enviar", headers=h_membro)

    # Terça-feira 10:00: Líder rejeita com feedback
    terca_rejeicao = datetime(2026, 10, 6, 10, 0, tzinfo=FUSO_LLAB)
    monkeypatch.setattr("app.weeklies.timezone_utils.get_now_fortaleza", lambda: terca_rejeicao)
    monkeypatch.setattr("app.weeklies.service.get_now_fortaleza", lambda: terca_rejeicao)

    res_rej = client.patch(
        f"/weeklies/{weekly_id}/avaliar",
        headers=h_lider,
        json={"status": "REJEITADA", "observacao_lider": "Favor detalhar escopo"},
    )
    assert res_rej.status_code == 200

    # Quarta-feira 10:30 (24h e 30min após a rejeição -> prazo expirado)
    quarta_expirada = datetime(2026, 10, 7, 10, 30, tzinfo=FUSO_LLAB)
    monkeypatch.setattr("app.weeklies.timezone_utils.get_now_fortaleza", lambda: quarta_expirada)
    monkeypatch.setattr("app.weeklies.service.get_now_fortaleza", lambda: quarta_expirada)

    # 1. Tentativa de editar o texto da task associada deve falhar
    res_up_task = client.patch(
        f"/tasks/{task_id}",
        headers=h_membro,
        json={"titulo": "Tentando alterar após prazo"},
    )
    assert res_up_task.status_code == 400
    assert "carência de 24h" in res_up_task.json()["detail"]

    # 2. Tentativa de alterar a weekly_task (ex: impedimento) deve falhar
    res_up_wt = client.patch(
        f"/weeklies/{weekly_id}/tasks/{wt_id}",
        headers=h_membro,
        json={"impedimento": "Algum impedimento"},
    )
    assert res_up_wt.status_code == 400
    assert "carência de 24h" in res_up_wt.json()["detail"]

    # 3. Tentativa de adicionar nova tarefa na weekly deve falhar
    res_add_t = client.post(
        f"/weeklies/{weekly_id}/tasks",
        headers=h_membro,
        json={"titulo": "Nova tarefa tardia"},
    )
    assert res_add_t.status_code == 400
    assert "carência de 24h" in res_add_t.json()["detail"]

    # 4. Tentativa de reenviar a weekly deve falhar
    res_reenvio = client.patch(f"/weeklies/{weekly_id}/enviar", headers=h_membro)
    assert res_reenvio.status_code == 400
    assert "carência de 24h" in res_reenvio.json()["detail"]


# ── 5: Processamento de Expiração por Omissão da Liderança ────


def test_processar_expiracao_omissao_lideranca(client, db_session, monkeypatch):
    """
    Weekly enviada pelo membro na janela, mas que não foi avaliada pelo líder
    até quinta-feira às 23:59:59 (fim do ciclo de revisão), transiciona para EXPIRADA
    com motivo 'OMISSAO_LIDERANCA'.
    """
    _membro, h_membro = _criar_usuario_com_setor(db_session, "exp_m3@test.com", "893001")
    _lider, _h_lider = _criar_usuario_com_setor(db_session, "exp_l3@test.com", "893002", papel="lider")

    # Segunda-feira: membro envia weekly
    segunda_envio = datetime(2026, 10, 5, 12, 0, tzinfo=FUSO_LLAB)
    monkeypatch.setattr("app.weeklies.timezone_utils.get_now_fortaleza", lambda: segunda_envio)
    monkeypatch.setattr("app.weeklies.service.get_now_fortaleza", lambda: segunda_envio)

    res_w = client.post(
        "/weeklies",
        headers=h_membro,
        json={"setor_id": str(TestID.SETOR_TESTE), "semana_referencia": "2026-10-05"},
    )
    weekly_id = res_w.json()["id"]

    res_t = client.post(
        f"/weeklies/{weekly_id}/tasks",
        headers=h_membro,
        json={"titulo": "Tarefa que ficará pendente"},
    )
    task_id = res_t.json()["task_id"]

    client.patch(f"/weeklies/{weekly_id}/enviar", headers=h_membro)

    # Avança para sexta-feira 00:05 (quinta 23:59:59 já estourou)
    sexta_feira = datetime(2026, 10, 9, 0, 5, tzinfo=FUSO_LLAB)
    monkeypatch.setattr("app.weeklies.timezone_utils.get_now_fortaleza", lambda: sexta_feira)
    monkeypatch.setattr("app.weeklies.service.get_now_fortaleza", lambda: sexta_feira)

    # Executa a varredura de expiração
    resultado = svc_processar_expiracao_weeklies(db_session, semana_referencia=date(2026, 10, 5))
    assert resultado["expiradas_omissao_lideranca"] == 1

    # Verifica o estado no banco de dados
    db_session.expire_all()
    weekly_db = db_session.query(Weekly).filter(Weekly.id == weekly_id).first()
    assert weekly_db.status == "EXPIRADA"
    assert weekly_db.motivo_expiracao == "OMISSAO_LIDERANCA"
    assert "não avaliou o relatório" in weekly_db.detalhe_expiracao

    # Tarefa associada deve permanecer PENDENTE para permitir rollover
    task_db = db_session.query(Task).filter(Task.id == task_id).first()
    assert task_db.status == "PENDENTE"


# ── 6: Processamento de Expiração por Falta de Correção ───────


def test_processar_expiracao_falta_de_correcao_membro(client, db_session, monkeypatch):
    """
    Weekly rejeitada pelo líder cujo prazo de 24h expirou sem que o membro tenha
    reenviado o relatório transiciona para EXPIRADA com motivo 'CORRECAO_NAO_ENVIADA'.
    """
    _membro, h_membro = _criar_usuario_com_setor(db_session, "exp_m4@test.com", "894001")
    _lider, h_lider = _criar_usuario_com_setor(db_session, "exp_l4@test.com", "894002", papel="lider")

    # Segunda-feira: membro envia weekly
    segunda_envio = datetime(2026, 10, 5, 12, 0, tzinfo=FUSO_LLAB)
    monkeypatch.setattr("app.weeklies.timezone_utils.get_now_fortaleza", lambda: segunda_envio)
    monkeypatch.setattr("app.weeklies.service.get_now_fortaleza", lambda: segunda_envio)

    res_w = client.post(
        "/weeklies",
        headers=h_membro,
        json={"setor_id": str(TestID.SETOR_TESTE), "semana_referencia": "2026-10-05"},
    )
    weekly_id = res_w.json()["id"]

    res_t = client.post(
        f"/weeklies/{weekly_id}/tasks",
        headers=h_membro,
        json={"titulo": "Tarefa não corrigida"},
    )
    task_id = res_t.json()["task_id"]

    client.patch(f"/weeklies/{weekly_id}/enviar", headers=h_membro)

    # Terça-feira 14:00: líder rejeita
    terca_rejeicao = datetime(2026, 10, 6, 14, 0, tzinfo=FUSO_LLAB)
    monkeypatch.setattr("app.weeklies.timezone_utils.get_now_fortaleza", lambda: terca_rejeicao)
    monkeypatch.setattr("app.weeklies.service.get_now_fortaleza", lambda: terca_rejeicao)

    client.patch(
        f"/weeklies/{weekly_id}/avaliar",
        headers=h_lider,
        json={"status": "REJEITADA", "observacao_lider": "Necessário alinhar prioridades"},
    )

    # Quinta-feira 10:00 (mais de 24h após a rejeição)
    quinta_feira = datetime(2026, 10, 8, 10, 0, tzinfo=FUSO_LLAB)
    monkeypatch.setattr("app.weeklies.timezone_utils.get_now_fortaleza", lambda: quinta_feira)
    monkeypatch.setattr("app.weeklies.service.get_now_fortaleza", lambda: quinta_feira)

    # Executa a varredura
    resultado = svc_processar_expiracao_weeklies(db_session, semana_referencia=date(2026, 10, 5))
    assert resultado["expiradas_correcao_membro"] == 1

    db_session.expire_all()
    weekly_db = db_session.query(Weekly).filter(Weekly.id == weekly_id).first()
    assert weekly_db.status == "EXPIRADA"
    assert weekly_db.motivo_expiracao == "CORRECAO_NAO_ENVIADA"
    assert "não reenviou as correções no prazo de carência" in weekly_db.detalhe_expiracao

    # Tarefa associada continua PENDENTE
    task_db = db_session.query(Task).filter(Task.id == task_id).first()
    assert task_db.status == "PENDENTE"


# ── 7: Rollover Automático de Tasks de Weeklies Expiradas ─────


def test_criacao_lote_com_rollover_de_expiradas(client, db_session, monkeypatch):
    """
    Ao executar a criação em lote na abertura do novo ciclo (sexta-feira):
    1. A varredura expira automaticamente weeklies pendentes de semanas anteriores.
    2. O rollover herda as tarefas pendentes dessas weeklies expiradas para a nova weekly.
    """
    _membro, h_membro = _criar_usuario_com_setor(db_session, "exp_m5@test.com", "895001")
    _lider, _h_lider = _criar_usuario_com_setor(db_session, "exp_l5@test.com", "895002", papel="lider")

    # Semana anterior: 2026-10-05
    segunda_envio = datetime(2026, 10, 5, 12, 0, tzinfo=FUSO_LLAB)
    monkeypatch.setattr("app.weeklies.timezone_utils.get_now_fortaleza", lambda: segunda_envio)
    monkeypatch.setattr("app.weeklies.service.get_now_fortaleza", lambda: segunda_envio)

    res_w = client.post(
        "/weeklies",
        headers=h_membro,
        json={"setor_id": str(TestID.SETOR_TESTE), "semana_referencia": "2026-10-05"},
    )
    weekly_id = res_w.json()["id"]

    res_t = client.post(
        f"/weeklies/{weekly_id}/tasks",
        headers=h_membro,
        json={"titulo": "Tarefa Rollover Expirada"},
    )
    task_id = res_t.json()["task_id"]

    client.patch(f"/weeklies/{weekly_id}/enviar", headers=h_membro)

    # Sexta-feira da semana seguinte (2026-10-09 00:00) -> Abertura de lote para semana 2026-10-12
    sexta_abertura = datetime(2026, 10, 9, 0, 1, tzinfo=FUSO_LLAB)
    monkeypatch.setattr("app.weeklies.timezone_utils.get_now_fortaleza", lambda: sexta_abertura)
    monkeypatch.setattr("app.weeklies.service.get_now_fortaleza", lambda: sexta_abertura)

    resultado = executar_criacao_weeklies_lote(db_session, semana_referencia=date(2026, 10, 12))
    assert resultado["expiracao"]["expiradas_omissao_lideranca"] >= 1

    db_session.expire_all()
    # 1. Weekly antiga deve estar EXPIRADA
    w_antiga = db_session.query(Weekly).filter(Weekly.id == weekly_id).first()
    assert w_antiga.status == "EXPIRADA"
    assert w_antiga.motivo_expiracao == "OMISSAO_LIDERANCA"

    # 2. Nova weekly deve ter sido criada e conter a tarefa herdada
    w_nova = (
        db_session.query(Weekly)
        .filter(
            Weekly.usuario_id == _membro.id,
            Weekly.semana_referencia == date(2026, 10, 12),
        )
        .first()
    )
    assert w_nova is not None
    assert w_nova.status == "RASCUNHO"

    wt_herdada = (
        db_session.query(WeeklyTask)
        .filter(
            WeeklyTask.weekly_id == w_nova.id,
            WeeklyTask.task_id == task_id,
        )
        .first()
    )
    assert wt_herdada is not None
    assert wt_herdada.origem == "HERDADA"


# ── 8: Dashboards Contabilizam Weeklies Expiradas ─────────────


def test_dashboards_contabilizam_weeklies_expiradas(client, db_session, monkeypatch):
    """
    Verifica se os dashboards setorial e geral incluem weeklies expiradas
    no cálculo da taxa de submissão e no contador de weeklies expiradas.
    """
    _membro, _h_membro = _criar_usuario_com_setor(db_session, "exp_m6@test.com", "896001")
    lider, _h_lider = _criar_usuario_com_setor(db_session, "exp_l6@test.com", "896002", papel="lider")
    admin, _h_admin = _criar_usuario_com_setor(
        db_session, "exp_adm@test.com", "896003", global_role=RoleID.ADMIN
    )

    # Cria weekly e marca como EXPIRADA diretamente
    weekly = Weekly(
        usuario_id=_membro.id,
        setor_id=TestID.SETOR_TESTE,
        semana_referencia=date(2026, 10, 5),
        status="EXPIRADA",
        motivo_expiracao="OMISSAO_LIDERANCA",
        detalhe_expiracao="Líder não avaliou a tempo.",
    )
    db_session.add(weekly)
    db_session.commit()

    # Dashboard Setorial
    res_setor = svc_get_sector_dashboard(
        setor_id=TestID.SETOR_TESTE,
        semana_referencia=date(2026, 10, 5),
        current_user=lider,
        db=db_session,
    )
    assert res_setor.weeklies_expiradas >= 1
    # Como a weekly foi submetida antes de expirar, a taxa de submissão do setor deve contabilizá-la
    assert res_setor.taxa_submissao_percentual > 0

    # Dashboard Geral
    res_geral = svc_get_global_dashboard(
        semana_referencia=date(2026, 10, 5),
        current_user=admin,
        db=db_session,
    )
    assert res_geral.total_weeklies_expiradas >= 1


# ── 9: Expiradas Não São Consideradas Ausências ───────────────


def test_semanas_expiradas_nao_geram_advertencia_ausencia(client, db_session, monkeypatch):
    """
    Um membro cuja weekly expirou (por omissão do líder ou após carência) cumpriu o dever
    de submeter o relatório. Portanto, a rotina de advertências por ausência não deve penalizá-lo.
    """
    membro, _h_membro = _criar_usuario_com_setor(db_session, "exp_m7@test.com", "897001")

    weekly = Weekly(
        usuario_id=membro.id,
        setor_id=TestID.SETOR_TESTE,
        semana_referencia=date(2026, 10, 5),
        status="EXPIRADA",
        motivo_expiracao="OMISSAO_LIDERANCA",
    )
    db_session.add(weekly)
    db_session.commit()

    # Executa a verificação de ausências para a semana 2026-10-05
    res_adv = svc_processar_advertencias_ausencias(db_session, semana_referencia=date(2026, 10, 5))
    # O membro não deve figurar entre as advertências criadas
    assert not any(adv["usuario_id"] == membro.id for adv in res_adv.get("advertencias_criadas", []))
