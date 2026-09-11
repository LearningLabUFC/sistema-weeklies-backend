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

## Arquitetura Modular by Feature

Este projeto utiliza a arquitetura **Modular by Feature** (ou *Vertical Slicing*). Em vez de agrupar arquivos por tipo de tecnologia (ex: todos os controllers juntos, todos os services juntos), o código é agrupado pela **funcionalidade (feature)**. 

Cada módulo da aplicação (ex: `auth`, `admin`, `users`) é independente e contém suas próprias regras de negócio, rotas e acesso a dados, dividido internamente em três camadas principais:
1. **Router (`router.py`)**: Camada Web (FastAPI). Recebe as requisições HTTP, valida payloads de entrada e repassa os dados para o Service.
2. **Service (`service.py`)**: Camada de Negócios. Contém toda a lógica e as regras do negócio. Esta camada não sabe nada sobre HTTP e levanta exceções semânticas de domínio (`app/core/exceptions.py`).
3. **Repository (`repository.py`)**: Camada de Dados. Centraliza todas as chamadas ao banco de dados (SQLAlchemy). O Service consome o Repository para buscar ou persistir entidades.

---

## Estrutura do Projeto

```text
sistema-weeklies-backend/
├── alembic/              # Configurações e versões de migrações
├── app/
│   ├── models/           # Modelos ORM (User, Role, Status, Course...)
│   ├── core/             # Infraestrutura transversal (config, db, redis, security, exceptions)
│   ├── auth/             # Módulo de Autenticação (router, service, repository, schemas)
│   ├── admin/            # Módulo de Administração (router, service, repository, schemas)
│   ├── users/            # Módulo de Usuários (router, service, repository, schemas)
│   ├── courses/          # Módulo de Cursos (router, service, repository, schemas)
│   ├── api_router.py     # Agrupador central de todas as rotas da API
│   ├── deps.py           # Injeção de dependências (Autenticação JWT, permissões RBAC)
│   └── main.py           # Entrypoint da aplicação FastAPI
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