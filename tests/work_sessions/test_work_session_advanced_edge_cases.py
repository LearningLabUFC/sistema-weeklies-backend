"""Casos de borda avançados — módulo de Controle de Horas."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.core.constants import TestID
from app.models.pause import Pause
from app.models.work_session import (
    MotivoEncerramento,
    WorkSession,
    WorkSessionStatus,
)
from app.work_sessions import service as work_session_service

from .helpers import _buscar_sessao, _headers


def _congelar_tempo(monkeypatch, instante: datetime) -> None:
    """Fixa datetime.now() usado pelo service."""

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


def test_current_apos_expiracao_sem_scheduler_limita_tempo(
    client,
    db_session,
    sessao_ativa,
    monkeypatch,
):
    """Sessão ainda aberta não pode contabilizar tempo após a expiração."""
    _usuario, token, sessao = sessao_ativa

    expiracao = datetime(
        2026,
        10,
        4,
        15,
        0,
        tzinfo=timezone.utc,
    )
    entrada = expiracao - timedelta(hours=2)

    work_session = _buscar_sessao(
        db_session,
        sessao["id"],
    )
    work_session.entrada = entrada
    work_session.expiracao = expiracao
    work_session.saida = None
    work_session.status = WorkSessionStatus.ATIVA
    db_session.commit()

    _congelar_tempo(
        monkeypatch,
        expiracao + timedelta(hours=1),
    )

    response = client.get(
        "/work-sessions/current",
        headers=_headers(token),
    )

    assert response.status_code == 200

    data = response.json()["sessao"]

    assert data is not None
    assert data["id"] == sessao["id"]
    assert data["tempo_trabalhado_segundos"] == 7200

    db_session.refresh(work_session)

    # Consultar não deve substituir o trabalho do scheduler.
    assert work_session.saida is None
    assert work_session.status == WorkSessionStatus.ATIVA


def test_end_apos_expiracao_sem_scheduler_preserva_limite(
    client,
    db_session,
    sessao_ativa,
    monkeypatch,
):
    """Encerramento tardio deve usar a expiração, não o horário da requisição."""
    _usuario, token, sessao = sessao_ativa

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
        expiracao + timedelta(minutes=20),
    )

    response = client.patch(
        f"/work-sessions/{sessao['id']}/end",
        headers=_headers(token),
    )

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == WorkSessionStatus.EXPIRADA_SISTEMA.value
    assert (
        data["motivo_encerramento"]
        == MotivoEncerramento.LIMITE_ATINGIDO.value
    )

    db_session.refresh(work_session)

    assert work_session.saida == expiracao
    assert work_session.status == WorkSessionStatus.EXPIRADA_SISTEMA
    assert (
        work_session.motivo_encerramento
        == MotivoEncerramento.LIMITE_ATINGIDO
    )


def test_summary_desconta_multiplas_pausas(
    client,
    db_session,
    sessao_ativa,
):
    """Todas as pausas encerradas devem ser descontadas do tempo trabalhado."""
    _usuario, token, sessao = sessao_ativa

    entrada = datetime(
        2026,
        10,
        4,
        9,
        0,
        tzinfo=timezone.utc,
    )
    saida = datetime(
        2026,
        10,
        4,
        12,
        0,
        tzinfo=timezone.utc,
    )

    work_session = _buscar_sessao(
        db_session,
        sessao["id"],
    )
    work_session.entrada = entrada
    work_session.saida = saida
    work_session.expiracao = entrada + timedelta(hours=8)
    work_session.status = WorkSessionStatus.FINALIZADA
    work_session.motivo_encerramento = MotivoEncerramento.MANUAL

    pausas = [
        Pause(
            sessao_trabalho_id=work_session.id,
            inicio=datetime(
                2026,
                10,
                4,
                9,
                30,
                tzinfo=timezone.utc,
            ),
            fim=datetime(
                2026,
                10,
                4,
                9,
                45,
                tzinfo=timezone.utc,
            ),
        ),
        Pause(
            sessao_trabalho_id=work_session.id,
            inicio=datetime(
                2026,
                10,
                4,
                10,
                30,
                tzinfo=timezone.utc,
            ),
            fim=datetime(
                2026,
                10,
                4,
                11,
                0,
                tzinfo=timezone.utc,
            ),
        ),
    ]

    db_session.add_all(pausas)
    db_session.commit()

    response = client.get(
        "/work-sessions/summary",
        params={
            "inicio": entrada.isoformat(),
            "fim": saida.isoformat(),
        },
        headers=_headers(token),
    )

    assert response.status_code == 200

    # 3h = 10800s; pausas = 15min + 30min = 2700s.
    assert (
        response.json()["tempo_trabalhado_segundos"]
        == 8100
    )


def test_summary_intervalo_semiaberto_exclui_limites_exatos(
    client,
    db_session,
    usuario_no_setor,
):
    """[inicio, fim): sessão terminando em inicio e começando em fim não entra."""
    usuario, token = usuario_no_setor

    inicio = datetime(
        2026,
        10,
        4,
        10,
        0,
        tzinfo=timezone.utc,
    )
    fim = datetime(
        2026,
        10,
        4,
        12,
        0,
        tzinfo=timezone.utc,
    )

    sessao_antes = WorkSession(
        id=uuid4(),
        usuario_id=usuario.id,
        setor_id=TestID.SETOR_TESTE,
        entrada=inicio - timedelta(hours=1),
        saida=inicio,
        expiracao=inicio + timedelta(hours=7),
        status=WorkSessionStatus.FINALIZADA,
        motivo_encerramento=MotivoEncerramento.MANUAL,
    )

    sessao_depois = WorkSession(
        id=uuid4(),
        usuario_id=usuario.id,
        setor_id=TestID.SETOR_TESTE,
        entrada=fim,
        saida=fim + timedelta(hours=1),
        expiracao=fim + timedelta(hours=8),
        status=WorkSessionStatus.FINALIZADA,
        motivo_encerramento=MotivoEncerramento.MANUAL,
    )

    db_session.add_all(
        [
            sessao_antes,
            sessao_depois,
        ]
    )
    db_session.commit()

    response = client.get(
        "/work-sessions/summary",
        params={
            "inicio": inicio.isoformat(),
            "fim": fim.isoformat(),
        },
        headers=_headers(token),
    )

    assert response.status_code == 200
    assert response.json()["tempo_trabalhado_segundos"] == 0


@pytest.mark.parametrize(
    ("metodo", "sufixo"),
    [
        ("post", "/pauses"),
        ("patch", "/continue"),
        ("patch", "/end"),
    ],
)
def test_operacoes_em_sessao_finalizada_retornam_conflito(
    client,
    db_session,
    sessao_ativa,
    metodo,
    sufixo,
):
    """Sessão finalizada não pode receber novas mutações."""
    _usuario, token, sessao = sessao_ativa

    work_session = _buscar_sessao(
        db_session,
        sessao["id"],
    )
    work_session.saida = datetime.now(timezone.utc)
    work_session.status = WorkSessionStatus.FINALIZADA
    work_session.motivo_encerramento = MotivoEncerramento.MANUAL
    db_session.commit()

    request = getattr(client, metodo)

    response = request(
        f"/work-sessions/{sessao['id']}{sufixo}",
        headers=_headers(token),
    )

    assert response.status_code == 409


def test_end_pause_rejeita_pause_de_outra_sessao(
    client,
    db_session,
    sessao_ativa,
):
    """Um pause_id válido não pode ser encerrado através de outra sessão."""
    usuario, token, sessao = sessao_ativa

    work_session = _buscar_sessao(
        db_session,
        sessao["id"],
    )
    work_session.status = WorkSessionStatus.EM_PAUSA

    outra_sessao = WorkSession(
        id=uuid4(),
        usuario_id=usuario.id,
        setor_id=work_session.setor_id,
        entrada=work_session.entrada - timedelta(days=1),
        saida=work_session.entrada - timedelta(hours=23),
        expiracao=work_session.entrada - timedelta(hours=16),
        status=WorkSessionStatus.FINALIZADA,
        motivo_encerramento=MotivoEncerramento.MANUAL,
    )
    db_session.add(outra_sessao)
    db_session.flush()

    pausa_outra_sessao = Pause(
        id=uuid4(),
        sessao_trabalho_id=outra_sessao.id,
        inicio=outra_sessao.entrada + timedelta(minutes=10),
        fim=None,
    )
    db_session.add(pausa_outra_sessao)
    db_session.commit()

    response = client.patch(
        (
            f"/work-sessions/{sessao['id']}"
            f"/pauses/{pausa_outra_sessao.id}/end"
        ),
        headers=_headers(token),
    )

    assert response.status_code == 404

    db_session.refresh(pausa_outra_sessao)
    assert pausa_outra_sessao.fim is None
