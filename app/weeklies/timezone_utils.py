"""Utilitários de fuso horário e controle da janela de submissão de Weeklies."""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.core.exceptions import BadRequestError

# Fuso oficial do Learning Lab UFC Russas: UTC-3 (fixo, sem horário de verão)
FUSO_LLAB = ZoneInfo("America/Fortaleza")


def get_now_fortaleza() -> datetime:
    """Retorna o datetime atual no fuso horário do Learning Lab (America/Fortaleza)."""
    return datetime.now(FUSO_LLAB)


def dentro_da_janela(momento: datetime | None = None) -> bool:
    """
    Verifica se o momento informado (ou o momento atual) está dentro da janela de submissão.
    Se settings.WEEKLY_IGNORAR_JANELA for True, sempre retorna True (modo de testes/dev).

    Janela oficial:
    - Abre: Sexta-feira às 00:00:00 (America/Fortaleza)
    - Fecha: Segunda-feira às 23:59:59 (America/Fortaleza)

    Dias da semana no Python (agora.weekday()):
    - 0 = Segunda-feira (ABERTA)
    - 1 = Terça-feira (FECHADA)
    - 2 = Quarta-feira (FECHADA)
    - 3 = Quinta-feira (FECHADA)
    - 4 = Sexta-feira (ABERTA)
    - 5 = Sábado (ABERTA)
    - 6 = Domingo (ABERTA)
    """
    from app.config import settings

    if settings.WEEKLY_IGNORAR_JANELA:
        return True

    if momento is None:
        momento = get_now_fortaleza()
    elif momento.tzinfo is None:
        # Se vier naive, assume UTC e converte para Fortaleza
        momento = momento.replace(tzinfo=timezone.utc).astimezone(FUSO_LLAB)
    else:
        momento = momento.astimezone(FUSO_LLAB)

    dia_semana = momento.weekday()
    return dia_semana in (4, 5, 6, 0)


def obter_semana_referencia(momento: datetime | None = None) -> date:
    """
    Calcula a data da segunda-feira de referência da janela atual ou mais recente.

    Regra de negócio (Decisão D2):
    - Identificação da semana: Data da segunda-feira em que a janela fecha.
    - Se for Sexta (4): +3 dias
    - Se for Sábado (5): +2 dias
    - Se for Domingo (6): +1 dia
    - Se for Segunda (0): o próprio dia
    - Se fora da janela (Terça a Quinta): retorna a segunda-feira que acabou de fechar.
    """
    if momento is None:
        momento = get_now_fortaleza()
    elif momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc).astimezone(FUSO_LLAB)
    else:
        momento = momento.astimezone(FUSO_LLAB)

    dia_semana = momento.weekday()
    data_base = momento.date()

    if dia_semana == 4:  # Sexta
        return data_base + timedelta(days=3)
    if dia_semana == 5:  # Sábado
        return data_base + timedelta(days=2)
    if dia_semana == 6:  # Domingo
        return data_base + timedelta(days=1)
    if dia_semana == 0:  # Segunda
        return data_base

    # Terça (1), Quarta (2), Quinta (3): segunda-feira que acabou de fechar
    return data_base - timedelta(days=dia_semana)


def validar_janela_submissao(
    momento: datetime | None = None,
    permitir_fora_da_janela: bool = False,
    *,
    semana_referencia: date | None = None,
) -> None:
    """
    Valida a janela atual e, quando informada, a semana do relatório alterado.
    Pode ser contornado se permitir_fora_da_janela for True (ex: ações administrativas)
    ou se settings.WEEKLY_IGNORAR_JANELA for True (modo de desenvolvimento/testes).
    """
    from app.config import settings

    if permitir_fora_da_janela or settings.WEEKLY_IGNORAR_JANELA:
        return

    if momento is None:
        momento = get_now_fortaleza()

    if not dentro_da_janela(momento):
        raise BadRequestError(
            "Fora da janela de submissão de weeklies "
            "(Sexta 00:00 a Segunda 23:59, horário de Brasília/Fortaleza)."
        )

    if semana_referencia is not None:
        if semana_referencia.weekday() != 0:
            raise BadRequestError("A semana de referência deve ser uma segunda-feira.")
        if semana_referencia != obter_semana_referencia(momento):
            raise BadRequestError(
                "Esta weekly não pertence à janela de submissão atual."
            )
