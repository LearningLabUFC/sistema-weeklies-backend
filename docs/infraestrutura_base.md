# Documentação da Infraestrutura Base da API

Esta documentação detalha a arquitetura de infraestrutura da API desenvolvida para o **Sistema de Gestão LL**. O objetivo desta camada é fornecer um ambiente de desenvolvimento padronizado, integrado com PostgreSQL, Redis, migrações automáticas de esquema e serviços auxiliares de e-mail e segurança.

---

## 1. Configuração e Variáveis de Ambiente (`app/config.py`)

A leitura e validação das variáveis de ambiente são gerenciadas centralizadamente pelo módulo `app/config.py` utilizando o **`pydantic-settings`**.

* **Arquivo `.env`**: Centraliza credenciais locais, portas, chaves JWT, configurações SMTP e parâmetros de rate limit.
* **Validação Automática**: Ao iniciar a API, o Pydantic garante que todas as variáveis obrigatórias existam e tenham os tipos corretos (ex: `POSTGRES_PORT` como inteiro).
* **`DATABASE_URL` e `REDIS_URL`**: São montadas dinamicamente via propriedades calculadas na classe `Settings`, evitando dependências de interpolação estática no arquivo de ambiente.
* **Configuração de Extras**: O Pydantic está configurado com `extra="ignore"`, permitindo que variáveis de ferramentas auxiliares (como pgAdmin no `docker-compose.yml`) coexistam no `.env` sem causar erros de validação.

---

## 2. Banco de Dados e Conexão (`app/database.py`)

A persistência de dados utiliza o ORM **SQLAlchemy 2.x** e o driver moderno **Psycopg 3** (`psycopg[binary]`) para conexão com o PostgreSQL.

* **Engine**: Criada com a URL de conexão `postgresql+psycopg://...`. Utiliza `pool_pre_ping=True` para descartar automaticamente conexões inativas antes de cada consulta.
* **SessionLocal**: Fábrica de sessões configurada sem `autocommit` ou `autoflush` automáticos, garantindo controle transacional explícito.
* **Base Declarativa**: Classe `Base` da qual todos os modelos ORM herdam (`declarative_base`).
* **Injeção de Dependência (`get_db`)**: Dependência FastAPI que abre uma nova sessão de banco de dados por requisição HTTP e garante o fechamento (`db.close()`) no bloco `finally`.

---

## 3. Modelos ORM (`app/models/`)

A base de dados é estruturada através de modelos relacionais SQLAlchemy:

* **`User` (`app/models/user.py`)**: Tabela `usuarios`. Contém os dados cadastrais, hash de senha (`senha_hash`), timestamp de alteração de credenciais (`senha_atualizada_em`), além de chaves estrangeiras com integridade referencial:
  - `curso_id`: Chave estrangeira para `cursos.id` (`relationship("Course")`).
  - `status_id`: Chave estrangeira para `status_usuarios.id` (`relationship("Status")`).
  - `global_role`: Chave estrangeira para `cargos.id` (`relationship("Role")`).
* **`Status` (`app/models/status.py`)**: Tabela `status_usuarios` com os estados `pendente`, `ativo` e `inativo`.
* **`Role` (`app/models/role.py`)**: Tabela `cargos` com os papéis `super_admin`, `admin` e `aluno`.
* **`Course` (`app/models/course.py`)**: Tabela `cursos` com nome e status ativo do curso acadêmico.

---

## 4. Gerenciador de Migrações (`Alembic`)

O **Alembic** gerencia as alterações de esquema no banco de dados.

* **Inicialização**: A pasta `alembic/` e o arquivo `alembic.ini` contêm as configurações de migração.
* **Conexão Dinâmica**: O script `alembic/env.py` importa as configurações da aplicação (`app.config.settings`) para ler a string de conexão diretamente.
* **Carregamento de Modelos**: O pacote `app.models` é importado no `env.py` para registrar todas as tabelas na `Base.metadata`, permitindo autogeração de novas migrações com `alembic revision --autogenerate`.

---

## 5. Criptografia de Senhas e Segurança (`app/utils/security.py`)

* **Bcrypt**: A biblioteca `bcrypt` é utilizada diretamente para geração e verificação segura de hashes de senha (`hash_senha` e `verificar_senha`), contornando incompatibilidades do antigo `passlib`.
* **JWT (Python-Jose)**: Utilitários para criação de `token_acesso` (60 min), `token_atualizacao` (7 dias) e `token_redefinicao` (5 min).
* **OTP**: Geração de códigos numéricos de 6 dígitos via `secrets.choice` (`gerar_codigo_otp`).

---

## 6. Redis e Cache em Memória (`app/redis.py`)

A infraestrutura conta com um container do **Redis 7** para dados voláteis de alta performance:

* **Cliente Assíncrono**: Utiliza `redis.asyncio` com suporte a `hiredis` para operações não bloqueantes no event loop do FastAPI.
* **Ciclo de Vida (`lifespan`)**: O pool de conexões do Redis é inicializado no startup da API no `app/main.py` e encerrado graciosamente no shutdown.
* **Rotinas OTP e Rate Limiting**:
  - `salvar_otp` / `verificar_otp`: Armazenamento de OTP com TTL de 15 minutos e consumo de uso único.
  - `verificar_rate_limit_email` / `verificar_rate_limit_ip`: Controle de taxa de requisições por janela deslizante (*sliding window*).
  - `verificar_bloqueio_bruteforce` / `aplicar_cooldown_bruteforce`: Bloqueio automático por 15 minutos após 5 tentativas falhas consecutivas.

---

## 7. Serviço de E-mails Transacionais (`app/utils/email_service.py`)

Envio assíncrono de e-mails em background utilizando SMTP:

* **Autenticação**: Suporte a TLS (porta 587) com Gmail App Password.
* **Templates HTML**: Utiliza template responsivo em `app/templates/otp_template.html` para exibição profissional do código de recuperação de conta.
* **Background Tasks**: O envio é disparado via `BackgroundTasks` do FastAPI para não bloquear o tempo de resposta HTTP.

---

## 8. Verificação de Saúde (`/api/health`)

O endpoint `/api/health` implementa verificação ativa de componentes:
* **API**: Retorna `status: healthy` caso o servidor HTTP esteja operacional.
* **PostgreSQL**: Executa uma query de teste (`SELECT 1`). Se o banco estiver inacessível, responde com status HTTP `503 Service Unavailable` e detalha a falha no corpo JSON.

---

## 9. Script de Inicialização Automatizado (`run.py`)

Script multiplataforma (Windows, macOS e Linux) que orquestra todo o ambiente de desenvolvimento local:

Ao executar `python run.py`:
1. **Docker Compose**: Detecta a versão do Docker Compose disponível (`docker compose` ou `docker-compose`) e sobe os containers do PostgreSQL, Redis e pgAdmin em background (`up -d`).
2. **Aguardar DB**: Aguarda a inicialização do PostgreSQL.
3. **Migrations**: Executa automaticamente `alembic upgrade head` via subprocesso com o Python ativo no ambiente virtual.
4. **FastAPI Server**: Inicia o servidor Uvicorn com hot-reload ativo na porta `8000`.
5. **Auto-Clean**: Ao receber `Ctrl+C`, captura o encerramento e executa automaticamente `docker compose down`.
