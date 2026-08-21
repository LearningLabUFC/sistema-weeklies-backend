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
| Cache / OTP    | Redis 7+ (Docker)           |
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

Copie o arquivo de exemplo e preencha com os seus valores:

```bash
cp .env.example .env
```

Edite o `.env` gerado e substitua os placeholders — em especial `POSTGRES_PASSWORD` e `SECRET_KEY`.

> **Nota:** o `.env` está listado no `.gitignore` — nunca versione credenciais.  
> Para gerar uma `SECRET_KEY` segura: `python -c "import secrets; print(secrets.token_urlsafe(64))"`

### 5. Iniciar a aplicação (Modo Automatizado)

Para facilitar o desenvolvimento local, foi criado um script unificado que inicializa os containers Docker (PostgreSQL, pgAdmin, Redis), aplica as migrações do Alembic e sobe a API. Basta rodar:

```bash
python run.py
```

* **API**: [http://localhost:8000](http://localhost:8000)
* **Documentação Interativa (Swagger UI)**: [http://localhost:8000/docs](http://localhost:8000/docs)
* **Health Check**: [http://localhost:8000/api/health](http://localhost:8000/api/health)

#### Autenticação no Swagger UI:
1. Faça login através do endpoint `POST /auth/login` com suas credenciais e copie o `token_acesso` retornado.
2. Clique no botão verde **Authorize** no canto superior direito da página do Swagger.
3. Cole o valor do token no campo **Value** (sem aspas) e clique em **Authorize**.
4. Agora todos os endpoints protegidos estarão autenticados.

*(Ao fechar a aplicação com `Ctrl+C`, os containers do Docker serão finalizados automaticamente).*

---

## Documentação Detalhada

Para especificações técnicas aprofundadas, consulte os documentos na pasta [`docs/`](docs/):

- 📄 [**Contrato da API (`docs/api_contract.md`)**](docs/api_contract.md): Especificação de endpoints, formato de payloads (request/response), status HTTP e interfaces TypeScript para integração com o frontend.
- 🔐 [**Módulo de Identidade e RBAC (`docs/modulo_identidade.md`)**](docs/modulo_identidade.md): Fluxo de aprovação de contas, controle de acesso baseado em papéis (`super_admin`, `admin`, `aluno`), soft deletes e recuperação de senha (OTP via Redis).
- 🏗️ [**Infraestrutura Base (`docs/infraestrutura_base.md`)**](docs/infraestrutura_base.md): Detalhes sobre conexão com PostgreSQL (Psycopg 3), gerenciamento de sessões, cache Redis, serviço de e-mails SMTP e automação com `run.py`.

---

## Estrutura do Projeto

```text
sistema-weeklies-backend/
├── alembic/              # Configurações e versões de migrações
├── app/
│   ├── models/           # Modelos ORM (User, Role, Status, Course...)
│   ├── routers/          # Endpoints agrupados por domínio (auth, users, admin, domain)
│   ├── utils/            # Utilitários (segurança, envio de e-mail, etc.)
│   ├── config.py         # Configurações centralizadas via pydantic-settings
│   ├── database.py       # Engine e SessionLocal do SQLAlchemy
│   ├── deps.py           # Injeção de dependências e autenticação JWT/RBAC
│   ├── main.py           # Entrypoint da aplicação FastAPI
│   ├── redis.py          # Conexão e rotinas assíncronas do Redis (OTP/Rate limit)
│   └── schemas.py        # Schemas de validação e serialização (Pydantic)
├── docs/                 # Documentação técnica do projeto
├── scripts/              # Utilitários CLI (ex: criação do primeiro super admin)
├── .env.example          # Modelo de variáveis de ambiente
├── docker-compose.yml    # Serviços locais (PostgreSQL, pgAdmin, Redis)
├── requirements.txt      # Dependências Python
└── run.py                # Script unificado de inicialização local
```

---

## Scripts úteis

| Comando                                        | Descrição                          |
| ---------------------------------------------- | ---------------------------------- |
| `python run.py`                                | Sobe infra Docker, migrações e API |
| `uvicorn app.main:app --reload`                | Servidor de desenvolvimento isolado|
| `alembic revision --autogenerate -m "msg"`     | Gerar nova migration               |
| `alembic upgrade head`                         | Aplicar migrações pendentes        |
| `alembic downgrade -1`                         | Reverter última migration          |
| `pytest`                                       | Rodar testes automatizados         |

---

## Licença

Projeto interno do **Learning Lab UFC**. Todos os direitos reservados.