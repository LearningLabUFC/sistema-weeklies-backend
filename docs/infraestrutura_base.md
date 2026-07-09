# Documentação da Infraestrutura Base da API

Esta documentação detalha a infraestrutura básica da API desenvolvida para o **Sistema de Gestão LL**. O objetivo desta infraestrutura é fornecer um ambiente de desenvolvimento padronizado, integrado com o banco de dados PostgreSQL e com suporte para migrações automáticas de esquema.

---

## 1. Configuração e Variáveis de Ambiente (`app/config.py`)

A leitura e validação das variáveis de ambiente são gerenciadas centralizadamente pelo módulo `app/config.py` utilizando o **`pydantic-settings`**.

* **Arquivo `.env`**: Centraliza as credenciais e configurações locais.
* **Validação Automática**: Ao iniciar a API, o Pydantic garante que todas as variáveis obrigatórias existam e tenham os tipos corretos (ex: `POSTGRES_PORT` como inteiro).
* **`DATABASE_URL`**: É montada dinamicamente via propriedade no código, evitando dependências de interpolação no arquivo de ambiente.
* **Configuração de Extras**: O Pydantic está configurado com `extra="ignore"`, permitindo que variáveis de outras ferramentas (como o pgAdmin no `docker-compose.yml`) coexistam no `.env` sem causar erros de validação na inicialização da aplicação.

---

## 2. Banco de Dados e Conexão (`app/database.py`)

A persistência de dados utiliza o ORM **SQLAlchemy** e o driver **Psycopg2** para conexão com o PostgreSQL.

* **Engine**: Criada com a URL de conexão validada. Utiliza `pool_pre_ping=True` para descartar automaticamente conexões inativas antes de cada consulta, evitando erros comuns de conexão caída.
* **SessionLocal**: Fábrica de sessões configurada para não utilizar `autocommit` ou `autoflush` automáticos, garantindo maior controle transacional.
* **Base Declarativa**: Classe base `Base` da qual todos os modelos ORM devem herdar.
* **Injeção de Dependência (`get_db`)**: Uma dependência FastAPI que abre uma nova sessão de banco de dados por requisição HTTP e garante o fechamento (`db.close()`) após o término da resposta.

---

## 3. Modelo ORM Inicial (`app/models/user.py`)

Foi mapeado o modelo de dados inicial da aplicação, representando a tabela `usuarios`:

* **Colunas**: Mapeamento direto do schema `UsuarioCompleto` da API, incluindo chaves primárias UUID geradas automaticamente, e chaves únicas indexadas (`email` e `matricula`).
* **Senha**: O campo `senha_hash` armazena a senha criptografada do usuário.
* **IDs Referenciais**: Os campos `curso_id`, `status_id` e `global_role` foram mantidos como colunas de UUID simples por enquanto, prontas para serem convertidas em chaves estrangeiras (`ForeignKey`) assim que as respectivas tabelas de suporte forem implementadas.

---

## 4. Gerenciador de Migrações (`Alembic`)

O **Alembic** é utilizado para gerenciar as alterações de esquema no banco de dados.

* **Inicialização**: A pasta `alembic/` e o arquivo `alembic.ini` contêm as configurações de migrações.
* **Conexão Dinâmica**: O script `alembic/env.py` foi configurado para importar as configurações da aplicação (`app.config.settings`) e ler a string de conexão direto de lá.
* **Carregamento de Modelos**: O pacote `app.models` é importado no `env.py` para garantir que o SQLAlchemy registre as tabelas na metadata (`Base.metadata`), permitindo a autogeração automática de novas revisões com `alembic revision --autogenerate`.

---

## 5. Criptografia de Senhas (`app/utils/security.py`)

A segurança de credenciais utiliza a biblioteca **`bcrypt`** de forma direta:

* **`hash_senha(senha: str)`**: Codifica e gera um salt aleatório para a senha plana, retornando o hash em string para armazenamento.
* **`verificar_senha(senha_plana: str, senha_hash: str)`**: Compara de forma segura a senha fornecida pelo cliente com o hash gravado no banco de dados.
* *Nota*: A integração direta com o `bcrypt` contorna problemas de compatibilidade conhecidos do pacote antigo `passlib` com versões modernas do Python.

---

## 6. Verificação de Saúde (`/api/health`)

A rota de health check foi configurada no endpoint `/api/health` e implementa:
* **Validação do Servidor**: Retorna se o servidor FastAPI está operacional.
* **Validação do Banco de Dados**: Executa uma query de teste simples (`SELECT 1`). Caso o banco esteja fora do ar, o endpoint responde com status HTTP `503 Service Unavailable` e detalha a desconexão no JSON de retorno.

---

## 7. Script de Inicialização Automatizado (`run.py`)

Para unificar o setup de desenvolvimento local entre diferentes sistemas operacionais (Windows, macOS e Linux), foi criado o script helper `run.py` na raiz do projeto.

Ao executar `python run.py`:
1. **Docker Compose**: O script detecta a versão do Docker Compose instalada (`docker compose` ou `docker-compose`) e sobe os containers do PostgreSQL e pgAdmin em segundo plano (`up -d`).
2. **Aguardar DB**: Aguarda alguns segundos para garantir que o PostgreSQL esteja pronto para aceitar conexões.
3. **Migrations**: Executa automaticamente as migrações do Alembic (`alembic upgrade head`) utilizando o interpretador Python do ambiente virtual ativo.
4. **FastAPI Server**: Inicia o servidor de desenvolvimento Uvicorn com hot-reload habilitado na porta `8000`.
5. **Auto-Clean**: Ao encerrar o servidor (com `Ctrl+C`), o script captura o sinal de parada e executa automaticamente `docker compose down` para desligar os containers e liberar os recursos do sistema.
