import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.core.constants import RoleID, RoleName, StatusID, StatusName, TestID
from app.database import Base, get_db
from app.main import app
from app.models.course import Course
from tests.setup_test_db import init_test_db

# 1. Certificar que o DB de testes existe
init_test_db()

# 2. Configurar SQLAlchemy para testes
db_url_str = str(settings.DATABASE_URL)
base_url = db_url_str.rsplit("/", 1)[0]
TEST_DATABASE_URL = f"{base_url}/weeklies_test_db"

test_engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="session", autouse=True)
def tables():
    """Cria tabelas antes de tudo e apaga no final, também insere os seeds."""
    Base.metadata.create_all(bind=test_engine)

    from app.models.role import Role
    from app.models.sector import Sector
    from app.models.status import Status

    db = TestingSessionLocal()
    try:
        # Seeds de Roles
        for role_id, role_nome in [
            (RoleID.SUPER_ADMIN, RoleName.SUPER_ADMIN),
            (RoleID.ADMIN, RoleName.ADMIN),
            (RoleID.USUARIO, RoleName.USUARIO),
        ]:
            if not db.query(Role).filter(Role.id == role_id).first():
                db.add(Role(id=role_id, nome=role_nome))

        # Seeds de Statuses
        for status_id, status_nome in [
            (StatusID.PENDENTE, StatusName.PENDENTE),
            (StatusID.ATIVO, StatusName.ATIVO),
            (StatusID.INATIVO, StatusName.INATIVO),
        ]:
            if not db.query(Status).filter(Status.id == status_id).first():
                db.add(Status(id=status_id, nome=status_nome))

        # Seed de Curso padrão para testes
        if not db.query(Course).filter(Course.id == TestID.CURSO_TESTE).first():
            db.add(
                Course(
                    id=TestID.CURSO_TESTE, nome="Engenharia de Software Teste", ativo=True
                )
            )

        # Seed de Setor padrão para testes
        if not db.query(Sector).filter(Sector.id == TestID.SETOR_TESTE).first():
            db.add(Sector(id=TestID.SETOR_TESTE, nome="Desenvolvimento Teste"))

        db.commit()
    finally:
        db.close()

    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db_session():
    """
    Inicia uma nova transação por teste.
    No final do teste faz o rollback para limpar estado.
    """
    connection = test_engine.connect()
    transaction = connection.begin()

    # O bind=connection faz com que a sessão use a transação atual
    session = TestingSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db_session, fake_redis):
    """
    Sobrescreve a dependência get_db com nossa sessão transacional e retorna o TestClient.
    """

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def fake_redis(monkeypatch):
    """
    Sobrescreve a conexão Redis pela implementação in-memory pura (fakeredis).
    Isola totalmente os testes do Redis real.
    """
    from fakeredis import FakeServer

    import app.core.redis.connection as app_redis_conn

    # Criar um servidor isolado por teste
    server = FakeServer()
    # fake_pool atua como o client async aioredis
    fake_pool = fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)

    monkeypatch.setattr(app_redis_conn, "_redis_pool", fake_pool)
    yield fake_pool


@pytest.fixture(autouse=True)
def mock_email_service(monkeypatch):
    """
    Mocka o serviço de e-mail globalmente para todos os testes.
    Isso impede que o sistema tente conectar no SMTP real (ex: Gmail) durante os testes,
    o que causava Timeout ou AuthenticationError no GitHub Actions.
    """
    import app.auth.service as auth_service

    # Se a função for chamada no novo service de auth:
    monkeypatch.setattr(auth_service, "enviar_email_otp", lambda email, codigo: True)
