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
5. [Endpoints — M1 (Infraestrutura)](#5-endpoints--m1-infraestrutura)
6. [Endpoints — M2 (Autenticação e Gestão de Contas)](#6-endpoints--m2-autenticação-e-gestão-de-contas)

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

O sistema utiliza **JSON Web Tokens (JWT)** com o algoritmo **HS256** para autenticação.

### 2.1. Access Token (Token de Acesso)

Token de curta duração usado para autenticar cada requisição.

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
  "email": "joao@exemplo.com",
  "role": "aluno",
  "iat": 1719835200,
  "exp": 1719838800
}
```

| Campo  | Tipo     | Descrição                                                        |
| ------ | -------- | ---------------------------------------------------------------- |
| `sub`  | `string` | UUID do usuário (subject)                                        |
| `email`| `string` | E-mail do usuário                                                |
| `role` | `string` | Nível de acesso: `"aluno"`, `"coordenador"` ou `"admin"`         |
| `iat`  | `number` | Timestamp Unix de quando o token foi emitido (issued at)         |
| `exp`  | `number` | Timestamp Unix de expiração (padrão: 60 minutos após emissão)    |

**Expiração:** 60 minutos (configurável via `ACCESS_TOKEN_EXPIRE_MINUTES` no `.env`)

### 2.2. Refresh Token (Token de Atualização)

Token de longa duração usado exclusivamente para obter um novo Access Token sem exigir novo login.

- **Expiração:** 7 dias
- **Armazenamento no Frontend:** `httpOnly cookie` ou `localStorage` (a definir com o time de front)
- **Rotação:** A cada uso do refresh token, um novo par (access + refresh) é gerado e o anterior é invalidado

### 2.3. Fluxo de Uso

```
1. Usuário faz login  →  Recebe access_token + refresh_token
2. Frontend envia requisições com:  Authorization: Bearer <access_token>
3. Access token expira  →  Frontend chama POST /auth/refresh com o refresh_token
4. Recebe novo par de tokens  →  Continua operando normalmente
5. Refresh token expira  →  Usuário precisa fazer login novamente
```

### 2.4. Como o Frontend Deve Enviar o Token

Todas as rotas protegidas exigem o header:

```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIi...
```

---

## 3. Padrão de Respostas de Erro

Todos os erros da API retornam um JSON com a seguinte estrutura:

```json
{
  "mensagem": "Descrição legível do erro."
}
```

**Interface TypeScript equivalente:**
```typescript
interface ErroPadrao {
  mensagem: string;
}
```

---

## 4. Códigos HTTP Utilizados

| Código | Significado                | Quando é usado                                          |
| ------ | -------------------------- | ------------------------------------------------------- |
| `200`  | OK                         | Requisição processada com sucesso                       |
| `201`  | Created                    | Recurso criado com sucesso (ex: novo usuário)           |
| `400`  | Bad Request                | Dados inválidos ou não atendem regras de negócio        |
| `401`  | Unauthorized               | Token ausente, expirado ou credenciais incorretas       |
| `403`  | Forbidden                  | Usuário autenticado mas sem permissão para o recurso    |
| `409`  | Conflict                   | Conflito de dados (e-mail ou matrícula já cadastrados)  |
| `422`  | Unprocessable Entity       | Erro de validação de formato nos campos enviados        |

---

## 5. Endpoints — M1 (Infraestrutura)

### `GET /health`

> Verifica se a API está no ar.

**Autenticação:** Não requer

**Response (200):**
```json
{
  "status": "healthy"
}
```

---

## 6. Endpoints — M2 (Autenticação e Gestão de Contas)

### 6.1. `POST /auth/register`

> Cadastrar novo usuário no sistema.

**Autenticação:** Não requer

**Request Body:**
```json
{
  "nome_completo": "João Silva",
  "email": "joao@exemplo.com",
  "senha": "SenhaForte123!",
  "data_nascimento": "2000-01-01",
  "matricula": "512345",
  "curso_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"
}
```

| Campo            | Tipo     | Obrigatório | Descrição                        |
| ---------------- | -------- | ----------- | -------------------------------- |
| `nome_completo`  | `string` | ✅          | Nome completo do usuário          |
| `email`          | `string` | ✅          | E-mail válido (formato validado)  |
| `senha`          | `string` | ✅          | Mínimo 8 caracteres, com números e símbolos |
| `data_nascimento`| `string` | ✅          | Formato `YYYY-MM-DD`             |
| `matricula`      | `string` | ✅          | Matrícula universitária (única)   |
| `curso_id`       | `string` | ✅          | UUID do curso acadêmico           |

**Response (201):**
```json
{
  "mensagem": "Usuário registrado com sucesso.",
  "token_acesso": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIi...signature",
  "tipo_token": "bearer",
  "token_atualizacao": "def50200543e332...",
  "usuario": {
    "nome_completo": "João Silva",
    "email": "joao@exemplo.com",
    "matricula": "512345",
    "data_nascimento": "2000-01-01",
    "data_ingresso": "2024-05-20",
    "meta_horas_semanais": 12,
    "foto_perfil": "avatar_padrao.png",
    "curso_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "status_id": "1fa85f64-5717-4562-b3fc-2c963f66afa1"
  }
}
```

**Erros possíveis:**

| Código | Cenário                   | Exemplo de mensagem                                               |
| ------ | ------------------------- | ----------------------------------------------------------------- |
| `400`  | Senha fraca               | `"A senha deve conter no mínimo 8 caracteres, incluindo números e símbolos."` |
| `400`  | Formato inválido          | `"O formato do e-mail é inválido."`                                |
| `409`  | E-mail duplicado          | `"Este e-mail já está cadastrado no sistema."`                     |
| `409`  | Matrícula duplicada       | `"Esta matrícula já pertence a outro usuário."`                    |

---

### 6.2. `POST /auth/login`

> Autenticar usuário e obter tokens de acesso.

**Autenticação:** Não requer

**Request Body:**
```json
{
  "email": "joao@exemplo.com",
  "senha": "SenhaForte123!"
}
```

| Campo   | Tipo     | Obrigatório | Descrição           |
| ------- | -------- | ----------- | ------------------- |
| `email` | `string` | ✅          | E-mail do usuário    |
| `senha` | `string` | ✅          | Senha do usuário     |

**Response (200):**
```json
{
  "mensagem": "Login realizado com sucesso.",
  "token_acesso": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIi...signature",
  "tipo_token": "bearer",
  "token_atualizacao": "def50200543e332...",
  "usuario": {
    "nome_completo": "João Silva",
    "email": "joao@exemplo.com",
    "matricula": "512345",
    "data_nascimento": "2000-01-01",
    "data_ingresso": "2024-05-20",
    "meta_horas_semanais": 12,
    "foto_perfil": "avatar_padrao.png",
    "curso_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "status_id": "1fa85f64-5717-4562-b3fc-2c963f66afa1"
  }
}
```

**Erros possíveis:**

| Código | Cenário                   | Exemplo de mensagem                                    |
| ------ | ------------------------- | ------------------------------------------------------ |
| `400`  | Campos ausentes           | `"Os campos de e-mail e senha são obrigatórios."`       |
| `401`  | Credenciais inválidas     | `"E-mail ou senha incorretos. Tente novamente."`        |

---

### 6.3. `POST /auth/logout`

> Encerrar sessão do usuário (invalidar refresh token).

**Autenticação:** 🔒 Requer `Authorization: Bearer <token>`

**Request Body:** Nenhum

**Response (200):**
```json
{
  "mensagem": "Sessão encerrada com sucesso."
}
```

**Erros possíveis:**

| Código | Cenário                   | Exemplo de mensagem                              |
| ------ | ------------------------- | ------------------------------------------------ |
| `401`  | Não autenticado           | `"Token de acesso ausente ou inválido."`          |

---

### 6.4. `POST /auth/refresh`

> Renovar o token de acesso usando o refresh token.

**Autenticação:** Não requer (usa o refresh token no body)

**Request Body:**
```json
{
  "token_atualizacao": "def50200543e332..."
}
```

| Campo               | Tipo     | Obrigatório | Descrição                              |
| ------------------- | -------- | ----------- | -------------------------------------- |
| `token_atualizacao` | `string` | ✅          | Refresh token obtido no login/registro  |

**Response (200):**
```json
{
  "mensagem": "Token renovado com sucesso.",
  "token_acesso": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIi...novoToken",
  "tipo_token": "bearer",
  "token_atualizacao": "ghi78900novoRefreshToken..."
}
```

**Erros possíveis:**

| Código | Cenário                   | Exemplo de mensagem                                          |
| ------ | ------------------------- | ------------------------------------------------------------ |
| `401`  | Token expirado            | `"O refresh token expirou. Faça login novamente."`            |
| `401`  | Token inválido            | `"Refresh token inválido ou já utilizado."`                   |

---

### 6.5. `POST /auth/forgot-password`

> Solicitar recuperação de senha (envio de código por e-mail).

**Autenticação:** Não requer

**Request Body:**
```json
{
  "email": "joao@exemplo.com"
}
```

| Campo   | Tipo     | Obrigatório | Descrição                          |
| ------- | -------- | ----------- | ---------------------------------- |
| `email` | `string` | ✅          | E-mail cadastrado do usuário        |

**Response (200):**
```json
{
  "mensagem": "Se o e-mail estiver cadastrado, um código de 6 dígitos foi enviado."
}
```

> **Nota de segurança:** A API sempre retorna 200, mesmo se o e-mail não existir no banco, para não revelar quais e-mails estão cadastrados.

**Erros possíveis:**

| Código | Cenário          | Exemplo de mensagem                                    |
| ------ | ---------------- | ------------------------------------------------------ |
| `400`  | E-mail inválido  | `"O endereço de e-mail fornecido não é válido."`        |

---

### 6.6. `POST /auth/verify-code`

> Validar o código numérico de 6 dígitos (OTP) enviado por e-mail.

**Autenticação:** Não requer

**Request Body:**
```json
{
  "email": "joao@exemplo.com",
  "codigo": "482910"
}
```

| Campo    | Tipo     | Obrigatório | Descrição                          |
| -------- | -------- | ----------- | ---------------------------------- |
| `email`  | `string` | ✅          | E-mail cadastrado do usuário        |
| `codigo` | `string` | ✅          | Código de 6 dígitos recebido        |

**Response (200):**
```json
{
  "mensagem": "Código validado com sucesso.",
  "token_redefinicao": "abc123xyz890tokenTemporario"
}
```

**Erros possíveis:**

| Código | Cenário                     | Exemplo de mensagem                                        |
| ------ | --------------------------- | ---------------------------------------------------------- |
| `401`  | Código inválido/expirado    | `"O código inserido é inválido ou já expirou."`             |

---

### 6.7. `POST /auth/reset-password`

> Salvar nova senha usando o token de redefinição.

**Autenticação:** Não requer (usa token de redefinição no body)

**Request Body:**
```json
{
  "token_redefinicao": "abc123xyz890tokenTemporario",
  "nova_senha": "NovaSenhaSegura2026!"
}
```

| Campo               | Tipo     | Obrigatório | Descrição                                      |
| ------------------- | -------- | ----------- | ---------------------------------------------- |
| `token_redefinicao` | `string` | ✅          | Token obtido na etapa de verificação de código   |
| `nova_senha`        | `string` | ✅          | Nova senha (mínimo 8 caracteres)                 |

**Response (200):**
```json
{
  "mensagem": "Sua senha foi redefinida com sucesso. Você já pode realizar o login."
}
```

**Erros possíveis:**

| Código | Cenário            | Exemplo de mensagem                                                              |
| ------ | ------------------ | -------------------------------------------------------------------------------- |
| `400`  | Senha fraca        | `"A nova senha deve ser diferente da anterior e conter ao menos 8 caracteres."`   |
| `401`  | Token expirado     | `"Sessão de redefinição expirada. Solicite um novo código."`                      |

---

### 6.8. `PUT /auth/change-password`

> Alterar senha do usuário autenticado.

**Autenticação:** 🔒 Requer `Authorization: Bearer <token>`

**Request Body:**
```json
{
  "senha_atual": "SenhaForte123!",
  "nova_senha": "NovaSenhaSegura2026!"
}
```

| Campo         | Tipo     | Obrigatório | Descrição                              |
| ------------- | -------- | ----------- | -------------------------------------- |
| `senha_atual` | `string` | ✅          | Senha atual para confirmação            |
| `nova_senha`  | `string` | ✅          | Nova senha (mínimo 8 caracteres)        |

**Response (200):**
```json
{
  "mensagem": "Senha alterada com sucesso."
}
```

**Erros possíveis:**

| Código | Cenário                    | Exemplo de mensagem                                                              |
| ------ | -------------------------- | -------------------------------------------------------------------------------- |
| `400`  | Senha fraca                | `"A nova senha deve conter no mínimo 8 caracteres, incluindo números e símbolos."` |
| `400`  | Senha igual à anterior     | `"A nova senha deve ser diferente da senha atual."`                               |
| `401`  | Senha atual incorreta      | `"A senha atual informada está incorreta."`                                       |
| `401`  | Não autenticado            | `"Token de acesso ausente ou inválido."`                                          |

---

### 6.9. `DELETE /auth/account`

> Excluir conta permanentemente (ação irreversível).

**Autenticação:** 🔒 Requer `Authorization: Bearer <token>`

**Request Body:**
```json
{
  "senha": "SenhaForte123!"
}
```

| Campo   | Tipo     | Obrigatório | Descrição                                    |
| ------- | -------- | ----------- | -------------------------------------------- |
| `senha` | `string` | ✅          | Senha atual para confirmação da exclusão      |

**Response (200):**
```json
{
  "mensagem": "Sua conta foi excluída permanentemente."
}
```

**Erros possíveis:**

| Código | Cenário              | Exemplo de mensagem                                                       |
| ------ | -------------------- | ------------------------------------------------------------------------- |
| `401`  | Senha incorreta      | `"A senha informada está incorreta. A conta não foi excluída."`            |
| `401`  | Não autenticado      | `"Token de acesso ausente ou inválido."`                                  |

---

### 6.10. `GET /users/me`

> Obter perfil do usuário autenticado.

**Autenticação:** 🔒 Requer `Authorization: Bearer <token>`

**Request Body:** Nenhum

**Response (200):**
```json
{
  "mensagem": "Perfil obtido com sucesso.",
  "usuario": {
    "nome_completo": "João Silva",
    "email": "joao@exemplo.com",
    "matricula": "512345",
    "data_nascimento": "2000-01-01",
    "data_ingresso": "2024-05-20",
    "meta_horas_semanais": 12,
    "foto_perfil": "avatar_padrao.png",
    "curso_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "status_id": "1fa85f64-5717-4562-b3fc-2c963f66afa1"
  }
}
```

**Erros possíveis:**

| Código | Cenário           | Exemplo de mensagem                              |
| ------ | ----------------- | ------------------------------------------------ |
| `401`  | Não autenticado   | `"Token de acesso ausente ou inválido."`          |

---

### 6.11. `PUT /users/me`

> Atualizar perfil do usuário autenticado (nome e/ou avatar).

**Autenticação:** 🔒 Requer `Authorization: Bearer <token>`

**Request Body:**
```json
{
  "nome_completo": "João Pedro Silva",
  "foto_perfil": "avatar_joao_2026.png"
}
```

| Campo           | Tipo     | Obrigatório | Descrição                                  |
| --------------- | -------- | ----------- | ------------------------------------------ |
| `nome_completo` | `string` | ❌          | Novo nome (se omitido, permanece o atual)   |
| `foto_perfil`   | `string` | ❌          | Novo avatar (se omitido, permanece o atual) |

> **Nota:** Ambos os campos são opcionais. Envie apenas os que deseja alterar.

**Response (200):**
```json
{
  "mensagem": "Perfil atualizado com sucesso.",
  "usuario": {
    "nome_completo": "João Pedro Silva",
    "email": "joao@exemplo.com",
    "matricula": "512345",
    "data_nascimento": "2000-01-01",
    "data_ingresso": "2024-05-20",
    "meta_horas_semanais": 12,
    "foto_perfil": "avatar_joao_2026.png",
    "curso_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "status_id": "1fa85f64-5717-4562-b3fc-2c963f66afa1"
  }
}
```

**Erros possíveis:**

| Código | Cenário           | Exemplo de mensagem                                         |
| ------ | ----------------- | ----------------------------------------------------------- |
| `401`  | Não autenticado   | `"Token de acesso ausente ou inválido."`                     |
| `422`  | Validação         | `"O nome completo não pode ser uma string vazia."`           |

---

## Interfaces TypeScript (Referência para o Frontend)

Abaixo, as interfaces TypeScript correspondentes aos schemas do backend para facilitar a criação de tipos no frontend:

```typescript
// ── Modelos base ────────────────────────────────────────────

interface ErroPadrao {
  mensagem: string;
}

interface UsuarioCompleto {
  nome_completo: string;
  email: string;
  matricula: string;
  data_nascimento: string; // "YYYY-MM-DD"
  data_ingresso: string;   // "YYYY-MM-DD"
  meta_horas_semanais: number;
  foto_perfil: string;
  curso_id: string;        // UUID
  status_id: string;       // UUID
}

// ── Auth — Requests ─────────────────────────────────────────

interface RegisterRequest {
  nome_completo: string;
  email: string;
  senha: string;
  data_nascimento: string;
  matricula: string;
  curso_id: string;
}

interface LoginRequest {
  email: string;
  senha: string;
}

interface ForgotPasswordRequest {
  email: string;
}

interface VerifyCodeRequest {
  email: string;
  codigo: string;
}

interface ResetPasswordRequest {
  token_redefinicao: string;
  nova_senha: string;
}

interface RefreshTokenRequest {
  token_atualizacao: string;
}

interface ChangePasswordRequest {
  senha_atual: string;
  nova_senha: string;
}

interface DeleteAccountRequest {
  senha: string;
}

// ── Auth — Responses ────────────────────────────────────────

interface AuthTokenResponse {
  mensagem: string;
  token_acesso: string;
  tipo_token: string;
  token_atualizacao: string;
  usuario: UsuarioCompleto;
}

interface MensagemResponse {
  mensagem: string;
}

interface VerifyCodeResponse {
  mensagem: string;
  token_redefinicao: string;
}

interface RefreshTokenResponse {
  mensagem: string;
  token_acesso: string;
  tipo_token: string;
  token_atualizacao: string;
}

// ── Users — Requests ────────────────────────────────────────

interface UpdateProfileRequest {
  nome_completo?: string;
  foto_perfil?: string;
}

// ── Users — Responses ───────────────────────────────────────

interface UsuarioPerfilResponse {
  mensagem: string;
  usuario: UsuarioCompleto;
}
```
