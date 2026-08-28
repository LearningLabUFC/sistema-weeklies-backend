# Contrato da API — Sistema de Gestão LL

> **Versão:** 1.0.0  
> **Base URL:** `http://localhost:8000`  
> **Documentação Interativa (Swagger):** `http://localhost:8000/docs`  
> **Formato de Dados:** JSON (`application/json`)

---

## Índice

1. [Convenções Gerais](#1-convenções-gerais)
2. [Autenticação JWT](#2-autenticação-jwt)
3. [Padrão de Respostas de Erro](#3-padrão-de-respostas-de-erro)
4. [Códigos HTTP Utilizados](#4-códigos-http-utilizados)
5. [Endpoints — Infraestrutura e Saúde](#5-endpoints--infraestrutura-e-saúde)
6. [Endpoints — Autenticação e Identidade (`/auth`)](#6-endpoints--autenticação-e-identidade-auth)
7. [Endpoints — Perfil do Usuário (`/users`)](#7-endpoints--perfil-do-usuário-users)
8. [Endpoints — Dados Gerais de Domínio (`/domain`)](#8-endpoints--dados-gerais-de-domínio-domain)
9. [Endpoints — Administração e RBAC (`/admin`)](#9-endpoints--administração-e-rbac-admin)
10. [Interfaces TypeScript (Referência para o Frontend)](#10-interfaces-typescript-referência-para-o-frontend)

---

## 1. Convenções Gerais

| Item                  | Padrão                                                  |
| --------------------- | ------------------------------------------------------- |
| Formato de datas      | `YYYY-MM-DD` (ISO 8601)                                 |
| IDs de entidades      | UUID v4 (`3fa85f64-5717-4562-b3fc-2c963f66afa6`)         |
| Idioma dos campos     | Português (ex: `nome_completo`, `token_acesso`)          |
| Nomenclatura de rotas | Kebab-case em inglês (ex: `/auth/forgot-password`)       |
| Content-Type          | `application/json` em todas as requisições com body      |
| Autenticação          | Header `Authorization: Bearer <token_acesso>`            |

---

## 2. Autenticação JWT

O sistema utiliza **JSON Web Tokens (JWT)** com o algoritmo **HS256** para autenticação stateless.

### 2.1. Access Token (Token de Acesso)

Token de curta duração utilizado para autenticar cada requisição a rotas protegidas.

**Header:**
```json
{
  "alg": "HS256",
  "typ": "JWT"
}
```

**Payload:**
```json
{
  "sub": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "tipo": "acesso",
  "iat": 1719835200,
  "exp": 1719838800
}
```

| Campo  | Tipo     | Descrição                                                              |
| ------ | -------- | ---------------------------------------------------------------------- |
| `sub`  | `string` | UUID do usuário no banco de dados                                       |
| `tipo` | `string` | Identificador do tipo do token (`"acesso"`)                             |
| `iat`  | `number` | Timestamp Unix de emissão (*issued at*)                                |
| `exp`  | `number` | Timestamp Unix de expiração (padrão: 60 minutos após emissão)           |

> **Nota sobre permissões:** O backend valida o cargo (`global_role`) e o status da conta (`ativo`) consultando o banco de dados via injeção de dependência (`get_current_user` / `require_role`), garantindo que mudanças de permissões ou inativações de conta tenham efeito imediato.

### 2.2. Refresh Token (Token de Atualização)

Token de longa duração usado para obter um novo par de tokens sem exigir novas credenciais de login.

- **Expiração:** 7 dias
- **Payload:** contém `"tipo": "atualizacao"` e `"sub": "<user_id>"`
- **Armazenamento no Frontend:** `localStorage` ou `httpOnly cookie`

### 2.3. Fluxo de Autenticação

```text
1. Login/Registro  → Frontend recebe token_acesso + token_atualizacao + dados do usuário
2. Requisições     → Frontend envia: Authorization: Bearer <token_acesso>
3. Token expirado  → Frontend chama POST /auth/refresh enviando o token_atualizacao
4. Logout          → Frontend descarta os tokens do armazenamento local
```

---

## 3. Padrão de Respostas de Erro

Todos os erros da API retornam um JSON com a seguinte estrutura padronizada:

```json
{
  "mensagem": "Descrição legível do erro."
}
```

---

## 4. Códigos HTTP Utilizados

| Código | Significado           | Quando é usado                                                              |
| ------ | --------------------- | --------------------------------------------------------------------------- |
| `200`  | OK                    | Requisição processada com sucesso                                           |
| `201`  | Created               | Recurso criado com sucesso (ex: novo usuário)                               |
| `400`  | Bad Request           | Dados inválidos ou não atendem regras de negócio (ex: senha fraca)           |
| `401`  | Unauthorized          | Token ausente/inválido ou credenciais incorretas                            |
| `403`  | Forbidden             | Usuário autenticado mas sem permissão de cargo (RBAC) ou ação não permitida  |
| `404`  | Not Found             | Recurso não encontrado (ex: usuário inexistente)                            |
| `409`  | Conflict              | Conflito de dados únicos (e-mail ou matrícula duplicados, regras de admin)  |
| `422`  | Unprocessable Entity  | Erro de validação de formato e campos pelo Pydantic                         |
| `429`  | Too Many Requests     | Limite de taxa atingido (rate limiting por IP/e-mail ou cooldown OTP)       |
| `503`  | Service Unavailable   | Serviço indisponível (ex: banco de dados desconectado no health check)      |

---

## 5. Endpoints — Infraestrutura e Saúde

### `GET /api/health`

> Verifica a integridade da aplicação FastAPI e a conectividade com o banco de dados PostgreSQL.

**Autenticação:** Não requer

**Response (200 OK):**
```json
{
  "status": "healthy",
  "database": "connected"
}
```

**Response (503 Service Unavailable):**
```json
{
  "status": "unhealthy",
  "database": "disconnected",
  "error": "detalhes do erro de conexão"
}
```

---

## 6. Endpoints — Autenticação e Identidade (`/auth`)

### 6.1. `POST /auth/register`

> Registra um novo membro na plataforma. O usuário é criado com status `pendente` e role `aluno`.

**Autenticação:** Não requer

**Request Body:**
```json
{
  "nome_completo": "João Silva",
  "email": "joao@exemplo.com",
  "senha": "SenhaForte123!",
  "data_nascimento": "2000-01-01",
  "matricula": "512345",
  "curso_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "meta_horas_semanais": 12
}
```

| Campo                  | Tipo     | Obrigatório | Descrição                                                    |
| ---------------------- | -------- | ----------- | ------------------------------------------------------------ |
| `nome_completo`        | `string` | ✅          | Nome completo do usuário                                     |
| `email`                | `string` | ✅          | E-mail válido                                                |
| `senha`                | `string` | ✅          | Mínimo 8 caracteres (maiúscula, minúscula, número e símbolo) |
| `data_nascimento`      | `string` | ✅          | Formato `YYYY-MM-DD`                                         |
| `matricula`            | `string` | ✅          | Matrícula universitária única                                |
| `curso_id`             | `string` | ✅          | UUID do curso acadêmico                                      |
| `meta_horas_semanais` | `int`    | ✅          | Carga horária semanal obrigatória (ex: 12)                    |

**Response (201 Created):**
```json
{
  "mensagem": "Usuário registrado com sucesso. Aguardando aprovação do administrador.",
  "token_acesso": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "tipo_token": "bearer",
  "token_atualizacao": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "usuario": {
    "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "nome_completo": "João Silva",
    "email": "joao@exemplo.com",
    "matricula": "512345",
    "data_nascimento": "2000-01-01",
    "data_ingresso": "2026-08-21",
    "meta_horas_semanais": 12,
    "foto_perfil": "avatar_padrao.png",
    "curso_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "status_id": "1fa85f64-5717-4562-b3fc-2c963f66afa1",
    "global_role": "2fa85f64-5717-4562-b3fc-2c963f66afa3"
  }
}
```

**Erros possíveis:**
- `400`: Senha fraca ou dados com formato inválido.
- `409`: E-mail ou matrícula já cadastrados.

---

### 6.2. `POST /auth/login`

> Autentica o usuário e retorna os tokens de acesso e dados do perfil.

**Autenticação:** Não requer

**Request Body:**
```json
{
  "email": "joao@exemplo.com",
  "senha": "SenhaForte123!"
}
```

**Response (200 OK):**
```json
{
  "mensagem": "Login realizado com sucesso.",
  "token_acesso": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "tipo_token": "bearer",
  "token_atualizacao": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "usuario": {
    "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "nome_completo": "João Silva",
    "email": "joao@exemplo.com",
    "matricula": "512345",
    "data_nascimento": "2000-01-01",
    "data_ingresso": "2024-05-20",
    "meta_horas_semanais": 12,
    "foto_perfil": "avatar_padrao.png",
    "curso_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "status_id": "1fa85f64-5717-4562-b3fc-2c963f66afa1",
    "global_role": "2fa85f64-5717-4562-b3fc-2c963f66afa3"
  }
}
```

**Erros possíveis:**
- `401`: Credenciais incorretas ou conta com status `inativo`.

---

### 6.3. `POST /auth/logout`

> Ponto de contato da API para encerramento de sessão do cliente. Em arquitetura JWT stateless, o frontend descarta os tokens locais.

**Autenticação:** Não requer

**Response (200 OK):**
```json
{
  "mensagem": "Sessão encerrada com sucesso."
}
```

---

### 6.4. `POST /auth/refresh`

> Renova o token de acesso utilizando o refresh token.

**Autenticação:** Não requer (envia o refresh token no corpo)

**Request Body:**
```json
{
  "token_atualizacao": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Response (200 OK):**
```json
{
  "mensagem": "Token renovado com sucesso.",
  "token_acesso": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "tipo_token": "bearer",
  "token_atualizacao": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

---

### 6.5. `POST /auth/forgot-password`

> Solicita a recuperação de senha gerando um código OTP de 6 dígitos enviado por e-mail (armazenado no Redis com TTL de 15 minutos).

**Autenticação:** Não requer  
**Rate Limit:** Máximo de 3 solicitações por e-mail a cada 15 min e 10 solicitações por IP a cada 15 min.

**Request Body:**
```json
{
  "email": "joao@exemplo.com"
}
```

**Response (200 OK):**
```json
{
  "mensagem": "Se o e-mail estiver cadastrado, um código de 6 dígitos foi enviado."
}
```

> **Nota de Segurança:** A API sempre retorna status 200 com mensagem genérica (mesmo se o e-mail não existir) para evitar enumeração de contas por terceiros.

**Erros possíveis:**
- `429`: Limite de solicitações atingido (por IP ou por e-mail).

---

### 6.6. `POST /auth/verify-code`

> Valida o código numérico OTP de 6 dígitos. Possui proteção contra ataques de força bruta.

**Autenticação:** Não requer  
**Segurança:** Máximo de 5 tentativas incorretas. Após o limite, o código é destruído e um cooldown de 15 minutos é aplicado.

**Request Body:**
```json
{
  "email": "joao@exemplo.com",
  "codigo": "482910"
}
```

**Response (200 OK):**
```json
{
  "mensagem": "Código validado com sucesso.",
  "token_redefinicao": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Erros possíveis:**
- `401`: Código numérico inválido ou expirado.
- `429`: Limite de tentativas atingido (cooldown ativo).

---

### 6.7. `POST /auth/reset-password`

> Define uma nova senha consumindo o `token_redefinicao` (com validade de 5 minutos gerado pelo endpoint de verificação de código).

**Autenticação:** Não requer (usa token temporário no body)

**Request Body:**
```json
{
  "token_redefinicao": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "nova_senha": "NovaSenhaSegura2026!"
}
```

**Response (200 OK):**
```json
{
  "mensagem": "Sua senha foi redefinida com sucesso. Você já pode realizar o login."
}
```

**Erros possíveis:**
- `400`: A nova senha não atende aos requisitos de segurança ou é idêntica à senha atual.
- `401`: Token de redefinição expirado ou inválido.

---

### 6.8. `PUT /auth/change-password`

> Altera a senha do usuário autenticado, exigindo a confirmação da senha atual.

**Autenticação:** 🔒 Requer `Authorization: Bearer <token_acesso>`

**Request Body:**
```json
{
  "senha_atual": "SenhaForte123!",
  "nova_senha": "NovaSenhaSegura2026!"
}
```

**Response (200 OK):**
```json
{
  "mensagem": "Senha alterada com sucesso."
}
```

**Erros possíveis:**
- `400`: Nova senha idêntica à atual ou fora do padrão de complexidade.
- `401`: Senha atual incorreta ou token ausente/inválido.

---

### 6.9. `DELETE /auth/account`

> Realiza o *soft delete* (desativação lógica) da conta do próprio usuário autenticado.

**Autenticação:** 🔒 Requer `Authorization: Bearer <token_acesso>`

**Request Body:**
```json
{
  "senha": "SenhaForte123!"
}
```

**Response (200 OK):**
```json
{
  "mensagem": "Sua conta foi desativada com sucesso."
}
```

**Erros possíveis:**
- `401`: Senha incorreta ou token inválido.

---

## 7. Endpoints — Perfil do Usuário (`/users`)

### 7.1. `GET /users/me`

> Retorna os dados completos do perfil do usuário autenticado.

**Autenticação:** 🔒 Requer `Authorization: Bearer <token_acesso>`

**Response (200 OK):**
```json
{
  "mensagem": "Perfil obtido com sucesso.",
  "usuario": {
    "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "nome_completo": "João Silva",
    "email": "joao@exemplo.com",
    "matricula": "512345",
    "data_nascimento": "2000-01-01",
    "data_ingresso": "2024-05-20",
    "meta_horas_semanais": 12,
    "foto_perfil": "avatar_padrao.png",
    "curso_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "status_id": "1fa85f64-5717-4562-b3fc-2c963f66afa1",
    "global_role": "2fa85f64-5717-4562-b3fc-2c963f66afa3"
  }
}
```

---

### 7.2. `PUT /users/me`

> Atualiza informações do perfil (nome, e-mail e/ou avatar). Todos os campos são opcionais.

**Autenticação:** 🔒 Requer `Authorization: Bearer <token_acesso>`

**Request Body:**
```json
{
  "nome_completo": "João Pedro Silva",
  "email": "joao.novo@exemplo.com",
  "foto_perfil": "avatar_joao_2026.png"
}
```

**Response (200 OK):**
```json
{
  "mensagem": "Perfil atualizado com sucesso.",
  "usuario": {
    "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "nome_completo": "João Pedro Silva",
    "email": "joao.novo@exemplo.com",
    "matricula": "512345",
    "data_nascimento": "2000-01-01",
    "data_ingresso": "2024-05-20",
    "meta_horas_semanais": 12,
    "foto_perfil": "avatar_joao_2026.png",
    "curso_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "status_id": "1fa85f64-5717-4562-b3fc-2c963f66afa1",
    "global_role": "2fa85f64-5717-4562-b3fc-2c963f66afa3"
  }
}
```

**Erros possíveis:**
- `401`: Token ausente ou inválido.
- `409`: O novo e-mail já pertence a outro usuário cadastrado.

---

## 8. Endpoints — Dados Gerais de Domínio (`/domain`)

### 8.1. `GET /domain/cursos`

> Lista todos os cursos acadêmicos cadastrados no sistema.

**Autenticação:** Não requer

**Response (200 OK):**
```json
[
  {
    "id": "3a9b258f-4bd4-4699-84b4-97308f32cecf",
    "nome": "Engenharia de Software",
    "ativo": true
  },
  {
    "id": "69224513-2b4e-44f6-847d-236a8a3d5cae",
    "nome": "Ciência da Computação",
    "ativo": true
  }
]
```

---

## 9. Endpoints — Administração e RBAC (`/admin`)

Todos os endpoints deste módulo exigem nível de permissão administrativo (`admin` ou `super_admin`), com exceção de deleção geral que exige `super_admin`.

### 9.1. `GET /admin/users`

> Listagem paginada e filtrável de todos os usuários com dados relacionais resolvidos (`curso_nome`, `status_nome`, `role_nome`).

**Autenticação:** 🔒 Requer cargo `admin` ou `super_admin`

**Query Parameters:**
| Parâmetro | Tipo | Padrão | Descrição |
|---|---|---|---|
| `pagina` | `int` | `1` | Número da página (inicia em 1) |
| `limite` | `int` | `20` | Itens por página (máx: 100) |
| `status` | `string` | `null` | Filtrar por status (`ativo`, `pendente`, `inativo`) |
| `role` | `string` | `null` | Filtrar por cargo (`super_admin`, `admin`, `aluno`) |
| `busca` | `string` | `null` | Busca por nome ou e-mail (case-insensitive) |

**Response (200 OK):**
```json
{
  "usuarios": [
    {
      "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "nome_completo": "João Silva",
      "email": "joao@exemplo.com",
      "matricula": "512345",
      "data_ingresso": "2024-05-20",
      "foto_perfil": "avatar_padrao.png",
      "curso_nome": "Engenharia de Software",
      "status_nome": "ativo",
      "role_nome": "aluno"
    }
  ],
  "total": 42,
  "pagina": 1,
  "limite": 20
}
```

---

### 9.2. `GET /admin/users/pending`

> Retorna a lista de usuários com cadastro pendente aguardando aprovação.

**Autenticação:** 🔒 Requer cargo `admin` ou `super_admin`

**Response (200 OK):**
```json
[
  {
    "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "nome_completo": "Maria Oliveira",
    "email": "maria@exemplo.com",
    "matricula": "512346",
    "data_nascimento": "2001-03-15",
    "data_ingresso": "2026-08-21",
    "meta_horas_semanais": 12,
    "foto_perfil": "avatar_padrao.png",
    "curso_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "status_id": "1fa85f64-5717-4562-b3fc-2c963f66afa1",
    "global_role": "2fa85f64-5717-4562-b3fc-2c963f66afa3"
  }
]
```

---

### 9.3. `PATCH /admin/users/{user_id}/status`

> Aprova ou altera o status de um usuário.

**Autenticação:** 🔒 Requer cargo `admin` ou `super_admin`  
**Regra de Segurança:** Administrador comum não pode alterar o status de um `super_admin`.

**Request Body:**
```json
{
  "novo_status": "ativo"
}
```

**Response (200 OK):**
```json
{
  "mensagem": "Status do usuário alterado para ativo com sucesso."
}
```

**Erros possíveis:**
- `400`: Status inválido (valores permitidos: `"ativo"`, `"inativo"`).
- `403`: Tentativa de alterar status de um `super_admin` por um admin comum.
- `404`: Usuário não encontrado.

---

### 9.4. `PATCH /admin/users/{user_id}/role`

> Altera o cargo de um usuário.

**Autenticação:** 🔒 Requer cargo `admin` ou `super_admin`  
**Regras de Negócio e Proteções:**
- Só é possível alterar cargo de membros com status `ativo`.
- Auto-rebaixamento é proibido (um admin não pode alterar seu próprio cargo).
- Um `admin` comum não pode alterar um `super_admin`.
- Proteção do último admin: O sistema impede o rebaixamento caso reste apenas 1 administrador ativo.

**Request Body:**
```json
{
  "role_nome": "admin"
}
```

**Response (200 OK):**
```json
{
  "mensagem": "Cargo do usuário alterado para 'admin' com sucesso."
}
```

**Erros possíveis:**
- `400`: Cargo inválido (`super_admin`, `admin`, `aluno`) ou usuário não ativo.
- `403`: Auto-alteração ou falta de privilégio para alterar outro `super_admin`.
- `404`: Usuário não encontrado.
- `409`: Tentativa de rebaixar o único administrador ativo do sistema.

---

### 9.5. `DELETE /admin/users/{user_id}`

> Inativa (soft delete) qualquer usuário ou administrador do sistema.

**Autenticação:** 🔒 Requer cargo `super_admin`

**Response (200 OK):**
```json
{
  "mensagem": "Usuário excluído (inativado) com sucesso."
}
```

---

## 10. Interfaces TypeScript (Referência para o Frontend)

```typescript
// ── Modelos Base ────────────────────────────────────────────

export interface ErroPadrao {
  mensagem: string;
}

export interface MensagemResponse {
  mensagem: string;
}

export interface UsuarioCompleto {
  id: string;              // UUID
  nome_completo: string;
  email: string;
  matricula: string;
  data_nascimento: string; // "YYYY-MM-DD"
  data_ingresso: string;   // "YYYY-MM-DD"
  meta_horas_semanais: number;
  foto_perfil: string;
  curso_id: string;        // UUID
  status_id: string;       // UUID
  global_role: string;     // UUID
}

export interface CursoResumo {
  id: string;              // UUID
  nome: string;
  ativo: boolean;
}

// ── Auth — Requests & Responses ─────────────────────────────

export interface RegisterRequest {
  nome_completo: string;
  email: string;
  senha: string;
  data_nascimento: string;
  matricula: string;
  curso_id: string;
  meta_horas_semanais: number;
}

export interface LoginRequest {
  email: string;
  senha: string;
}

export interface AuthTokenResponse {
  mensagem: string;
  token_acesso: string;
  tipo_token: string;
  token_atualizacao: string;
  usuario: UsuarioCompleto;
}

export interface ForgotPasswordRequest {
  email: string;
}

export interface VerifyCodeRequest {
  email: string;
  codigo: string;
}

export interface VerifyCodeResponse {
  mensagem: string;
  token_redefinicao: string;
}

export interface ResetPasswordRequest {
  token_redefinicao: string;
  nova_senha: string;
}

export interface ChangePasswordRequest {
  senha_atual: string;
  nova_senha: string;
}

export interface RefreshTokenRequest {
  token_atualizacao: string;
}

export interface RefreshTokenResponse {
  mensagem: string;
  token_acesso: string;
  tipo_token: string;
  token_atualizacao: string;
}

export interface DeleteAccountRequest {
  senha: string;
}

// ── Users — Requests & Responses ────────────────────────────

export interface UpdateProfileRequest {
  nome_completo?: string;
  email?: string;
  foto_perfil?: string;
}

export interface UsuarioPerfilResponse {
  mensagem: string;
  usuario: UsuarioCompleto;
}

// ── Admin — Requests & Responses ────────────────────────────

export interface UsuarioListItem {
  id: string;
  nome_completo: string;
  email: string;
  matricula: string;
  data_ingresso: string;
  foto_perfil: string;
  curso_nome: string;
  status_nome: string;
  role_nome: string;
}

export interface UsuarioListResponse {
  usuarios: UsuarioListItem[];
  total: number;
  pagina: number;
  limite: number;
}

export interface ChangeStatusRequest {
  novo_status: "ativo" | "inativo";
}

export interface ChangeRoleRequest {
  role_nome: "super_admin" | "admin" | "aluno";
}
```
