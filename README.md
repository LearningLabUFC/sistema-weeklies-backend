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

Copie o arquivo de exemplo e preencha com os seus valores:

```bash
cp .env.example .env
```

Edite o `.env` gerado e substitua os placeholders — em especial `POSTGRES_PASSWORD` e `SECRET_KEY`.

> **Nota:** o `.env` está listado no `.gitignore` — nunca versione credenciais.  
> Para gerar uma `SECRET_KEY` segura: `python -c "import secrets; print(secrets.token_urlsafe(64))"`

### 5. Iniciar a aplicação (Modo Automatizado)

Para facilitar o desenvolvimento local, foi criado um script unificado que inicializa o banco de dados Docker, aplica as migrações do Alembic e sobe a API. Basta rodar:

```bash
python run.py
```

* **API**: [http://localhost:8000](http://localhost:8000)
* **Documentação (Swagger UI)**: [http://localhost:8000/docs](http://localhost:8000/docs)
* **Health Check**: [http://localhost:8000/api/health](http://localhost:8000/api/health)

#### Autenticação no Swagger UI:
1. Faça login através do endpoint `POST /auth/login` com suas credenciais e copie o `token_acesso` retornado.
2. Clique no botão verde **Authorize** no canto superior direito da página do Swagger.
3. Cole o valor do token no campo **Value** (sem aspas) e clique em **Authorize**.
4. Agora todos os endpoints protegidos estarão autenticados.

*(Ao fechar a aplicação com `Ctrl+C`, os containers do Docker serão finalizados automaticamente).*

---

## Gestão de Membros e Permissões (RBAC)

Endpoints protegidos para administradores (`admin` e `super_admin`) gerenciarem a equipe:

| Método | Endpoint | Acesso | Descrição |
| ------ | -------- | ------ | --------- |
| `GET` | `/admin/users` | Admin / Super Admin | Listagem paginada (`pagina`, `limite`), com busca por nome/email (`busca`) e filtros (`status`, `role`). Retorna dados completos dos membros com nomes de curso, status e cargo resolvidos. |
| `GET` | `/admin/users/pending` | Admin / Super Admin | Lista usuários com cadastro pendente aguardando aprovação. |
| `PATCH` | `/admin/users/{user_id}/role` | Admin / Super Admin | Altera o cargo de um membro (`super_admin`, `admin`, `aluno`). Impedimentos: `admin` comum não pode alterar `super_admin`, auto-rebaixamento é proibido, e o último admin do sistema não pode ser rebaixado. |
| `PATCH` | `/admin/users/{user_id}/status` | Admin / Super Admin | Aprova ou altera o status de um membro (`ativo`, `inativo`). |
| `DELETE` | `/admin/users/{user_id}` | Super Admin | Inativa (soft delete) qualquer usuário no sistema. |

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
├── .env.example          # Modelo de variáveis de ambiente (versionado)
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