"""
Configuração centralizada da aplicação.

Utiliza pydantic-settings para carregar, validar e tipar
todas as variáveis de ambiente definidas no arquivo .env.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações da aplicação, carregadas a partir de variáveis de ambiente."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Banco de dados (PostgreSQL) ──────────────────────────
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5433

    # ── Autenticação JWT ─────────────────────────────────────
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # ── Redis (OTP / Cache) ──────────────────────────────────
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    OTP_EXPIRE_MINUTES: int = 15

    # ── E-mail (SMTP — Gmail App Password) ───────────────────
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_NAME: str = "LearningLab"
    SMTP_FROM_EMAIL: str = "noreply@learninglab.com.br"
    SMTP_USE_TLS: bool = True

    # ── Rate Limiting (forgot-password) ──────────────────────
    FORGOT_PASSWORD_MAX_REQUESTS: int = 3
    FORGOT_PASSWORD_WINDOW_MINUTES: int = 15

    # ── Anti Brute-force (verify-code) ───────────────────────
    VERIFY_CODE_MAX_ATTEMPTS: int = 5
    VERIFY_CODE_COOLDOWN_MINUTES: int = 15

    # ── Frontend URL ───────────────────────────────────────────
    FRONTEND_URL: str = "http://localhost:5173"

    @property
    def DATABASE_URL(self) -> str:
        """Monta a URL de conexão com o PostgreSQL a partir das variáveis individuais."""
        return (
            f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def REDIS_URL(self) -> str:
        """Monta a URL de conexão com o Redis."""
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"


settings = Settings()
