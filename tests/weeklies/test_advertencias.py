"""Testes para a Fase 7: Sistema de Advertências (WeeklyWarning).

Cenários cobertos:
1. Regra de ausências consecutivas:
   - 1 semana sem envio: nenhuma advertência gerada.
   - 2 semanas consecutivas sem envio: gera 1a_ADVERTENCIA.
   - 3 semanas consecutivas sem envio: gera 2a_ADVERTENCIA.
   - 4 semanas consecutivas sem envio: gera DESLIGAMENTO.
2. Reset do contador consecutivo: envio na semana intermediária reseta o contador.
3. Respeito à data de ingresso: semanas anteriores a data_ingresso não são contabilizadas.
4. Idempotência: reprocessar ausências na mesma semana não gera advertências duplicadas.
5. Endpoints de consulta:
   - GET /advertencias/setor/{setor_id} (líder/admin: 200, membro não-líder: 403).
   - GET /advertencias/me (membro consulta suas advertências com paginação).
"""

from datetime import date
from types import SimpleNamespace
from uuid import uuid4

from app.core.constants import RoleID, StatusID, TestID
from app.core.security import criar_token_acesso
from app.models.sector_user import SectorUser
from app.models.user import User
from app.models.weekly import Weekly
from app.models.weekly_warning import WeeklyWarning
from app.weeklies.service import (
    contar_semanas_consecutivas_sem_envio,
    svc_processar_advertencias_ausencias,
)

W1 = date(2026, 9, 14)
W2 = date(2026, 9, 21)
W3 = date(2026, 9, 28)
W4 = date(2026, 10, 5)


def _criar_cenario_usuario(
    db_session,
    nome: str,
    matricula: str,
    papel: str = "membro",
    data_ingresso: date = W1,
    global_role=RoleID.USUARIO,
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

    assoc = SectorUser(
        usuario_id=user.id,
        setor_id=TestID.SETOR_TESTE,
        papel=papel,
        data_ingresso=data_ingresso,
    )
    db_session.add(assoc)
    db_session.commit()

    token = criar_token_acesso({"sub": str(user.id)})
    headers = {"Authorization": f"Bearer {token}"}

    return SimpleNamespace(user=user, assoc=assoc, headers=headers)


def test_contar_semanas_consecutivas_sem_envio(db_session):
    """Testa a lógica de retrocesso consecutivo na contagem de ausências."""
    cenario = _criar_cenario_usuario(db_session, "Membro Teste Contagem", f"C{uuid4().hex[:6]}")
    u_id = cenario.user.id
    s_id = TestID.SETOR_TESTE
    data_ingresso = cenario.user.data_ingresso

    # Sem nenhuma weekly criada: 1 semana retrocedendo a partir de W1
    assert (
        contar_semanas_consecutivas_sem_envio(
            db_session, u_id, s_id, W1, data_ingresso=data_ingresso
        )
        == 1
    )
    # 2 semanas retrocedendo a partir de W2
    assert (
        contar_semanas_consecutivas_sem_envio(
            db_session, u_id, s_id, W2, data_ingresso=data_ingresso
        )
        == 2
    )

    # Cria uma weekly enviada em W2
    w2 = Weekly(usuario_id=u_id, setor_id=s_id, semana_referencia=W2, status="ENVIADA")
    db_session.add(w2)
    db_session.commit()

    # Em W2: enviou, então semanas sem envio a partir de W2 é 0
    assert (
        contar_semanas_consecutivas_sem_envio(
            db_session, u_id, s_id, W2, data_ingresso=data_ingresso
        )
        == 0
    )

    # Em W3: não enviou W3, mas enviou W2 -> consecutivas = 1 (resetou!)
    assert (
        contar_semanas_consecutivas_sem_envio(
            db_session, u_id, s_id, W3, data_ingresso=data_ingresso
        )
        == 1
    )


def test_respeito_data_ingresso_na_contagem(db_session):
    """Semanas anteriores à data de ingresso do membro não devem ser contadas como falta."""
    # Membro ingressou em W2
    cenario = _criar_cenario_usuario(
        db_session, "Membro Recente", f"R{uuid4().hex[:6]}", data_ingresso=W2
    )
    u_id = cenario.user.id
    s_id = TestID.SETOR_TESTE

    # Avaliando em W3 (não enviou W3 nem W2): deve contar no máximo até W2
    # W1 é anterior a data_ingresso (W2), logo não é contabilizada
    consecutivas = contar_semanas_consecutivas_sem_envio(
        db_session, u_id, s_id, W3, data_ingresso=W2
    )
    assert consecutivas == 2  # W3 e W2, mas não W1


def test_geracao_advertencias_regua_completa(db_session):
    """Testa a geração progressiva: 2 semanas (1a_ADV), 3 semanas (2a_ADV), 4 semanas (DESLIGAMENTO)."""
    membro = _criar_cenario_usuario(db_session, "Membro Regua", f"REG_{uuid4().hex[:6]}")
    u_id = membro.user.id

    # 1. Semana 1 (W1): 1ª ausência -> nenhuma advertência emitida
    res1 = svc_processar_advertencias_ausencias(db_session, semana_referencia=W1)
    assert res1["advertencias_geradas"] == 0
    advs_membro_1 = db_session.query(WeeklyWarning).filter(WeeklyWarning.usuario_id == u_id).all()
    assert len(advs_membro_1) == 0

    # 2. Semana 2 (W2): 2ª ausência consecutiva -> 1a_ADVERTENCIA
    res2 = svc_processar_advertencias_ausencias(db_session, semana_referencia=W2)
    assert res2["advertencias_geradas"] >= 1
    adv2 = db_session.query(WeeklyWarning).filter(
        WeeklyWarning.usuario_id == u_id, WeeklyWarning.semana_referencia == W2
    ).first()
    assert adv2 is not None
    assert adv2.tipo == "1a_ADVERTENCIA"
    assert adv2.semanas_ausentes == 2

    # 3. Semana 3 (W3): 3ª ausência consecutiva -> 2a_ADVERTENCIA
    res3 = svc_processar_advertencias_ausencias(db_session, semana_referencia=W3)
    assert res3["advertencias_geradas"] >= 1
    adv3 = db_session.query(WeeklyWarning).filter(
        WeeklyWarning.usuario_id == u_id, WeeklyWarning.semana_referencia == W3
    ).first()
    assert adv3 is not None
    assert adv3.tipo == "2a_ADVERTENCIA"
    assert adv3.semanas_ausentes == 3

    # 4. Semana 4 (W4): 4ª ausência consecutiva -> DESLIGAMENTO
    res4 = svc_processar_advertencias_ausencias(db_session, semana_referencia=W4)
    assert res4["advertencias_geradas"] >= 1
    adv4 = db_session.query(WeeklyWarning).filter(
        WeeklyWarning.usuario_id == u_id, WeeklyWarning.semana_referencia == W4
    ).first()
    assert adv4 is not None
    assert adv4.tipo == "DESLIGAMENTO"
    assert adv4.semanas_ausentes == 4


def test_idempotencia_processamento_advertencias(db_session):
    """Executar o processamento duas vezes para a mesma semana não duplica a advertência."""
    membro = _criar_cenario_usuario(db_session, "Membro Idempotente", f"IDEMP_{uuid4().hex[:6]}")
    u_id = membro.user.id

    # Executa a primeira vez para W2 (2ª ausência)
    res_a = svc_processar_advertencias_ausencias(db_session, semana_referencia=W2)
    assert res_a["advertencias_geradas"] >= 1
    count_inicial = db_session.query(WeeklyWarning).filter(
        WeeklyWarning.usuario_id == u_id, WeeklyWarning.semana_referencia == W2
    ).count()
    assert count_inicial == 1

    # Executa novamente
    res_b = svc_processar_advertencias_ausencias(db_session, semana_referencia=W2)
    assert res_b["advertencias_geradas"] == 0
    count_final = db_session.query(WeeklyWarning).filter(
        WeeklyWarning.usuario_id == u_id, WeeklyWarning.semana_referencia == W2
    ).count()
    assert count_final == 1


def test_reset_contador_apos_envio(db_session):
    """Garante que ao enviar a weekly na semana 3, o contador de ausências consecutivas reseta."""
    membro = _criar_cenario_usuario(db_session, "Membro Reset", f"RST_{uuid4().hex[:6]}")
    u_id = membro.user.id
    s_id = TestID.SETOR_TESTE

    # Falta em W1 e W2: gera 1a_ADVERTENCIA em W2
    svc_processar_advertencias_ausencias(db_session, semana_referencia=W2)

    # Em W3 o membro envia a weekly
    w3 = Weekly(usuario_id=u_id, setor_id=s_id, semana_referencia=W3, status="ENVIADA")
    db_session.add(w3)
    db_session.commit()

    # Em W4 o membro falta novamente
    svc_processar_advertencias_ausencias(db_session, semana_referencia=W4)

    # Em W4, como W3 foi enviada, o membro tem apenas 1 semana de ausência consecutiva.
    # Nenhuma advertência deve ter sido gerada em W4!
    adv_w4 = db_session.query(WeeklyWarning).filter(
        WeeklyWarning.usuario_id == u_id, WeeklyWarning.semana_referencia == W4
    ).first()
    assert adv_w4 is None


def test_api_list_sector_warnings_permissoes(client, db_session):
    """Testa o endpoint GET /advertencias/setor/{setor_id}."""
    membro = _criar_cenario_usuario(db_session, "Membro Comum", f"M_{uuid4().hex[:6]}", papel="membro")
    lider = _criar_cenario_usuario(db_session, "Lider Setor", f"L_{uuid4().hex[:6]}", papel="lider")

    # Cria uma advertência para o membro
    adv = WeeklyWarning(
        usuario_id=membro.user.id,
        setor_id=TestID.SETOR_TESTE,
        tipo="1a_ADVERTENCIA",
        semana_referencia=W2,
        semanas_ausentes=2,
    )
    db_session.add(adv)
    db_session.commit()

    # 1. Líder do setor acessa: sucesso (200)
    resp_lider = client.get(
        f"/advertencias/setor/{TestID.SETOR_TESTE}",
        headers=lider.headers,
    )
    assert resp_lider.status_code == 200
    dados = resp_lider.json()
    assert dados["total"] >= 1
    assert any(a["id"] == str(adv.id) for a in dados["advertencias"])

    # 2. Membro comum acessa: 403 Forbidden
    resp_membro = client.get(
        f"/advertencias/setor/{TestID.SETOR_TESTE}",
        headers=membro.headers,
    )
    assert resp_membro.status_code == 403
    assert "Você não tem permissão" in resp_membro.json()["detail"]


def test_api_list_my_warnings(client, db_session):
    """Testa o endpoint GET /advertencias/me."""
    membro = _criar_cenario_usuario(db_session, "Membro Me", f"ME_{uuid4().hex[:6]}", papel="membro")

    adv = WeeklyWarning(
        usuario_id=membro.user.id,
        setor_id=TestID.SETOR_TESTE,
        tipo="2a_ADVERTENCIA",
        semana_referencia=W3,
        semanas_ausentes=3,
    )
    db_session.add(adv)
    db_session.commit()

    resp = client.get("/advertencias/me", headers=membro.headers)
    assert resp.status_code == 200
    dados = resp.json()
    assert dados["total"] == 1
    assert dados["advertencias"][0]["tipo"] == "2a_ADVERTENCIA"
    assert dados["advertencias"][0]["semanas_ausentes"] == 3
    assert dados["advertencias"][0]["usuario_id"] == str(membro.user.id)


def test_usuario_antigo_recem_vinculado_nao_recebe_desligamento(db_session):
    """Garante que um usuário antigo (ex: data_ingresso em 2024) recém-vinculado a um setor
    não receba falsas ausências retroativas nem ocorrência indevida de DESLIGAMENTO.
    """
    # 1. Usuário com 2 anos de casa (2024-01-01), mas recém-vinculado ao setor numa quarta-feira (2026-10-07)
    antigo = _criar_cenario_usuario(
        db_session,
        "Usuário Antigo Recém Vinculado",
        f"ANT_{uuid4().hex[:6]}",
        data_ingresso=date(2024, 1, 1),
    )
    # Atualiza o vínculo do setor especificamente para quarta-feira 2026-10-07
    antigo.assoc.data_ingresso = date(2026, 10, 7)
    db_session.commit()

    u_id = antigo.user.id
    s_id = TestID.SETOR_TESTE

    # 2. Avalia a semana que fechou na segunda-feira anterior (2026-10-05):
    # Como ele entrou no setor na quarta-feira (após o fechamento), não possui obrigação para 2026-10-05.
    res_ant = svc_processar_advertencias_ausencias(db_session, semana_referencia=date(2026, 10, 5))
    adv_ant = db_session.query(WeeklyWarning).filter(
        WeeklyWarning.usuario_id == u_id, WeeklyWarning.semana_referencia == date(2026, 10, 5)
    ).first()
    assert adv_ant is None
    # Também não deve figurar entre os ausentes reportados para a semana 2026-10-05
    assert not any(d["usuario_id"] == str(u_id) for d in res_ant.get("detalhes_ausentes", []))

    # 3. Na semana seguinte (2026-10-12): primeira obrigação exigível
    # Se o membro não enviar, deve acumular EXATAMENTE 1 ausência (e não 12 semanas retroativas!)
    consecutivas = contar_semanas_consecutivas_sem_envio(
        db_session,
        u_id,
        s_id,
        semana_base=date(2026, 10, 12),
        data_inicio_obrigacao=date(2026, 10, 7),
    )
    assert consecutivas == 1  # Apenas a semana 2026-10-12, parando em 2026-10-07

    # 4. Ao processar advertências para 2026-10-12, nenhuma advertência é emitida (pois precisa de 2 consecutivas)
    _res_prox = svc_processar_advertencias_ausencias(db_session, semana_referencia=date(2026, 10, 12))
    adv_prox = db_session.query(WeeklyWarning).filter(
        WeeklyWarning.usuario_id == u_id, WeeklyWarning.semana_referencia == date(2026, 10, 12)
    ).first()
    assert adv_prox is None  # Jamais DESLIGAMENTO imediato!


def test_respeito_ao_marco_de_implantacao(db_session, monkeypatch):
    """Garante que a contagem de faltas respeite o marco oficial de implantação do módulo,
    não retroagindo para períodos anteriores ao lançamento do sistema.
    """
    from app.config import settings

    # Define marco oficial de implantação do módulo: 2026-10-05
    monkeypatch.setattr(settings, "WEEKLY_MARCO_IMPLANTACAO", date(2026, 10, 5))

    membro = _criar_cenario_usuario(
        db_session,
        "Membro Pré Implantação",
        f"PRE_{uuid4().hex[:6]}",
        data_ingresso=date(2024, 1, 1),
    )
    # Vínculo antigo também em 2024
    membro.assoc.data_ingresso = date(2024, 1, 1)
    db_session.commit()

    u_id = membro.user.id
    s_id = TestID.SETOR_TESTE

    # Avaliando ausência em 2026-10-12 sem envios:
    # Deve retroceder no máximo até 2026-10-05 (marco de implantação), totalizando 2 semanas (2026-10-12 e 2026-10-05)
    # e NUNCA semanas de setembro/agosto de 2026 ou 2024!
    consecutivas = contar_semanas_consecutivas_sem_envio(
        db_session,
        u_id,
        s_id,
        semana_base=date(2026, 10, 12),
        data_inicio_obrigacao=max(date(2024, 1, 1), settings.WEEKLY_MARCO_IMPLANTACAO),
    )
    assert consecutivas == 2  # 2026-10-12 e 2026-10-05


def test_administrador_em_setor_nao_recebe_advertencias(db_session):
    """
    Garante que administradores globais vinculados a setores (como membros ou líderes)
    não são incluídos na população sujeita à obrigação semanal e não recebem advertências.
    """
    admin_membro = _criar_cenario_usuario(
        db_session,
        "Admin Vinculado Como Membro",
        f"ADM_{uuid4().hex[:6]}",
        papel="membro",
        data_ingresso=W1,
        global_role=RoleID.ADMIN,
    )
    admin_id = admin_membro.user.id

    # Processa ausências para semanas consecutivas sem nenhum envio pelo admin
    svc_processar_advertencias_ausencias(db_session, semana_referencia=W2)
    svc_processar_advertencias_ausencias(db_session, semana_referencia=W3)
    svc_processar_advertencias_ausencias(db_session, semana_referencia=W4)

    # Nenhuma advertência deve ter sido gerada para o admin
    adverts = db_session.query(WeeklyWarning).filter(WeeklyWarning.usuario_id == admin_id).all()
    assert len(adverts) == 0

