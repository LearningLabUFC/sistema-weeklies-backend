"""Testes automatizados de governança e hierarquia de avaliação de weeklies.

Regras testadas:
1. Ninguém pode avaliar a própria weekly (403 Forbidden).
2. Weeklies de líderes de setor só podem ser avaliadas por administradores globais (403 para co-líderes).
3. Administrador global pode avaliar weeklies de líderes.
4. Líder do setor pode avaliar weeklies de membros comuns.
5. Administrador não pode avaliar sua própria weekly se participar operacionalmente.
6. Outro administrador pode avaliar a weekly de um administrador.
"""

from datetime import date, datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app.core.constants import RoleID, StatusID, TestID
from app.models.sector_user import SectorUser
from app.models.task import Task
from app.models.user import User
from app.models.weekly import Weekly
from app.models.weekly_task import WeeklyTask

FUSO_LLAB = ZoneInfo("America/Fortaleza")


def _criar_e_logar(client, db_session, email, matricula, role_id=RoleID.USUARIO):
    """Cria um usuário ativo com role especificado e retorna (user, auth_header)."""
    letras = "".join(c for c in email.split("@")[0] if c.isalpha()).title()
    payload = {
        "nome_completo": f"Membro {letras} Silva",
        "email": email,
        "senha": "SenhaForte123!",
        "matricula": str(matricula).zfill(6),
        "data_nascimento": "2000-01-01",
        "meta_horas_semanais": 12,
        "curso_id": str(TestID.CURSO_TESTE),
    }
    res_reg = client.post("/auth/register", json=payload)
    assert res_reg.status_code == 201, f"Falha no registro: {res_reg.text}"
    user = db_session.query(User).filter(User.email == email).first()
    assert user is not None
    user.status_id = StatusID.ATIVO
    user.global_role = role_id
    db_session.commit()

    res = client.post("/auth/login", json={"email": email, "senha": "SenhaForte123!"})
    token = res.json()["token_acesso"]
    headers = {"Authorization": f"Bearer {token}"}
    return user, headers


def _vincular_setor(db_session, user_id, setor_id, papel="membro"):
    assoc = SectorUser(setor_id=setor_id, usuario_id=user_id, papel=papel)
    db_session.add(assoc)
    db_session.commit()
    return assoc


def _criar_weekly_enviada(db_session, user_id, setor_id, semana_ref):
    """Cria diretamente uma weekly com status ENVIADA e uma task associada."""
    task = Task(
        usuario_id=user_id,
        setor_id=setor_id,
        titulo="Tarefa operacional para teste de governança",
        status="PENDENTE",
    )
    db_session.add(task)
    db_session.flush()

    weekly = Weekly(
        usuario_id=user_id,
        setor_id=setor_id,
        semana_referencia=semana_ref,
        status="ENVIADA",
        enviada_em=datetime.now(ZoneInfo("UTC")),
    )
    db_session.add(weekly)
    db_session.flush()

    wt = WeeklyTask(
        weekly_id=weekly.id,
        task_id=task.id,
        concluida=True,
        posicao=0,
    )
    db_session.add(wt)
    db_session.commit()
    db_session.refresh(weekly)
    return weekly


@patch("app.weeklies.timezone_utils.get_now_fortaleza")
def test_lider_nao_pode_avaliar_propria_weekly(mock_now, client, db_session):
    mock_now.return_value = datetime(2026, 10, 2, 14, 0, tzinfo=FUSO_LLAB)

    lider, h_lider = _criar_e_logar(
        client, db_session, "lider_auto@ufc.br", 77101, RoleID.USUARIO
    )
    _vincular_setor(db_session, lider.id, TestID.SETOR_TESTE, papel="lider")

    weekly = _criar_weekly_enviada(
        db_session, lider.id, TestID.SETOR_TESTE, date(2026, 10, 5)
    )

    res = client.patch(
        f"/weeklies/{weekly.id}/avaliar",
        headers=h_lider,
        json={"status": "APROVADA"},
    )
    assert res.status_code == 403
    assert "Você não pode avaliar a sua própria weekly" in res.json()["detail"]


@patch("app.weeklies.timezone_utils.get_now_fortaleza")
def test_co_lider_nao_pode_avaliar_weekly_de_lider(mock_now, client, db_session):
    mock_now.return_value = datetime(2026, 10, 2, 14, 0, tzinfo=FUSO_LLAB)

    lider_autor, _ = _criar_e_logar(
        client, db_session, "lider_autor@ufc.br", 77102, RoleID.USUARIO
    )
    _vincular_setor(db_session, lider_autor.id, TestID.SETOR_TESTE, papel="lider")

    lider_par, h_lider_par = _criar_e_logar(
        client, db_session, "lider_par@ufc.br", 77103, RoleID.USUARIO
    )
    _vincular_setor(db_session, lider_par.id, TestID.SETOR_TESTE, papel="lider")

    weekly = _criar_weekly_enviada(
        db_session, lider_autor.id, TestID.SETOR_TESTE, date(2026, 10, 5)
    )

    res = client.patch(
        f"/weeklies/{weekly.id}/avaliar",
        headers=h_lider_par,
        json={"status": "APROVADA"},
    )
    assert res.status_code == 403
    assert "Weeklies de líderes só podem ser avaliadas por administradores" in res.json()["detail"]


@patch("app.weeklies.timezone_utils.get_now_fortaleza")
def test_admin_pode_avaliar_weekly_de_lider(mock_now, client, db_session):
    mock_now.return_value = datetime(2026, 10, 2, 14, 0, tzinfo=FUSO_LLAB)

    lider, _ = _criar_e_logar(
        client, db_session, "lider_para_admin@ufc.br", 77104, RoleID.USUARIO
    )
    _vincular_setor(db_session, lider.id, TestID.SETOR_TESTE, papel="lider")

    admin, h_admin = _criar_e_logar(
        client, db_session, "admin_avaliador@ufc.br", 77105, RoleID.ADMIN
    )

    weekly = _criar_weekly_enviada(
        db_session, lider.id, TestID.SETOR_TESTE, date(2026, 10, 5)
    )

    res = client.patch(
        f"/weeklies/{weekly.id}/avaliar",
        headers=h_admin,
        json={"status": "APROVADA"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "APROVADA"
    assert res.json()["avaliada_por"] == str(admin.id)


@patch("app.weeklies.timezone_utils.get_now_fortaleza")
def test_lider_pode_avaliar_weekly_de_membro_comum(mock_now, client, db_session):
    mock_now.return_value = datetime(2026, 10, 2, 14, 0, tzinfo=FUSO_LLAB)

    membro, _ = _criar_e_logar(
        client, db_session, "membro_comum@ufc.br", 77106, RoleID.USUARIO
    )
    _vincular_setor(db_session, membro.id, TestID.SETOR_TESTE, papel="membro")

    lider, h_lider = _criar_e_logar(
        client, db_session, "lider_do_setor@ufc.br", 77107, RoleID.USUARIO
    )
    _vincular_setor(db_session, lider.id, TestID.SETOR_TESTE, papel="lider")

    weekly = _criar_weekly_enviada(
        db_session, membro.id, TestID.SETOR_TESTE, date(2026, 10, 5)
    )

    res = client.patch(
        f"/weeklies/{weekly.id}/avaliar",
        headers=h_lider,
        json={"status": "APROVADA"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "APROVADA"
    assert res.json()["avaliada_por"] == str(lider.id)


@patch("app.weeklies.timezone_utils.get_now_fortaleza")
def test_admin_nao_pode_avaliar_propria_weekly(mock_now, client, db_session):
    mock_now.return_value = datetime(2026, 10, 2, 14, 0, tzinfo=FUSO_LLAB)

    admin, h_admin = _criar_e_logar(
        client, db_session, "admin_autor@ufc.br", 77108, RoleID.ADMIN
    )
    _vincular_setor(db_session, admin.id, TestID.SETOR_TESTE, papel="membro")

    weekly = _criar_weekly_enviada(
        db_session, admin.id, TestID.SETOR_TESTE, date(2026, 10, 5)
    )

    res = client.patch(
        f"/weeklies/{weekly.id}/avaliar",
        headers=h_admin,
        json={"status": "APROVADA"},
    )
    assert res.status_code == 403
    assert "Você não pode avaliar a sua própria weekly" in res.json()["detail"]


@patch("app.weeklies.timezone_utils.get_now_fortaleza")
def test_outro_admin_pode_avaliar_weekly_de_admin(mock_now, client, db_session):
    mock_now.return_value = datetime(2026, 10, 2, 14, 0, tzinfo=FUSO_LLAB)

    admin_autor, _ = _criar_e_logar(
        client, db_session, "admin_autor2@ufc.br", 77109, RoleID.ADMIN
    )
    _vincular_setor(db_session, admin_autor.id, TestID.SETOR_TESTE, papel="membro")

    admin_avaliador, h_admin2 = _criar_e_logar(
        client, db_session, "admin_avaliador2@ufc.br", 77110, RoleID.ADMIN
    )

    weekly = _criar_weekly_enviada(
        db_session, admin_autor.id, TestID.SETOR_TESTE, date(2026, 10, 5)
    )

    res = client.patch(
        f"/weeklies/{weekly.id}/avaliar",
        headers=h_admin2,
        json={"status": "APROVADA"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "APROVADA"
    assert res.json()["avaliada_por"] == str(admin_avaliador.id)
