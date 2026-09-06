"""
Script utilitário para criar o banco de dados de teste (weeklies_test_db).
Roda antes de iniciar os testes para garantir que o banco existe no container PostgreSQL.
"""

from sqlalchemy import create_engine, text

from app.config import settings


def init_test_db():
    # URL do banco de dados principal (não o de teste) para poder criar o de teste
    # Exemplo: postgresql://user:pass@localhost:5432/weeklies_db
    # Vamos trocar o nome do banco para 'postgres' para conectar no db default e executar o CREATE DATABASE
    
    # Extrair os componentes da string de conexao original
    db_url_str = str(settings.DATABASE_URL)
    base_url = db_url_str.rsplit('/', 1)[0]
    default_db_url = f"{base_url}/postgres"
    
    TEST_DB_NAME = "weeklies_test_db"
    
    print(f"Verificando existência do banco de teste: {TEST_DB_NAME}...")
    
    # Engine conectando no banco padrão 'postgres'
    engine = create_engine(default_db_url, isolation_level="AUTOCOMMIT")
    
    try:
        with engine.connect() as conn:
            # Verifica se o banco já existe
            result = conn.execute(text(f"SELECT 1 FROM pg_database WHERE datname='{TEST_DB_NAME}'"))
            if not result.scalar():
                print(f"Criando banco de dados de teste: {TEST_DB_NAME}...")
                conn.execute(text(f"CREATE DATABASE {TEST_DB_NAME}"))
                print("Banco de dados criado com sucesso.")
            else:
                print("Banco de dados de teste já existe.")
    except Exception as e:  # noqa: BLE001
        print(f"Erro ao verificar/criar banco de teste: {e}")
    finally:
        engine.dispose()

if __name__ == "__main__":
    init_test_db()
