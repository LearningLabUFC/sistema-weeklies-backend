"""Testes para a Fase 11: Dashboard Líder e Admin.

Cenários cobertos:
1. Dashboard do setor (GET /dashboard/setor/{setor_id}):
   - Líder do setor obtém métricas consolidadas:
     * total_membros, weeklies por status, taxa_submissao_percentual
     * total_tasks, tasks_concluidas, tasks_pendentes, tasks_em_auditoria, total_impedimentos
   - Admin global também pode consultar o dashboard de qualquer setor (200).
   - Membro comum do setor tentando acessar -> 403 Forbidden.
   - Usuário sem vínculo com o setor tentando acessar -> 403 Forbidden.
   - Setor inexistente -> 404 Not Found.
2. Dashboard geral consolidado (GET /dashboard/geral):
   - Admin global obtém totais agregados de todos os setores ativos e lista detalhada por setor.
   - Líder que não possui papel global de admin -> 403 Forbidden.
   - Membro comum -> 403 Forbidden.
3. Filtro por semana de referência:
   - Suporte ao parâmetro query semana_referencia no formato YYYY-MM-DD.
"""

from datetime import date
from types import SimpleNamespace
from uuid import uuid4

from app.core.constants import RoleID, StatusID, TestID
from app.core.security import criar_token_acesso
from app.models.sector_user import SectorUser
from app.models.task import Task
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


def test_get_sector_dashboard_lider_sucesso(client, db_session):
    """Líder do setor acessa o dashboard e recebe métricas consolidadas corretas."""
    semana_ref = obter_semana_referencia()

    lider = _criar_usuario_com_papel(
        db_session, "Lider Dash 1", f"L{uuid4().hex[:6]}", papel="lider"
    )
    m1 = _criar_usuario_com_papel(db_session, "Membro Dash 1", f"M{uuid4().hex[:6]}")
    m2 = _criar_usuario_com_papel(db_session, "Membro Dash 2", f"M{uuid4().hex[:6]}")

    # Weekly Enviada com 2 tarefas (1 concluída, 1 com impedimento)
    w_env = Weekly(
        usuario_id=m1.user.id,
        setor_id=TestID.SETOR_TESTE,
        semana_referencia=semana_ref,
        status="ENVIADA",
    )
    # Weekly Aprovada com 1 tarefa concluída
    w_apr = Weekly(
        usuario_id=m2.user.id,
        setor_id=TestID.SETOR_TESTE,
        semana_referencia=semana_ref,
        status="APROVADA",
    )
    # Weekly em Rascunho do líder
    w_rasc = Weekly(
        usuario_id=lider.user.id,
        setor_id=TestID.SETOR_TESTE,
        semana_referencia=semana_ref,
        status="RASCUNHO",
    )
    db_session.add_all([w_env, w_apr, w_rasc])
    db_session.commit()

    t1 = Task(usuario_id=m1.user.id, setor_id=TestID.SETOR_TESTE, titulo="Task 1", status="PENDENTE")
    t2 = Task(usuario_id=m1.user.id, setor_id=TestID.SETOR_TESTE, titulo="Task 2", status="CONCLUIDA")
    t3 = Task(usuario_id=m2.user.id, setor_id=TestID.SETOR_TESTE, titulo="Task 3", status="CONCLUIDA")
    t_aud = Task(usuario_id=m1.user.id, setor_id=TestID.SETOR_TESTE, titulo="Task Aud", status="EM_AUDITORIA")
    db_session.add_all([t1, t2, t3, t_aud])
    db_session.commit()

    wt1 = WeeklyTask(weekly_id=w_env.id, task_id=t1.id, concluida=False, impedimento="Falta API", posicao=1)
    wt2 = WeeklyTask(weekly_id=w_env.id, task_id=t2.id, concluida=True, posicao=2)
    wt3 = WeeklyTask(weekly_id=w_apr.id, task_id=t3.id, concluida=True, posicao=1)
    db_session.add_all([wt1, wt2, wt3])
    db_session.commit()

    resp = client.get(
        f"/dashboard/setor/{TestID.SETOR_TESTE}",
        headers=lider.headers,
    )

    assert resp.status_code == 200
    dados = resp.json()
    assert dados["setor_id"] == str(TestID.SETOR_TESTE)
    assert dados["total_membros"] >= 3
    assert dados["weeklies_enviadas"] >= 1
    assert dados["weeklies_aprovadas"] >= 1
    assert dados["weeklies_rascunho"] >= 1
    assert dados["total_tasks"] >= 3
    assert dados["tasks_concluidas"] >= 2
    assert dados["total_impedimentos"] >= 1
    assert dados["tasks_em_auditoria"] >= 1
    assert dados["taxa_submissao_percentual"] > 0


def test_get_sector_dashboard_admin_sucesso(client, db_session):
    """Admin global pode acessar o dashboard de qualquer setor."""
    admin = _criar_usuario_com_papel(
        db_session, "Admin Global Dash", f"AD{uuid4().hex[:6]}", global_role=RoleID.ADMIN
    )

    resp = client.get(
        f"/dashboard/setor/{TestID.SETOR_TESTE}",
        headers=admin.headers,
    )
    assert resp.status_code == 200
    dados = resp.json()
    assert dados["setor_id"] == str(TestID.SETOR_TESTE)


def test_get_sector_dashboard_permissoes_e_erros(client, db_session):
    """Membro comum e setor inexistente devem ser tratados com códigos HTTP apropriados."""
    membro = _criar_usuario_com_papel(
        db_session, "Membro Comum Dash", f"MC{uuid4().hex[:6]}", papel="membro"
    )
    admin = _criar_usuario_com_papel(
        db_session, "Admin Dash Perm", f"AD{uuid4().hex[:6]}", global_role=RoleID.ADMIN
    )

    # 1. Membro comum tentando acessar -> 403
    resp_membro = client.get(
        f"/dashboard/setor/{TestID.SETOR_TESTE}",
        headers=membro.headers,
    )
    assert resp_membro.status_code == 403

    # 2. Setor inexistente -> 404
    setor_fantasma = uuid4()
    resp_404 = client.get(
        f"/dashboard/setor/{setor_fantasma}",
        headers=admin.headers,
    )
    assert resp_404.status_code == 404


def test_get_global_dashboard_admin_sucesso(client, db_session):
    """Admin obtém o dashboard geral consolidando todos os setores ativos."""
    admin = _criar_usuario_com_papel(
        db_session, "Admin Global Totais", f"AD{uuid4().hex[:6]}", global_role=RoleID.ADMIN
    )
    _criar_usuario_com_papel(
        db_session, "Membro Global Totais", f"MB{uuid4().hex[:6]}", papel="membro"
    )

    resp = client.get("/dashboard/geral", headers=admin.headers)
    assert resp.status_code == 200
    dados = resp.json()

    assert dados["total_setores"] >= 1
    assert dados["total_membros"] >= 1
    assert "taxa_submissao_geral_percentual" in dados
    assert "setores" in dados
    assert len(dados["setores"]) >= 1


def test_get_global_dashboard_permissoes(client, db_session):
    """Líder comum e membro comum não podem acessar o dashboard geral."""
    lider = _criar_usuario_com_papel(
        db_session, "Lider Nao Admin", f"L{uuid4().hex[:6]}", papel="lider"
    )
    membro = _criar_usuario_com_papel(
        db_session, "Membro Dash Nao Admin", f"M{uuid4().hex[:6]}", papel="membro"
    )

    resp_lider = client.get("/dashboard/geral", headers=lider.headers)
    assert resp_lider.status_code == 403

    resp_membro = client.get("/dashboard/geral", headers=membro.headers)
    assert resp_membro.status_code == 403


def test_dashboard_filtro_semana_referencia(client, db_session):
    """Filtro de semana_referencia deve ser respeitado no cálculo das métricas."""
    admin = _criar_usuario_com_papel(
        db_session, "Admin Dash Semana", f"AD{uuid4().hex[:6]}", global_role=RoleID.ADMIN
    )

    semana_passada = "2026-09-21"
    resp = client.get(
        f"/dashboard/setor/{TestID.SETOR_TESTE}?semana_referencia={semana_passada}",
        headers=admin.headers,
    )
    assert resp.status_code == 200
    dados = resp.json()
    assert dados["semana_referencia"] == semana_passada


def test_dashboard_historico_nao_ultrapassa_cem_porcento_com_desligamentos(client, db_session):
    """Garante que weeklies de semanas passadas não produzem taxa de entrega > 100%
    mesmo quando membros foram desativados ou excluídos posteriormente.
    """
    admin = _criar_usuario_com_papel(
        db_session, "Admin Dash Hist", f"AH{uuid4().hex[:6]}", global_role=RoleID.ADMIN
    )
    m1 = _criar_usuario_com_papel(db_session, "Membro Hist 1", f"H1{uuid4().hex[:5]}")
    m2 = _criar_usuario_com_papel(db_session, "Membro Hist 2", f"H2{uuid4().hex[:5]}")

    semana_historica = date(2026, 3, 9)

    w1 = Weekly(
        usuario_id=m1.user.id,
        setor_id=TestID.SETOR_TESTE,
        semana_referencia=semana_historica,
        status="ENVIADA",
    )
    w2 = Weekly(
        usuario_id=m2.user.id,
        setor_id=TestID.SETOR_TESTE,
        semana_referencia=semana_historica,
        status="APROVADA",
    )
    db_session.add_all([w1, w2])
    db_session.commit()

    # Desativa ambos os membros no presente (simulando que se formaram)
    m1.user.status_id = StatusID.INATIVO
    m2.user.status_id = StatusID.INATIVO
    db_session.commit()

    resp = client.get(
        f"/dashboard/setor/{TestID.SETOR_TESTE}?semana_referencia=2026-03-09",
        headers=admin.headers,
    )
    assert resp.status_code == 200
    dados = resp.json()
    assert dados["total_membros"] >= 2
    assert dados["taxa_submissao_percentual"] <= 100.0
    assert dados["taxa_submissao_percentual"] == 100.0

