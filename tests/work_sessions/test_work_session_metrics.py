"""Testes de Work Session Metrics."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.core.constants import TestID
from app.models.work_session import (
    MotivoEncerramento,
    WorkSession,
    WorkSessionStatus,
)

from .helpers import _headers


def test_metrics_summary_admin_sucesso(
    client,
    admin_logado,
):
    _admin, token = admin_logado

    inicio = datetime.now(timezone.utc) - timedelta(days=1)
    fim = datetime.now(timezone.utc) + timedelta(days=1)

    response = client.get(
        "/work-sessions/metrics/summary",
        params={
            "inicio": inicio.isoformat(),
            "fim": fim.isoformat(),
        },
        headers=_headers(token),
    )

    assert response.status_code == 200

    data = response.json()

    assert "tempo_trabalhado_segundos" in data
    assert "tempo_pausado_segundos" in data
    assert "sessoes_iniciadas" in data
    assert "usuarios_com_tempo_trabalhado" in data

def test_metrics_usuario_comum_retorna_403(
    client,
    usuario_logado,
):
    _usuario, token = usuario_logado

    inicio = datetime.now(timezone.utc) - timedelta(days=1)
    fim = datetime.now(timezone.utc) + timedelta(days=1)

    response = client.get(
        "/work-sessions/metrics/summary",
        params={
            "inicio": inicio.isoformat(),
            "fim": fim.isoformat(),
        },
        headers=_headers(token),
    )

    assert response.status_code == 403

def test_metrics_periodo_invalido(
    client,
    admin_logado,
):
    _admin, token = admin_logado

    agora = datetime.now(timezone.utc)

    response = client.get(
        "/work-sessions/metrics/summary",
        params={
            "inicio": agora.isoformat(),
            "fim": (
                agora - timedelta(hours=1)
            ).isoformat(),
        },
        headers=_headers(token),
    )

    assert response.status_code == 400

def test_metrics_users_admin_sucesso(
    client,
    admin_logado,
):
    _admin, token = admin_logado

    inicio = datetime.now(timezone.utc) - timedelta(days=1)
    fim = datetime.now(timezone.utc) + timedelta(days=1)

    response = client.get(
        "/work-sessions/metrics/users",
        params={
            "inicio": inicio.isoformat(),
            "fim": fim.isoformat(),
        },
        headers=_headers(token),
    )

    assert response.status_code == 200

    data = response.json()

    assert "usuarios" in data
    assert "total" in data
    assert data["pagina"] == 1
    assert data["limite"] == 20

def test_metrics_sectors_admin_sucesso(
    client,
    admin_logado,
):
    _admin, token = admin_logado

    inicio = datetime.now(timezone.utc) - timedelta(days=1)
    fim = datetime.now(timezone.utc) + timedelta(days=1)

    response = client.get(
        "/work-sessions/metrics/sectors",
        params={
            "inicio": inicio.isoformat(),
            "fim": fim.isoformat(),
        },
        headers=_headers(token),
    )

    assert response.status_code == 200

    data = response.json()

    assert "setores" in data
    assert "total" in data

def test_metrics_timeline_admin_sucesso(
    client,
    admin_logado,
):
    _admin, token = admin_logado

    inicio = datetime.now(timezone.utc) - timedelta(days=3)
    fim = datetime.now(timezone.utc)

    response = client.get(
        "/work-sessions/metrics/timeline",
        params={
            "inicio": inicio.isoformat(),
            "fim": fim.isoformat(),
            "agrupamento": "dia",
        },
        headers=_headers(token),
    )

    assert response.status_code == 200

    data = response.json()

    assert data["agrupamento"] == "dia"
    assert data["fuso"] == "America/Sao_Paulo"
    assert "intervalos" in data

def test_metrics_timeline_usuario_comum_retorna_403(
    client,
    usuario_logado,
):
    _usuario, token = usuario_logado

    inicio = datetime.now(timezone.utc) - timedelta(days=1)
    fim = datetime.now(timezone.utc)

    response = client.get(
        "/work-sessions/metrics/timeline",
        params={
            "inicio": inicio.isoformat(),
            "fim": fim.isoformat(),
        },
        headers=_headers(token),
    )

    assert response.status_code == 403

def test_metrics_timeline_agrupamento_invalido(
    client,
    admin_logado,
):
    _admin, token = admin_logado

    inicio = datetime.now(timezone.utc) - timedelta(days=1)
    fim = datetime.now(timezone.utc)

    response = client.get(
        "/work-sessions/metrics/timeline",
        params={
            "inicio": inicio.isoformat(),
            "fim": fim.isoformat(),
            "agrupamento": "ano",
        },
        headers=_headers(token),
    )

    assert response.status_code == 400

def test_metrics_timeline_periodo_invalido(
    client,
    admin_logado,
):
    _admin, token = admin_logado

    agora = datetime.now(timezone.utc)

    response = client.get(
        "/work-sessions/metrics/timeline",
        params={
            "inicio": agora.isoformat(),
            "fim": (
                agora - timedelta(hours=1)
            ).isoformat(),
        },
        headers=_headers(token),
    )

    assert response.status_code == 400

def test_metrics_timeline_divide_sessao_entre_dias(
    client,
    db_session,
    admin_logado,
    usuario_no_setor,
):
    _admin, admin_token = admin_logado
    usuario, _user_token = usuario_no_setor

    fuso = ZoneInfo("America/Sao_Paulo")

    entrada = datetime(
        2026,
        10,
        1,
        23,
        0,
        tzinfo=fuso,
    )

    saida = datetime(
        2026,
        10,
        2,
        2,
        0,
        tzinfo=fuso,
    )

    sessao = WorkSession(
        usuario_id=usuario.id,
        setor_id=TestID.SETOR_TESTE,
        entrada=entrada,
        saida=saida,
        expiracao=entrada + timedelta(hours=8),
        status=WorkSessionStatus.FINALIZADA,
        motivo_encerramento=MotivoEncerramento.MANUAL,
    )

    db_session.add(sessao)
    db_session.commit()

    inicio = datetime(
        2026,
        10,
        1,
        0,
        0,
        tzinfo=fuso,
    )

    fim = datetime(
        2026,
        10,
        3,
        0,
        0,
        tzinfo=fuso,
    )

    response = client.get(
        "/work-sessions/metrics/timeline",
        params={
            "inicio": inicio.isoformat(),
            "fim": fim.isoformat(),
            "usuario_id": str(usuario.id),
            "agrupamento": "dia",
        },
        headers=_headers(admin_token),
    )

    assert response.status_code == 200

    data = response.json()

    assert data["agrupamento"] == "dia"
    assert data["fuso"] == "America/Sao_Paulo"

    intervalos = data["intervalos"]

    assert len(intervalos) == 2

    primeiro_dia = intervalos[0]
    segundo_dia = intervalos[1]

    assert primeiro_dia["tempo_trabalhado_segundos"] == 3600
    assert primeiro_dia["tempo_pausado_segundos"] == 0

    assert segundo_dia["tempo_trabalhado_segundos"] == 7200
    assert segundo_dia["tempo_pausado_segundos"] == 0

    total_trabalhado = sum(
        intervalo["tempo_trabalhado_segundos"]
        for intervalo in intervalos
    )

    assert total_trabalhado == 10800

