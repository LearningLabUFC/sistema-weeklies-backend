# Relatório de Auditoria de QA — Testes do Backend

**Projeto:** Sistema Weeklies — Backend  
**Auditor:** Douglas (QA)  
**Data:** 18/09/2026  
**Branch de correção:** `qa/fix-hardcoded-test-values`  
**PR:** `develop ← qa/fix-hardcoded-test-values`

---

## 1. Objetivo

Revisar a semântica, a qualidade e a robustez da suíte de testes de integração criada pelo time de desenvolvimento, garantindo que os testes:
- Validem corretamente o contrato da API (mensagens, status codes, payloads)
- Não possuam valores hardcoded que dificultam manutenção
- Sigam o padrão AAA (Arrange, Act, Assert)

---

## 2. Escopo da Auditoria

| Arquivo | Tipo | Total de Testes |
|---|---|---|
| `tests/admin/test_admin_routes.py` | Integração (rotas) | 16 |
| `tests/auth/test_auth_routes.py` | Integração (rotas) | 19 |
| `tests/auth/test_password_validation.py` | Unitário (schemas) | 13 |
| `tests/auth/test_register_validation.py` | Unitário (schemas) | 13 |
| `tests/core/test_security.py` | Unitário (segurança) | 13 |
| `tests/sectors/test_sector_routes.py` | Integração (rotas) | 21 |
| `tests/users/test_users_routes.py` | Integração (rotas) | 8 |
| `conftest.py` | Infraestrutura (fixtures) | — |
| `tests/setup_test_db.py` | Infraestrutura (DB) | — |
| **Total** | | **128 testes** |

---

## 3. Problemas Encontrados

### 3.1 🔴 UUIDs Hardcoded e Duplicados (Severidade: Média)

**Descrição:** Cada arquivo de teste (admin, auth, users, sectors) redefinia manualmente as mesmas constantes de UUID copiando e colando strings mágicas. Se o seed de Roles ou Status mudasse, seria necessário atualizar múltiplos arquivos independentes, gerando risco de inconsistência.

**Arquivos afetados:**
- `conftest.py` — UUIDs de curso e setor escritos inline
- `tests/admin/test_admin_routes.py` — 6 constantes hardcoded
- `tests/auth/test_auth_routes.py` — 2 constantes hardcoded
- `tests/users/test_users_routes.py` — 2 constantes hardcoded
- `tests/sectors/test_sector_routes.py` — 2 constantes hardcoded (CURSO e SETOR)

**Exceção positiva:** O arquivo `test_sector_routes.py` já importava `ROLES` e `STATUSES` dos seeds reais para derivar IDs de role/status. Os outros arquivos não seguiam este padrão.

**Correção aplicada:** Centralizar todas as constantes no `conftest.py` importando dos módulos `app.seeds.seed_roles` e `app.seeds.seed_status`. Todos os arquivos de teste agora fazem `from conftest import ...`.

---

### 3.2 🔴 Assertions Frouxas / Não-Semânticas (Severidade: Média-Alta)

**Descrição:** Os testes de integração usavam verificações parciais de strings com `in`, `.lower()` e `or` em vez de comparar com a mensagem exata retornada pela API. Isso permitia falsos-positivos caso a API retornasse uma mensagem diferente da esperada, mas que ainda contivesse a substring buscada.

**Exemplo do problema:**
```python
# ❌ ANTES (frouxa — aceita qualquer mensagem com "permissão" ou "Acesso negado")
assert (
    "permissão" in res.json()["detail"].lower()
    or "Acesso negado" in res.json()["detail"]
)

# ✅ DEPOIS (exata — valida o contrato da API conforme deps.py:87)
assert res.json()["detail"] == "Acesso negado. Nível de permissão insuficiente."
```

**Total de assertions corrigidas:**

| Arquivo | Assertions Corrigidas |
|---|---|
| `tests/admin/test_admin_routes.py` | 12 |
| `tests/auth/test_auth_routes.py` | 14 |
| `tests/users/test_users_routes.py` | 1 |
| `tests/sectors/test_sector_routes.py` | 3 |
| **Total** | **30** |

**Assertions mantidas com `in` (justificativa):**
- `test_verify_code_bruteforce` — Mensagem contém `settings.VERIFY_CODE_COOLDOWN_MINUTES` (dinâmica)
- `test_create_sector_admin` — Mensagem contém nome do setor via f-string
- `test_add_member_to_sector` / `test_add_leader_to_sector` — Mensagem contém papel via f-string
- `test_change_member_role` — Mensagem contém papel via f-string

---

## 4. Pontos Positivos Identificados

| Aspecto | Avaliação |
|---|---|
| **Estrutura AAA (Arrange/Act/Assert)** | ✅ Todos os testes seguem o padrão |
| **Isolamento de dados (transação + rollback)** | ✅ Implementado corretamente no `conftest.py` |
| **Fake Redis (sem dependência de infra real)** | ✅ Usado via `fakeredis` |
| **Mock de e-mail (sem SMTP real)** | ✅ `monkeypatch` global no `conftest.py` |
| **Docstrings descritivas** | ✅ Todos os testes possuem docstring explicativa |
| **Nomenclatura dos testes** | ✅ Clara e descritiva (ex: `test_change_role_auto_rebaixamento`) |
| **Cenários negativos** | ✅ Cobrem 403, 401, 400, 409, 422, 429 |
| **Testes de rate limit e bruteforce** | ✅ Cobertos com limites reais do `settings` |
| **Testes de validação de schema (Pydantic)** | ✅ Cobrem senha, matrícula, nome, data de nascimento |
| **Testes unitários de segurança (JWT, bcrypt, OTP)** | ✅ Cobrem criação, decodificação, salt e unicode |

---

## 5. Resultado Final

```
============================= 128 passed in 41.48s =============================
```

✅ **128 testes passando** após as correções — nenhuma alteração de comportamento.

---

## 6. Recomendações Futuras

| # | Recomendação | Prioridade |
|---|---|---|
| 1 | Adicionar testes de contrato para validar a estrutura completa do JSON (`assert res.json() == {...}`) nos endpoints de listagem e criação | Média |
| 2 | Criar arquivo `app/core/messages.py` centralizando todas as mensagens de erro/sucesso como constantes, e importá-las tanto nos services quanto nos testes | Baixa |
| 3 | Adicionar cobertura de testes para fluxos de concorrência (ex: dois admins alterando o mesmo usuário simultaneamente) | Baixa |
| 4 | Configurar `pytest-cov` para acompanhar a cobertura de código e definir threshold mínimo no CI | Média |
