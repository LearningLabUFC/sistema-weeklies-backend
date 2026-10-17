"""Testes para o módulo de Weeklies — CRUD de Tasks (Fase 2) e Ciclo de Vida de Weeklies (Fase 3)."""

from datetime import date, datetime, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app.core.constants import RoleID, StatusID, TestID
from app.models.sector import Sector
from app.models.sector_user import SectorUser
from app.models.task import Task
from app.models.user import User
from app.models.weekly import Weekly
from app.weeklies.timezone_utils import (
    FUSO_LLAB,
    dentro_da_janela,
    obter_semana_referencia,
)

# ── Helpers de Usuários e Setores ────────────────────────────


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
    """Vincula um usuário a um setor com papel específico."""
    assoc = SectorUser(setor_id=setor_id, usuario_id=user_id, papel=papel)
    db_session.add(assoc)
    db_session.commit()
    return assoc


# ── 1. Testes Unitários de Fuso Horário e Janela ──────────────


def test_timezone_utils_dentro_da_janela():
    # Sexta-feira às 14:00 (ABERTA)
    dt_sexta = datetime(2026, 10, 2, 14, 0, 0, tzinfo=FUSO_LLAB)
    assert dentro_da_janela(dt_sexta) is True

    # Sábado às 10:00 (ABERTA)
    dt_sabado = datetime(2026, 10, 3, 10, 0, 0, tzinfo=FUSO_LLAB)
    assert dentro_da_janela(dt_sabado) is True

    # Domingo às 22:00 (ABERTA)
    dt_domingo = datetime(2026, 10, 4, 22, 0, 0, tzinfo=FUSO_LLAB)
    assert dentro_da_janela(dt_domingo) is True

    # Segunda-feira às 23:59 (ABERTA)
    dt_segunda = datetime(2026, 10, 5, 23, 59, 0, tzinfo=FUSO_LLAB)
    assert dentro_da_janela(dt_segunda) is True

    # Terça-feira às 00:01 (FECHADA)
    dt_terca = datetime(2026, 10, 6, 0, 1, 0, tzinfo=FUSO_LLAB)
    assert dentro_da_janela(dt_terca) is False

    # Quarta-feira às 12:00 (FECHADA)
    dt_quarta = datetime(2026, 10, 7, 12, 0, 0, tzinfo=FUSO_LLAB)
    assert dentro_da_janela(dt_quarta) is False

    # Quinta-feira às 18:00 (FECHADA)
    dt_quinta = datetime(2026, 10, 8, 18, 0, 0, tzinfo=FUSO_LLAB)
    assert dentro_da_janela(dt_quinta) is False


def test_timezone_utils_obter_semana_referencia():
    # Sexta 02/10/2026 -> próxima segunda é 05/10/2026
    dt_sexta = datetime(2026, 10, 2, 12, 0, 0, tzinfo=FUSO_LLAB)
    assert obter_semana_referencia(dt_sexta) == date(2026, 10, 5)

    # Sábado 03/10/2026 -> próxima segunda é 05/10/2026
    dt_sabado = datetime(2026, 10, 3, 12, 0, 0, tzinfo=FUSO_LLAB)
    assert obter_semana_referencia(dt_sabado) == date(2026, 10, 5)

    # Domingo 04/10/2026 -> próxima segunda é 05/10/2026
    dt_domingo = datetime(2026, 10, 4, 12, 0, 0, tzinfo=FUSO_LLAB)
    assert obter_semana_referencia(dt_domingo) == date(2026, 10, 5)

    # Segunda 05/10/2026 -> ela mesma 05/10/2026
    dt_segunda = datetime(2026, 10, 5, 12, 0, 0, tzinfo=FUSO_LLAB)
    assert obter_semana_referencia(dt_segunda) == date(2026, 10, 5)

    # Terça 06/10/2026 -> fechamento recente foi 05/10/2026
    dt_terca = datetime(2026, 10, 6, 12, 0, 0, tzinfo=FUSO_LLAB)
    assert obter_semana_referencia(dt_terca) == date(2026, 10, 5)


# ── 2. Testes de Integração — CRUD de Tasks (Fase 2) ──────────


def test_tasks_crud_fluxo_completo(client, db_session):
    user, headers = _criar_e_logar(
        client, db_session, "taskmember@teste.com", "99001"
    )
    _vincular_setor(db_session, user.id, TestID.SETOR_TESTE, "membro")

    # 1. Criar task com sucesso
    res = client.post(
        "/tasks",
        headers=headers,
        json={
            "setor_id": str(TestID.SETOR_TESTE),
            "titulo": "Implementar endpoints de weeklies",
            "descricao": "Criar router, service e schemas",
        },
    )
    assert res.status_code == 201
    task_data = res.json()
    task_id = task_data["id"]
    assert task_data["titulo"] == "Implementar endpoints de weeklies"
    assert task_data["status"] == "PENDENTE"
    assert task_data["usuario_id"] == str(user.id)
    assert task_data["setor_id"] == str(TestID.SETOR_TESTE)

    # 2. Listar tasks do usuário
    res_list = client.post(
        "/tasks",
        headers=headers,
        json={
            "setor_id": str(TestID.SETOR_TESTE),
            "titulo": "Segunda tarefa de teste",
        },
    )
    assert res_list.status_code == 201

    res_me = client.get("/tasks/me", headers=headers)
    assert res_me.status_code == 200
    assert res_me.json()["total"] == 2

    # 3. Editar task (apenas dono pode editar título/descrição)
    res_edit = client.patch(
        f"/tasks/{task_id}",
        headers=headers,
        json={"titulo": "Implementar endpoints de weeklies atualizado"},
    )
    assert res_edit.status_code == 200
    assert res_edit.json()["titulo"] == "Implementar endpoints de weeklies atualizado"

    # 4. Outro usuário não pode editar a task (Garantia 1 / IDOR)
    other_user, other_headers = _criar_e_logar(
        client, db_session, "otheruser@teste.com", "99002"
    )
    _vincular_setor(db_session, other_user.id, TestID.SETOR_TESTE, "membro")
    res_idor = client.patch(
        f"/tasks/{task_id}",
        headers=other_headers,
        json={"titulo": "Tentativa hacker"},
    )
    assert res_idor.status_code == 403


def test_tasks_prazo_e_soft_delete_por_lider(client, db_session):
    membro, headers_membro = _criar_e_logar(
        client, db_session, "membro_comum@teste.com", "99003"
    )
    lider, headers_lider = _criar_e_logar(
        client, db_session, "lider_setor@teste.com", "99004"
    )
    _vincular_setor(db_session, membro.id, TestID.SETOR_TESTE, "membro")
    _vincular_setor(db_session, lider.id, TestID.SETOR_TESTE, "lider")

    res_task = client.post(
        "/tasks",
        headers=headers_membro,
        json={
            "setor_id": str(TestID.SETOR_TESTE),
            "titulo": "Tarefa com prazo a ser alterado",
        },
    )
    task_id = res_task.json()["id"]

    # Membro comum tenta alterar prazo -> 403
    res_prazo_membro = client.patch(
        f"/tasks/{task_id}/prazo",
        headers=headers_membro,
        json={"prazo_conclusao": "2026-11-01"},
    )
    assert res_prazo_membro.status_code == 403

    # Líder tenta alterar prazo para o passado -> 400
    res_prazo_lider_passado = client.patch(
        f"/tasks/{task_id}/prazo",
        headers=headers_lider,
        json={"prazo_conclusao": "2000-01-01"},
    )
    assert res_prazo_lider_passado.status_code == 400

    # Líder do setor altera prazo com sucesso -> 200
    res_prazo_lider = client.patch(
        f"/tasks/{task_id}/prazo",
        headers=headers_lider,
        json={"prazo_conclusao": "2026-11-01"},
    )
    assert res_prazo_lider.status_code == 200
    assert res_prazo_lider.json()["prazo_conclusao"] == "2026-11-01"

    # Membro comum tenta remover task -> 403
    res_del_membro = client.delete(f"/tasks/{task_id}", headers=headers_membro)
    assert res_del_membro.status_code == 403

    # Líder remove task (soft delete) -> 200
    res_del_lider = client.delete(f"/tasks/{task_id}", headers=headers_lider)
    assert res_del_lider.status_code == 200

    # Task no banco passa a ter status REMOVIDA_PELO_LIDER
    task_db = db_session.query(Task).filter(Task.id == task_id).first()
    assert task_db.status == "REMOVIDA_PELO_LIDER"
    assert task_db.removida_por == lider.id


# ── 3. Testes de Integração — Ciclo de Vida de Weeklies (Fase 3) ──


@patch("app.weeklies.service.validar_janela_submissao")
@patch(
    "app.weeklies.service.obter_semana_referencia",
    return_value=date(2026, 10, 5),
)
def test_weeklies_fluxo_completo_fase_3(
    mock_semana, mock_validar, client, db_session
):
    """
    Testa o ciclo de vida completo da Weekly (Fase 3):
    1. Obter ou criar weekly atual (/me/atual)
    2. Adicionar task existente
    3. Adicionar task inline
    4. Atualizar conclusão e impedimento em uma task
    5. Remover task da weekly
    6. Enviar weekly (RASCUNHO -> ENVIADA)
    7. Listar minhas weeklies com contadores (/me)
    8. Consultar detalhes da weekly (/weeklies/{id})
    """
    membro, headers = _criar_e_logar(
        client, db_session, "weeklymember@teste.com", "99010"
    )
    _vincular_setor(db_session, membro.id, TestID.SETOR_TESTE, "membro")

    # 1. Obter/Criar weekly da semana atual
    res_atual = client.get(
        f"/weeklies/me/atual?setor_id={TestID.SETOR_TESTE}",
        headers=headers,
    )
    assert res_atual.status_code == 200
    weekly = res_atual.json()
    weekly_id = weekly["id"]
    assert weekly["status"] == "RASCUNHO"
    assert weekly["semana_referencia"] == "2026-10-05"
    assert len(weekly["tasks"]) == 0

    # 2. Criar uma task avulsa primeiro
    res_task = client.post(
        "/tasks",
        headers=headers,
        json={
            "setor_id": str(TestID.SETOR_TESTE),
            "titulo": "Modelagem de dados",
        },
    )
    task1_id = res_task.json()["id"]

    # Adicionar task existente à weekly
    res_add1 = client.post(
        f"/weeklies/{weekly_id}/tasks",
        headers=headers,
        json={"task_id": task1_id},
    )
    assert res_add1.status_code == 201
    wt1 = res_add1.json()
    assert wt1["task_id"] == task1_id
    assert wt1["titulo"] == "Modelagem de dados"
    assert wt1["concluida"] is False
    assert wt1["origem"] == "NOVA"

    # 3. Adicionar task inline à weekly (cria a Task e a associa diretamente)
    res_add2 = client.post(
        f"/weeklies/{weekly_id}/tasks",
        headers=headers,
        json={
            "titulo": "Desenvolver testes automatizados",
            "descricao": "Cobrir fluxos de sucesso e falha",
        },
    )
    assert res_add2.status_code == 201
    wt2 = res_add2.json()
    wt2_id = wt2["id"]
    assert wt2["titulo"] == "Desenvolver testes automatizados"
    assert wt2["concluida"] is False

    # 4. Atualizar WeeklyTask: marcar wt1 como concluída e wt2 com impedimento
    res_up1 = client.patch(
        f"/weeklies/{weekly_id}/tasks/{wt1['id']}",
        headers=headers,
        json={"concluida": True},
    )
    assert res_up1.status_code == 200
    assert res_up1.json()["concluida"] is True

    res_up2 = client.patch(
        f"/weeklies/{weekly_id}/tasks/{wt2_id}",
        headers=headers,
        json={"impedimento": "Aguardando liberação de credenciais"},
    )
    assert res_up2.status_code == 200
    assert res_up2.json()["impedimento"] == "Aguardando liberação de credenciais"

    # 5. Adicionar uma terceira task para depois remover
    res_add3 = client.post(
        f"/weeklies/{weekly_id}/tasks",
        headers=headers,
        json={"titulo": "Tarefa temporária"},
    )
    wt3_id = res_add3.json()["id"]

    # Remover a terceira task da weekly
    res_del_wt = client.delete(
        f"/weeklies/{weekly_id}/tasks/{wt3_id}",
        headers=headers,
    )
    assert res_del_wt.status_code == 200

    # 6. Enviar a weekly (RASCUNHO -> ENVIADA)
    res_enviar = client.patch(
        f"/weeklies/{weekly_id}/enviar",
        headers=headers,
    )
    assert res_enviar.status_code == 200
    assert res_enviar.json()["status"] == "ENVIADA"
    assert res_enviar.json()["enviada_em"] is not None

    # 7. Listar minhas weeklies (/me) e validar os contadores
    res_minhas = client.get("/weeklies/me", headers=headers)
    assert res_minhas.status_code == 200
    lista = res_minhas.json()
    assert lista["total"] == 1
    item_resumo = lista["weeklies"][0]
    assert item_resumo["id"] == weekly_id
    assert item_resumo["status"] == "ENVIADA"
    assert item_resumo["total_tasks"] == 2
    assert item_resumo["total_concluidas"] == 1
    assert item_resumo["total_impedimentos"] == 1

    # 8. Detalhes da weekly (/weeklies/{id})
    res_detalhes = client.get(f"/weeklies/{weekly_id}", headers=headers)
    assert res_detalhes.status_code == 200
    assert len(res_detalhes.json()["tasks"]) == 2


def test_weeklies_bloqueio_fora_da_janela(client, db_session):
    """Garante que operações de escrita de weekly falham quando fora da janela."""
    membro, headers = _criar_e_logar(
        client, db_session, "janelateste@teste.com", "99020"
    )
    _vincular_setor(db_session, membro.id, TestID.SETOR_TESTE, "membro")

    # Simular momento fora da janela (Terça-feira 12h00)
    terca_fora = datetime(2026, 10, 6, 12, 0, 0, tzinfo=ZoneInfo("America/Fortaleza"))
    with patch(
        "app.weeklies.timezone_utils.get_now_fortaleza",
        return_value=terca_fora,
    ):
        # Tentativa de criar weekly via POST /weeklies
        res = client.post(
            "/weeklies",
            headers=headers,
            json={"setor_id": str(TestID.SETOR_TESTE)},
        )
        assert res.status_code == 400
        assert "Fora da janela de submissão" in res.json()["detail"]


def test_weeklies_protecao_idor_e_setor(client, db_session):
    """Garante isolamento entre membros e setores na adição de tasks e visualização."""
    user1, headers1 = _criar_e_logar(
        client, db_session, "membro1@teste.com", "99031"
    )
    user2, headers2 = _criar_e_logar(
        client, db_session, "membro2@teste.com", "99032"
    )
    _vincular_setor(db_session, user1.id, TestID.SETOR_TESTE, "membro")
    _vincular_setor(db_session, user2.id, TestID.SETOR_TESTE, "membro")

    # Criar outro setor
    outro_setor = Sector(nome="Setor Secundário")
    db_session.add(outro_setor)
    db_session.commit()
    db_session.refresh(outro_setor)
    _vincular_setor(db_session, user1.id, outro_setor.id, "membro")

    with patch("app.weeklies.service.validar_janela_submissao"):
        # Weekly do user1 no setor padrão
        weekly1 = Weekly(
            usuario_id=user1.id,
            setor_id=TestID.SETOR_TESTE,
            semana_referencia=date(2026, 10, 5),
            status="RASCUNHO",
        )
        db_session.add(weekly1)
        db_session.commit()
        db_session.refresh(weekly1)

        # Task pertencente a user2
        task_user2 = Task(
            usuario_id=user2.id,
            setor_id=TestID.SETOR_TESTE,
            titulo="Task privada do user2",
        )
        db_session.add(task_user2)

        # Task do user1 em OUTRO setor
        task_outro_setor = Task(
            usuario_id=user1.id,
            setor_id=outro_setor.id,
            titulo="Task de outro setor",
        )
        db_session.add(task_outro_setor)
        db_session.commit()

        # 1. User1 tenta adicionar a task de User2 à sua weekly -> 403 Forbidden
        res_idor = client.post(
            f"/weeklies/{weekly1.id}/tasks",
            headers=headers1,
            json={"task_id": str(task_user2.id)},
        )
        assert res_idor.status_code == 403

        # 2. User1 tenta adicionar task de outro setor à sua weekly deste setor -> 400 Bad Request
        res_setor_invalido = client.post(
            f"/weeklies/{weekly1.id}/tasks",
            headers=headers1,
            json={"task_id": str(task_outro_setor.id)},
        )
        assert res_setor_invalido.status_code == 400
        assert "pertence a um setor diferente" in res_setor_invalido.json()["detail"]

        # 3. User2 tenta visualizar a weekly do User1 -> 403 Forbidden
        res_view_outro = client.get(
            f"/weeklies/{weekly1.id}",
            headers=headers2,
        )
        assert res_view_outro.status_code == 403


# ── 4. Testes de Integração — Avaliação de Weeklies (Fase 4) ──


def test_weeklies_fase_4_avaliacao(client, db_session):
    user, headers_user = _criar_e_logar(
        client, db_session, "membro_aval@teste.com", "99041"
    )
    lider, headers_lider = _criar_e_logar(
        client, db_session, "lider_aval@teste.com", "99042"
    )
    _vincular_setor(db_session, user.id, TestID.SETOR_TESTE, "membro")
    _vincular_setor(db_session, lider.id, TestID.SETOR_TESTE, "lider")

    with patch("app.weeklies.service.validar_janela_submissao"):
        # Criar weekly e enviar
        weekly = Weekly(
            usuario_id=user.id,
            setor_id=TestID.SETOR_TESTE,
            semana_referencia=date(2026, 10, 5),
            status="ENVIADA",
            enviada_em=datetime.now(timezone.utc),
        )
        db_session.add(weekly)
        db_session.commit()
        db_session.refresh(weekly)

        # 1. Membro tenta avaliar a própria weekly -> 403
        res_aval_membro = client.patch(
            f"/weeklies/{weekly.id}/avaliar",
            headers=headers_user,
            json={"status": "APROVADA"},
        )
        assert res_aval_membro.status_code == 403

        # 2. Líder tenta rejeitar sem observação -> 400
        res_aval_rej_sem_obs = client.patch(
            f"/weeklies/{weekly.id}/avaliar",
            headers=headers_lider,
            json={"status": "REJEITADA"},
        )
        assert res_aval_rej_sem_obs.status_code == 400

        # 3. Líder rejeita com observação -> 200
        res_aval_rej = client.patch(
            f"/weeklies/{weekly.id}/avaliar",
            headers=headers_lider,
            json={"status": "REJEITADA", "observacao_lider": "Faltou a tarefa X"},
        )
        assert res_aval_rej.status_code == 200
        assert res_aval_rej.json()["status"] == "REJEITADA"

        # 4. Líder lista weeklies do setor
        res_list_setor = client.get(
            f"/weeklies/setor/{TestID.SETOR_TESTE}",
            headers=headers_lider,
        )
        assert res_list_setor.status_code == 200
        weeklies_setor = res_list_setor.json()["weeklies"]
        assert len(weeklies_setor) >= 1
        assert any(w["id"] == str(weekly.id) for w in weeklies_setor)

