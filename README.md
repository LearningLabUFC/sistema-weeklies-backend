# Sistema Weeklies — Backend

API REST para o sistema de gestão de atividades e presença do Learning Lab UFC.  
O serviço centraliza weeklies, controle de ponto e acompanhamento de presenças em reuniões quinzenais.

---

## Stack

| Camada         | Tecnologia                  |
| -------------- | --------------------------- |
| Linguagem      | Python 3.11+                |
| Framework      | FastAPI                     |
| ORM            | SQLAlchemy 2.x              |
| Migrações      | Alembic                     |
| Banco de Dados | PostgreSQL 15+ (Docker)     |
| Servidor ASGI  | Uvicorn                     |

---

## Pré-requisitos

- [Python ≥ 3.11](https://www.python.org/downloads/)
- [Docker](https://docs.docker.com/get-docker/)
- `pip` (incluído com o Python)
- `git`

---

## Primeiros passos

### 1. Clonar o repositório

```bash
git clone https://github.com/LearningLabUFC/sistema-weeklies-backend.git
cd sistema-weeklies-backend
```

### 2. Criar e ativar o ambiente virtual

```bash
python -m venv .venv
source .venv/bin/activate   # Linux / macOS
# .venv\Scripts\activate    # Windows
```

### 3. Instalar dependências

```bash
pip install -r requirements.txt
```

### 4. Configurar variáveis de ambiente

O arquivo **`.env`** já está incluído na raiz do projeto. Revise os valores e ajuste conforme necessário:

```dotenv
POSTGRES_USER=weeklies_user
POSTGRES_PASSWORD=weeklies_secret
POSTGRES_DB=weeklies_db
POSTGRES_PORT=5432

DATABASE_URL=postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@localhost:${POSTGRES_PORT}/${POSTGRES_DB}

SECRET_KEY=troque-por-uma-chave-segura-em-producao
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
```

> **Nota:** o `.env` já está listado no `.gitignore` — nunca versione credenciais.

### 5. Subir o PostgreSQL com Docker

```bash
docker run -d \
  --name weeklies-postgres \
  -e POSTGRES_USER=weeklies_user \
  -e POSTGRES_PASSWORD=weeklies_secret \
  -e POSTGRES_DB=weeklies_db \
  -p 5432:5432 \
  -v weeklies_pgdata:/var/lib/postgresql/data \
  postgres:15-alpine
```

> O volume nomeado `weeklies_pgdata` garante que os dados persistam entre reinícios do container.

### 6. Rodar as migrações (Alembic)

```bash
# Inicializar o Alembic (apenas na primeira vez, se ainda não houver pasta alembic/)
alembic init alembic

# Gerar uma migration a partir dos modelos
alembic revision --autogenerate -m "initial schema"

# Aplicar as migrações
alembic upgrade head
```

### 7. Iniciar o servidor de desenvolvimento

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

A API estará disponível em **http://localhost:8000**.  
A documentação interativa (Swagger UI) estará em **http://localhost:8000/docs**.

---

## Estrutura de diretórios (sugerida)

```
sistema-weeklies-backend/
├── alembic/              # Configuração e versões de migrações
├── app/
│   ├── __init__.py
│   ├── main.py           # Entrypoint FastAPI
│   ├── config.py         # Carregamento de variáveis de ambiente
│   ├── database.py       # Engine e SessionLocal do SQLAlchemy
│   ├── models/           # Modelos ORM (User, Weekly, Attendance…)
│   ├── schemas/          # Schemas Pydantic (request/response)
│   ├── routers/          # Endpoints agrupados por domínio
│   ├── services/         # Regras de negócio
│   └── utils/            # Helpers (hashing, JWT, etc.)
├── .env                  # Variáveis de ambiente (não versionado)
├── .gitignore
├── alembic.ini
├── requirements.txt
└── README.md
```

---

## Scripts úteis

| Comando                                        | Descrição                          |
| ---------------------------------------------- | ---------------------------------- |
| `uvicorn app.main:app --reload`                | Servidor de desenvolvimento        |
| `alembic revision --autogenerate -m "msg"`     | Gerar nova migration               |
| `alembic upgrade head`                         | Aplicar migrações pendentes        |
| `alembic downgrade -1`                         | Reverter última migration          |
| `pytest`                                       | Rodar testes (quando configurados) |

---

## Licença

Projeto interno do **Learning Lab UFC**. Todos os direitos reservados.