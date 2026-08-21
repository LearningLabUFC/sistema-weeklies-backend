# Módulo de Identidade, Autenticação e RBAC

Esta documentação descreve as regras de negócio e a arquitetura de segurança implementadas para o sistema de gestão de usuários (Módulo de Identidade).

---

## 1. Sistema de Status (Fluxo de Aprovação e Soft Delete)

Para manter o histórico e a integridade referencial do banco de dados, o sistema **nunca exclui fisicamente** um usuário (`DELETE` no banco). Em vez disso, utilizamos a tabela `status_usuarios`.

### Status Existentes
- **`pendente`**: Status padrão atribuído a quem se registra na plataforma (`POST /auth/register`). O usuário aguarda aprovação de um administrador.
- **`ativo`**: O usuário está aprovado e com acesso regular ao sistema (autenticação JWT liberada).
- **`inativo`**: O usuário teve sua conta desativada (Soft Delete). Bloqueia autenticações e revoga a validade conceitual da conta, sem quebrar os relatórios ou históricos associados a ele.

### Regras de Negócio
- A rota `POST /auth/login` bloqueia autenticações de contas com status **inativo**.
- A rota `DELETE /auth/account` permite que o próprio usuário autenticado (mediante confirmação de senha) realize o *soft delete* da sua conta.

---

## 2. Sistema de Cargos (RBAC - Role Based Access Control)

O controle de acesso às rotas da API é gerenciado através da tabela `cargos` (Roles), vinculada à coluna `global_role` do usuário. 

### Cargos Existentes
- **`super_admin`**: Acesso irrestrito ao sistema. Único perfil com permissão para inativar qualquer membro e alterar cargos de outros administradores.
- **`admin`**: Acesso administrativo padrão. Permite visualizar usuários, aprovar pendentes e alterar cargos de alunos.
- **`aluno`**: Cargo padrão (atribuído automaticamente no cadastro). Possui permissões restritas apenas às suas próprias entidades.

### Implementação de Segurança
As rotas são protegidas utilizando a dependência FastAPI `require_role(allowed_roles)` em conjunto com `get_current_user`. 
Por exemplo, uma rota decorada com `Depends(require_role(["super_admin", "admin"]))` bloqueará automaticamente com HTTP `403 Forbidden` qualquer requisição cujo usuário logado seja um `aluno`.

---

## 3. Administração do Sistema (`/admin`)

O router `/admin` centraliza os endpoints protegidos para gestão da equipe:

### Endpoints de Administração
- **`GET /admin/users`** *(Requer `admin` ou `super_admin`)*: Listagem paginada (`pagina`, `limite`), com filtros por status (`status`), cargo (`role`) e busca textual case-insensitive por nome ou e-mail (`busca`). Retorna os dados com nomes resolvidos das relações (`curso_nome`, `status_nome`, `role_nome`).
- **`GET /admin/users/pending`** *(Requer `admin` ou `super_admin`)*: Retorna a lista de usuários com status `pendente` aguardando moderação.
- **`PATCH /admin/users/{user_id}/status`** *(Requer `admin` ou `super_admin`)*: Altera o status do usuário (ex: de `pendente` para `ativo` ou `inativo`). Um `admin` comum é bloqueado caso tente alterar o status de um `super_admin`.
- **`PATCH /admin/users/{user_id}/role`** *(Requer `admin` ou `super_admin`)*: Altera o cargo de um membro (`super_admin`, `admin`, `aluno`).
  - *Proteções implementadas:* Proíbe auto-rebaixamento, impede que `admin` comum altere `super_admin`, exige que o usuário esteja ativo e impede o rebaixamento caso reste apenas 1 administrador ativo no sistema.
- **`DELETE /admin/users/{user_id}`** *(Requer `super_admin`)*: Inativa (soft delete) qualquer usuário ou administrador no sistema.

---

## 4. O Problema do Primeiro Administrador ("Ovo e a Galinha")

Como apenas administradores podem aprovar usuários, e o banco inicial não possui administradores, foi criado um utilitário CLI para gerar o administrador raiz.

### Como gerar o Super Admin
Sempre que o banco de dados for limpo (ou na primeira instalação), execute o script localmente no terminal:

```bash
.venv/bin/python scripts/create_admin.py
```

**Resultado:**
O sistema insere no banco de dados a conta:
- **Email:** `admin@learninglab.com.br`
- **Senha:** `Admin@123`
- **Role:** `super_admin`
- **Status:** `ativo`

A partir dessa conta inicial, o gestor pode fazer login e aprovar novos registros.

---

## 5. Alteração de Senhas e Invalidação de Tokens

- **Mudança Voluntária:** A troca de senha deve ser feita obrigatoriamente pela rota `PUT /auth/change-password`, exigindo a `senha_atual` correta e validando complexidade da `nova_senha`.
- **Invalidação Automática de Sessões:** Ao alterar a senha, a coluna `senha_atualizada_em` do usuário é atualizada com o timestamp atual. A dependência `get_current_user` valida se o token JWT (`iat`) foi emitido após a última troca de senha; tokens antigos são automaticamente rejeitados com `401 Unauthorized`.
- O endpoint de perfil (`PUT /users/me`) **não processa alterações de senha**, mitigando riscos em sessões abertas.

---

## 6. Recuperação de Senha (Fluxo OTP com Redis)

O fluxo de recuperação de senha utiliza códigos de uso único (OTP) armazenados no Redis, sem expor tokens de redefinição no banco de dados relacional.

### Etapas do Fluxo
1. **Solicitação (`POST /auth/forgot-password`)**: O usuário informa seu e-mail. A API gera um código numérico de 6 dígitos via `secrets.choice` e o salva no Redis sob a chave `otp:{email}` com TTL de **15 minutos**. O envio de e-mail ocorre em background via SMTP.
2. **Rate Limiting na Solicitação**:
   - Limite por e-mail: máximo de 3 requisições a cada 15 minutos.
   - Limite global por IP: máximo de 10 requisições a cada 15 minutos.
   - Resposta genérica (200 OK) mesmo que o e-mail não exista para impedir enumeração de usuários.
3. **Verificação (`POST /auth/verify-code`)**: O usuário envia o e-mail e o código de 6 dígitos.
   - *Anti Brute-force:* Limite de 5 tentativas incorretas. Ao atingir o limite, o OTP é destruído e um cooldown de 15 minutos é aplicado.
   - *Sucesso:* O código é deletado imediatamente do Redis (uso único) e um Token JWT de Redefinição (com validade de 5 minutos e tipo `redefinicao`) é retornado.
4. **Redefinição (`POST /auth/reset-password`)**: O usuário submete o Token JWT de Redefinição e a nova senha. A API decodifica o JWT, valida o tipo `redefinicao` e atualiza a senha no PostgreSQL.
