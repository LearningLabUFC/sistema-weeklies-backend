from datetime import datetime
from unittest.mock import MagicMock

import pytest

from app.weeklies.timezone_utils import FUSO_LLAB


@pytest.fixture(autouse=True)
def weekly_clock(monkeypatch):
    """Os testes do módulo não dependem do dia em que a CI é executada."""
    now = datetime(2026, 10, 2, 12, tzinfo=FUSO_LLAB)
    monkeypatch.setattr("app.weeklies.timezone_utils.get_now_fortaleza", lambda: now)
    monkeypatch.setattr("app.weeklies.service.get_now_fortaleza", lambda: now)


@pytest.fixture(autouse=True)
def mock_weekly_smtp(monkeypatch):
    """Executa os caminhos de notificação sem abrir conexões SMTP reais."""
    smtp = MagicMock()
    monkeypatch.setattr("app.core.email.smtplib.SMTP", smtp)
    return smtp
