import uuid

import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models.course import Course
from tests.setup_test_db import init_test_db

# 1. Certificar que o DB de testes existe
init_test_db()

# 2. Configurar SQLAlchemy para testes
db_url_str = str(settings.DATABASE_URL)
base_url = db_url_str.rsplit('/', 1)[0]
TEST_DATABASE_URL = f"{base_url}/weeklies_test_db"

test_engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="session", autouse=True)
def tables():
    """Cria tabelas antes de tudo e apaga no final, também insere os seeds."""
    Base.metadata.create_all(bind=test_engine)
    
    from app.seeds.seed_roles import ROLES, Role
    from app.seeds.seed_status import STATUSES, Status
    
    db = TestingSessionLocal()
    try:
        # Seeds de Roles
        for r_data in ROLES:
            if not db.query(Role).filter(Role.id == r_data["id"]).first():
                db.add(Role(id=r_data["id"], nome=r_data["nome"]))
                
        # Seeds de Statuses
        for s_data in STATUSES:
            if not db.query(Status).filter(Status.id == s_data["id"]).first():
                db.add(Status(id=s_data["id"], nome=s_data["nome"]))
        
        # Seed de Curso padrão para testes
        curso_id = uuid.UUID("3fa85f64-5717-4562-b3fc-2c963f66afa4")
        if not db.query(Course).filter(Course.id == curso_id).first():
            db.add(Course(id=curso_id, nome="Engenharia de Software Teste", ativo=True))
            
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

    import app.redis as app_redis
    
    # Criar um servidor isolado por teste
    server = FakeServer()
    # fake_pool atua como o client async aioredis
    fake_pool = fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)
    
    monkeypatch.setattr(app_redis, "_redis_pool", fake_pool)
    yield fake_pool
