"""
Configuração centralizada da aplicação.

Utiliza pydantic-settings para carregar, validar e tipar
todas as variáveis de ambiente definidas no arquivo .env.
"""

from datetime import date

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações da aplicação, carregadas a partir de variáveis de ambiente."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Banco de dados (PostgreSQL) ──────────────────────────
    POSTGRES_USER: str = ""
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = ""
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5433
    DATABASE_URL_ENV: str | None = Field(default=None, validation_alias="DATABASE_URL")

    # ── Autenticação JWT ─────────────────────────────────────
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── Redis (OTP / Cache) ──────────────────────────────────
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str | None = None
    REDIS_SSL: bool = False
    REDIS_URL_ENV: str | None = Field(default=None, validation_alias="REDIS_URL")
    OTP_EXPIRE_MINUTES: int = 15

    # ── E-mail (SMTP — Gmail App Password) ───────────────────
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_NAME: str = "LearningLab"
    SMTP_FROM_EMAIL: str = "noreply@learninglab.com.br"
    SMTP_USE_TLS: bool = True
    SMTP_TIMEOUT: float = Field(default=10.0, gt=0)

    # ── Rate Limiting (forgot-password) ──────────────────────
    FORGOT_PASSWORD_MAX_REQUESTS: int = 3
    FORGOT_PASSWORD_IP_MAX_REQUESTS: int = 10
    FORGOT_PASSWORD_WINDOW_MINUTES: int = 15

    # ── Anti Brute-force (verify-code) ───────────────────────
    VERIFY_CODE_MAX_ATTEMPTS: int = 5
    VERIFY_CODE_COOLDOWN_MINUTES: int = 15

    # ── Controle de Horas ────────────────────────────────────────
    WORK_SESSION_LIMIT_HOURS: int = 8
    WORK_SESSION_EXTENSION_HOURS: int = 2
    WORK_SESSION_EXTENSION_WINDOW_MINUTES: int = 10

    # ── Frontend URL ───────────────────────────────────────────
    FRONTEND_URL: str = "http://localhost:5173"

    # ── Weeklies & Scheduler ──────────────────────────────────
    ENABLE_SCHEDULER: bool = True
    WEEKLY_TIMEZONE: str = "America/Fortaleza"
    WEEKLY_TASK_DEFAULT_DEADLINE_DAYS: int = 14
    WEEKLY_AUDIT_ESCALATION_DAYS: int = 7
    WEEKLY_STRIKE_1_WEEKS: int = 2
    WEEKLY_STRIKE_2_WEEKS: int = 3
    WEEKLY_STRIKE_3_WEEKS: int = 4
    WEEKLY_MARCO_IMPLANTACAO: date | None = None
    WEEKLY_IGNORAR_JANELA: bool = False

    @property
    def DATABASE_URL(self) -> str:
        """Monta a URL de conexão com o PostgreSQL a partir das variáveis individuais ou retorna DATABASE_URL se definida."""
        if self.DATABASE_URL_ENV:
            url = self.DATABASE_URL_ENV
            if url.startswith("postgresql://"):
                return url.replace("postgresql://", "postgresql+psycopg://", 1)
            if url.startswith("postgres://"):
                return url.replace("postgres://", "postgresql+psycopg://", 1)
            return url
        return (
            f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def REDIS_URL(self) -> str:
        """Monta a URL de conexão com o Redis (ou retorna REDIS_URL se definida no ambiente)."""
        if self.REDIS_URL_ENV:
            return self.REDIS_URL_ENV
        scheme = "rediss" if self.REDIS_SSL else "redis"
        auth = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        return f"{scheme}://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"


settings = Settings()
