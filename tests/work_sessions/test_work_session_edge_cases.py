"""Casos de borda — módulo de Controle de Horas."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from app.config import settings
from app.core.constants import TestID
from app.models.pause import Pause
from app.models.sector import Sector
from app.models.work_session import (
    MotivoEncerramento,
    WorkSession,
    WorkSessionStatus,
)
from app.work_sessions import service as work_session_service
from app.work_sessions.service import svc_process_expired_sessions

from .helpers import _adicionar_ao_setor, _buscar_sessao, _headers


def _congelar_tempo(monkeypatch, instante: datetime) -> None:
    """Fixa datetime.now() usado pelo service em um instante conhecido."""

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return instante.replace(tzinfo=None)
            return instante.astimezone(tz)

    monkeypatch.setattr(
        work_session_service,
        "datetime",
        FrozenDateTime,
    )


# ── Prorrogação: limites exatos ──────────────────────────────


def test_continue_exatamente_no_inicio_da_janela(
    client,
    db_session,
    sessao_ativa,
    monkeypatch,
):
    _usuario, token, sessao = sessao_ativa

    agora = datetime(2026, 10, 4, 15, 0, tzinfo=timezone.utc)
    _congelar_tempo(monkeypatch, agora)

    work_session = _buscar_sessao(
        db_session,
        sessao["id"],
    )
    work_session.expiracao = agora + timedelta(
        minutes=settings.WORK_SESSION_EXTENSION_WINDOW_MINUTES,
    )
    db_session.commit()

    response = client.patch(
        f"/work-sessions/{sessao['id']}/continue",
        headers=_headers(token),
    )

    assert response.status_code == 200

    db_session.refresh(work_session)

    assert work_session.expiracao == (
        agora
        + timedelta(
            minutes=settings.WORK_SESSION_EXTENSION_WINDOW_MINUTES,
            hours=settings.WORK_SESSION_EXTENSION_HOURS,
        )
    )


def test_continue_um_segundo_antes_da_janela(
    client,
    db_session,
    sessao_ativa,
    monkeypatch,
):
    _usuario, token, sessao = sessao_ativa

    agora = datetime(2026, 10, 4, 15, 0, tzinfo=timezone.utc)
    _congelar_tempo(monkeypatch, agora)

    work_session = _buscar_sessao(
        db_session,
        sessao["id"],
    )
    expiracao_original = agora + timedelta(
        minutes=settings.WORK_SESSION_EXTENSION_WINDOW_MINUTES,
        seconds=1,
    )
    work_session.expiracao = expiracao_original
    db_session.commit()

    response = client.patch(
        f"/work-sessions/{sessao['id']}/continue",
        headers=_headers(token),
    )

    assert response.status_code == 409

    db_session.refresh(work_session)
    assert work_session.expiracao == expiracao_original


def test_continue_exatamente_na_expiracao(
    client,
    db_session,
    sessao_ativa,
    monkeypatch,
):
    _usuario, token, sessao = sessao_ativa

    agora = datetime(2026, 10, 4, 15, 0, tzinfo=timezone.utc)
    _congelar_tempo(monkeypatch, agora)

    work_session = _buscar_sessao(
        db_session,
        sessao["id"],
    )
    work_session.expiracao = agora
    db_session.commit()

    response = client.patch(
        f"/work-sessions/{sessao['id']}/continue",
        headers=_headers(token),
    )

    assert response.status_code == 409

    db_session.refresh(work_session)
    assert work_session.expiracao == agora


# ── Expiração automática / scheduler ─────────────────────────


def test_scheduler_expira_sessao_em_pausa(
    client,
    db_session,
    sessao_ativa,
    monkeypatch,
):
    _usuario, token, sessao = sessao_ativa

    pause_response = client.post(
        f"/work-sessions/{sessao['id']}/pauses",
        headers=_headers(token),
    )

    assert pause_response.status_code == 201

    pausa_id = UUID(pause_response.json()["id"])
    work_session = _buscar_sessao(
        db_session,
        sessao["id"],
    )
    pausa = (
        db_session.query(Pause)
        .filter(Pause.id == pausa_id)
        .first()
    )

    expiracao = datetime(
        2026,
        10,
        4,
        15,
        0,
        tzinfo=timezone.utc,
    )

    work_session.entrada = expiracao - timedelta(hours=2)
    work_session.expiracao = expiracao
    work_session.status = WorkSessionStatus.EM_PAUSA
    pausa.inicio = expiracao - timedelta(minutes=30)

    db_session.commit()

    _congelar_tempo(
        monkeypatch,
        expiracao + timedelta(minutes=5),
    )

    svc_process_expired_sessions(db_session)

    db_session.refresh(work_session)
    db_session.refresh(pausa)

    assert work_session.status == WorkSessionStatus.EXPIRADA_SISTEMA
    assert (
        work_session.motivo_encerramento
        == MotivoEncerramento.LIMITE_ATINGIDO
    )
    assert work_session.saida == expiracao
    assert pausa.fim == expiracao


def test_scheduler_e_idempotente(
    db_session,
    sessao_ativa,
    monkeypatch,
):
    _usuario, _token, sessao = sessao_ativa

    expiracao = datetime(
        2026,
        10,
        4,
        15,
        0,
        tzinfo=timezone.utc,
    )

    work_session = _buscar_sessao(
        db_session,
        sessao["id"],
    )
    work_session.entrada = expiracao - timedelta(hours=2)
    work_session.expiracao = expiracao
    db_session.commit()

    _congelar_tempo(
        monkeypatch,
        expiracao + timedelta(minutes=5),
    )

    svc_process_expired_sessions(db_session)

    db_session.refresh(work_session)

    primeira_saida = work_session.saida
    primeiro_status = work_session.status
    primeiro_motivo = work_session.motivo_encerramento

    svc_process_expired_sessions(db_session)

    db_session.refresh(work_session)

    assert work_session.saida == primeira_saida
    assert work_session.status == primeiro_status
    assert work_session.motivo_encerramento == primeiro_motivo
    assert work_session.saida == expiracao
    assert work_session.status == WorkSessionStatus.EXPIRADA_SISTEMA


# ── Papéis globais + papel no setor ─────────────────────────


def test_admin_lider_continua_sem_poder_bater_ponto(
    client,
    db_session,
    admin_logado,
):
    admin, token = admin_logado

    _adicionar_ao_setor(
        db_session,
        admin,
        "lider",
    )

    response = client.post(
        "/work-sessions",
        json={
            "setor_id": str(TestID.SETOR_TESTE),
        },
        headers=_headers(token),
    )

    assert response.status_code == 403

    sessao = (
        db_session.query(WorkSession)
        .filter(WorkSession.usuario_id == admin.id)
        .first()
    )

    assert sessao is None


def test_admin_lider_continua_podendo_consultar_sessoes(
    client,
    db_session,
    sessao_ativa,
    admin_logado,
):
    _usuario, _token_usuario, sessao = sessao_ativa
    admin, token_admin = admin_logado

    _adicionar_ao_setor(
        db_session,
        admin,
        "lider",
    )

    response = client.get(
        f"/work-sessions/{sessao['id']}",
        headers=_headers(token_admin),
    )

    assert response.status_code == 200
    assert response.json()["id"] == sessao["id"]


def test_lider_nao_pode_consultar_sessao_de_outro_setor(
    client,
    db_session,
    sessao_ativa,
    lider_logado,
):
    usuario, _token_usuario, sessao = sessao_ativa
    _lider, token_lider = lider_logado

    outro_setor = Sector(
        nome="Setor Edge Case",
        descricao="Setor usado em teste de permissão.",
        ativo=True,
    )
    db_session.add(outro_setor)
    db_session.commit()
    db_session.refresh(outro_setor)

    work_session = _buscar_sessao(
        db_session,
        sessao["id"],
    )
    work_session.setor_id = outro_setor.id
    db_session.commit()

    response = client.get(
        f"/work-sessions/{sessao['id']}",
        headers=_headers(token_lider),
    )

    assert response.status_code == 403

    db_session.refresh(work_session)
    assert work_session.usuario_id == usuario.id
    assert work_session.setor_id == outro_setor.id


# ── Filtros de período ───────────────────────────────────────


@pytest.mark.parametrize(
    "params",
    [
        {"inicio": "2026-10-04T10:00:00+00:00"},
        {"fim": "2026-10-04T12:00:00+00:00"},
    ],
)
def test_listagem_exige_inicio_e_fim_juntos(
    client,
    usuario_logado,
    params,
):
    _usuario, token = usuario_logado

    response = client.get(
        "/work-sessions",
        params=params,
        headers=_headers(token),
    )

    assert response.status_code == 400


@pytest.mark.parametrize(
    ("entrada", "saida", "esperado"),
    [
        (
            datetime(2026, 10, 4, 9, 0, tzinfo=timezone.utc),
            datetime(2026, 10, 4, 11, 0, tzinfo=timezone.utc),
            3600,
        ),
        (
            datetime(2026, 10, 4, 11, 0, tzinfo=timezone.utc),
            datetime(2026, 10, 4, 13, 0, tzinfo=timezone.utc),
            3600,
        ),
        (
            datetime(2026, 10, 4, 9, 0, tzinfo=timezone.utc),
            datetime(2026, 10, 4, 13, 0, tzinfo=timezone.utc),
            7200,
        ),
    ],
)
def test_summary_recorta_sessao_aos_limites_do_periodo(
    client,
    db_session,
    sessao_ativa,
    entrada,
    saida,
    esperado,
):
    _usuario, token, sessao = sessao_ativa

    work_session = _buscar_sessao(
        db_session,
        sessao["id"],
    )
    work_session.entrada = entrada
    work_session.saida = saida
    work_session.expiracao = entrada + timedelta(hours=8)
    work_session.status = WorkSessionStatus.FINALIZADA
    work_session.motivo_encerramento = MotivoEncerramento.MANUAL
    db_session.commit()

    response = client.get(
        "/work-sessions/summary",
        params={
            "inicio": datetime(
                2026,
                10,
                4,
                10,
                0,
                tzinfo=timezone.utc,
            ).isoformat(),
            "fim": datetime(
                2026,
                10,
                4,
                12,
                0,
                tzinfo=timezone.utc,
            ).isoformat(),
        },
        headers=_headers(token),
    )

    assert response.status_code == 200
    assert (
        response.json()["tempo_trabalhado_segundos"]
        == esperado
    )


@pytest.mark.parametrize(
    ("inicio_pausa", "fim_pausa"),
    [
        (
            datetime(2026, 10, 4, 9, 30, tzinfo=timezone.utc),
            datetime(2026, 10, 4, 10, 30, tzinfo=timezone.utc),
        ),
        (
            datetime(2026, 10, 4, 11, 30, tzinfo=timezone.utc),
            datetime(2026, 10, 4, 12, 30, tzinfo=timezone.utc),
        ),
    ],
)
def test_summary_recorta_pausa_aos_limites_do_periodo(
    client,
    db_session,
    sessao_ativa,
    inicio_pausa,
    fim_pausa,
):
    _usuario, token, sessao = sessao_ativa

    work_session = _buscar_sessao(
        db_session,
        sessao["id"],
    )
    work_session.entrada = datetime(
        2026,
        10,
        4,
        9,
        0,
        tzinfo=timezone.utc,
    )
    work_session.saida = datetime(
        2026,
        10,
        4,
        13,
        0,
        tzinfo=timezone.utc,
    )
    work_session.expiracao = datetime(
        2026,
        10,
        4,
        17,
        0,
        tzinfo=timezone.utc,
    )
    work_session.status = WorkSessionStatus.FINALIZADA
    work_session.motivo_encerramento = MotivoEncerramento.MANUAL

    pausa = Pause(
        sessao_trabalho_id=work_session.id,
        inicio=inicio_pausa,
        fim=fim_pausa,
    )

    db_session.add(pausa)
    db_session.commit()

    response = client.get(
        "/work-sessions/summary",
        params={
            "inicio": datetime(
                2026,
                10,
                4,
                10,
                0,
                tzinfo=timezone.utc,
            ).isoformat(),
            "fim": datetime(
                2026,
                10,
                4,
                12,
                0,
                tzinfo=timezone.utc,
            ).isoformat(),
        },
        headers=_headers(token),
    )

    assert response.status_code == 200

    # 2 horas no período - 30 minutos de pausa = 1h30.
    assert (
        response.json()["tempo_trabalhado_segundos"]
        == 5400
    )


# ── Estado do banco após erro ────────────────────────────────


def test_segunda_pausa_rejeitada_nao_cria_registro_extra(
    client,
    db_session,
    sessao_ativa,
):
    _usuario, token, sessao = sessao_ativa

    primeira = client.post(
        f"/work-sessions/{sessao['id']}/pauses",
        headers=_headers(token),
    )

    assert primeira.status_code == 201

    quantidade_antes = (
        db_session.query(Pause)
        .filter(
            Pause.sessao_trabalho_id
            == UUID(sessao["id"])
        )
        .count()
    )

    segunda = client.post(
        f"/work-sessions/{sessao['id']}/pauses",
        headers=_headers(token),
    )

    assert segunda.status_code == 409

    quantidade_depois = (
        db_session.query(Pause)
        .filter(
            Pause.sessao_trabalho_id
            == UUID(sessao["id"])
        )
        .count()
    )

    assert quantidade_antes == 1
    assert quantidade_depois == 1


# ── Timeline ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("agrupamento", "inicio", "fim", "qtd_intervalos"),
    [
        (
            "semana",
            "2026-10-07T12:00:00-03:00",
            "2026-10-15T12:00:00-03:00",
            2,
        ),
        (
            "mes",
            "2026-10-15T12:00:00-03:00",
            "2026-11-10T12:00:00-03:00",
            2,
        ),
    ],
)
def test_metrics_timeline_sem_horas_retorna_intervalos_zerados(
    client,
    admin_logado,
    agrupamento,
    inicio,
    fim,
    qtd_intervalos,
):
    _admin, token = admin_logado

    response = client.get(
        "/work-sessions/metrics/timeline",
        params={
            "inicio": inicio,
            "fim": fim,
            "agrupamento": agrupamento,
        },
        headers=_headers(token),
    )

    assert response.status_code == 200

    data = response.json()

    assert data["agrupamento"] == agrupamento
    assert data["fuso"] == "America/Sao_Paulo"
    assert len(data["intervalos"]) == qtd_intervalos

    for intervalo in data["intervalos"]:
        assert intervalo["tempo_trabalhado_segundos"] == 0
        assert intervalo["tempo_pausado_segundos"] == 0


def test_metrics_timeline_semana_quebra_na_segunda_feira(
    client,
    admin_logado,
):
    _admin, token = admin_logado

    response = client.get(
        "/work-sessions/metrics/timeline",
        params={
            "inicio": "2026-10-07T12:00:00-03:00",
            "fim": "2026-10-15T12:00:00-03:00",
            "agrupamento": "semana",
        },
        headers=_headers(token),
    )

    assert response.status_code == 200

    intervalos = response.json()["intervalos"]

    assert intervalos[0]["inicio"].startswith(
        "2026-10-07T12:00:00"
    )
    assert intervalos[0]["fim"].startswith(
        "2026-10-12T00:00:00"
    )
    assert intervalos[1]["inicio"].startswith(
        "2026-10-12T00:00:00"
    )
    assert intervalos[1]["fim"].startswith(
        "2026-10-15T12:00:00"
    )


def test_metrics_timeline_mes_quebra_no_primeiro_dia(
    client,
    admin_logado,
):
    _admin, token = admin_logado

    response = client.get(
        "/work-sessions/metrics/timeline",
        params={
            "inicio": "2026-10-15T12:00:00-03:00",
            "fim": "2026-11-10T12:00:00-03:00",
            "agrupamento": "mes",
        },
        headers=_headers(token),
    )

    assert response.status_code == 200

    intervalos = response.json()["intervalos"]

    assert intervalos[0]["inicio"].startswith(
        "2026-10-15T12:00:00"
    )
    assert intervalos[0]["fim"].startswith(
        "2026-11-01T00:00:00"
    )
    assert intervalos[1]["inicio"].startswith(
        "2026-11-01T00:00:00"
    )
    assert intervalos[1]["fim"].startswith(
        "2026-11-10T12:00:00"
    )


# ── Paginação ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "params",
    [
        {"pagina": 0},
        {"limite": 101},
    ],
)
def test_listagem_rejeita_paginacao_fora_dos_limites(
    client,
    usuario_logado,
    params,
):
    _usuario, token = usuario_logado

    response = client.get(
        "/work-sessions",
        params=params,
        headers=_headers(token),
    )

    assert response.status_code == 422


def test_listagem_pagina_sem_registros_retorna_lista_vazia(
    client,
    usuario_logado,
):
    _usuario, token = usuario_logado

    response = client.get(
        "/work-sessions",
        params={
            "pagina": 999,
            "limite": 20,
        },
        headers=_headers(token),
    )

    assert response.status_code == 200

    data = response.json()

    assert data["sessoes"] == []
    assert data["pagina"] == 999
    assert data["limite"] == 20
