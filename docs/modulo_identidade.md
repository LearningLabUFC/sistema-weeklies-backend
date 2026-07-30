# Módulo de Identidade, Autenticação e RBAC

Esta documentação descreve as regras de negócio e a arquitetura de segurança implementadas para o sistema de gestão de usuários (Módulo de Identidade).

## 1. Sistema de Status (Fluxo de Aprovação e Soft Delete)

Para manter o histórico e a integridade do banco de dados, o sistema **nunca exclui fisicamente** um usuário (`DELETE` no banco). Em vez disso, utilizamos uma tabela de `status_usuarios`.

### Status Existentes
- **`pendente`**: Status padrão para quem acaba de se registrar na plataforma (`POST /auth/register`). O usuário não consegue fazer login no sistema até que um administrador o aprove.
- **`ativo`**: O usuário foi aprovado e tem acesso livre ao sistema (autenticação JWT liberada).
- **`inativo`**: O usuário teve sua conta excluída (Soft Delete). Bloqueia imediatamente novos logins e revoga a validade conceitual da conta, sem quebrar os relatórios associados a ele.

### Regras de Negócio
- A rota `POST /auth/login` só emite tokens para usuários com status **ativo**.
- A rota `DELETE /auth/account` permite que um usuário (mediante confirmação de senha) realize o *soft delete* da própria conta.

## 2. Sistema de Cargos (RBAC - Role Based Access Control)

O controle de acesso às rotas da API é gerenciado através da tabela `cargos` (Roles), vinculada à coluna `global_role` do usuário. 

### Cargos Existentes
- **`super_admin`**: Acesso total ao sistema. Único perfil com permissão para promover/rebaixar/excluir outros administradores.
- **`admin`**: Acesso administrativo padrão. Permite visualizar usuários pendentes e aprovar novos alunos.
- **`aluno`**: Cargo padrão (atribuído automaticamente no cadastro via formulário). Possui permissões restritas apenas às suas próprias entidades.

### Implementação de Segurança
As rotas são protegidas utilizando a dependência `require_role(allowed_roles)`. 
Por exemplo, uma rota decorada com `Depends(require_role(["super_admin", "admin"]))` bloqueará automaticamente (HTTP 403 Forbidden) qualquer requisição cujo token pertença a um `aluno`.

## 3. Administração do Sistema

Foi criado um Router exclusivo para Administração (`/admin`), protegido pelas regras de RBAC acima.

### Endpoints de Administração
- **`GET /admin/users/pending`** *(Requer `admin` ou `super_admin`)*: Retorna a lista de todos os usuários com status `pendente`.
- **`PATCH /admin/users/{user_id}/status`** *(Requer `admin` ou `super_admin`)*: Altera o status do usuário (ex: de `pendente` para `ativo`). Um `admin` normal é bloqueado pela API caso tente alterar o status de um `super_admin`.
- **`DELETE /admin/users/{user_id}`** *(Requer `super_admin`)*: Exclui (soft delete) qualquer usuário do sistema.

## 4. O Problema do Primeiro Administrador ("Ovo e a Galinha")

Uma vez que apenas administradores podem aprovar usuários, e o banco inicial não possui administradores, foi criado um utilitário CLI para gerar o administrador raiz.

### Como gerar o Super Admin
Sempre que o banco de dados for limpo (ou na primeira instalação), o desenvolvedor deve rodar o script localmente no terminal:

```bash
.venv/bin/python scripts/create_admin.py
```

**Resultado:**
O sistema irá forçar a inserção no banco de dados de uma conta:
- **Email:** `admin@learninglab.com.br`
- **Senha:** `Admin@123`
- **Role:** `super_admin`
- **Status:** `ativo`

A partir dessa conta inicial, o gestor poderá fazer login e começar a aprovar os alunos que se registrarem pelo sistema.

## 5. Alteração de Senhas (Segurança)

- **Mudança Voluntária:** A troca de senha deve ser feita obrigatoriamente pela rota `PUT /auth/change-password`. Essa rota foi blindada para exigir que a `senha_atual` correta seja informada.
- O endpoint genérico de atualização de perfil (`PUT /users/me`) **não processa alterações de senha**, evitando a vulnerabilidade de atualização não autorizada caso uma sessão fique aberta.
