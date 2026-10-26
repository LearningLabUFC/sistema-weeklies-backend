# Metodologia de Desenvolvimento e Qualidade

Este documento descreve os padrões e metodologias adotadas no Sistema Weeklies Backend para garantir uma base de código limpa, previsível e segura.

## Pragmatic TDD (Test-Driven Development Pragmático)

Em vez de focar excessivamente na cobertura microscópica de cada função isolada com *mocks* (TDD clássico/purista), o projeto adota uma abordagem de **TDD Pragmático focado em Testes de Integração e Comportamento**. 

As regras de ouro da nossa metodologia de testes são:

1. **Evitar Números e Strings Mágicos:** Valores estáticos (como UUIDs de *roles* e *status*) devem ser isolados em constantes reaproveitáveis. Nunca execute queries repetitivas nos testes para descobrir dados fixos que o sistema injeta via *seeds*.
2. **Priorizar o Caminho Real:** Sempre que possível, os testes utilizam um banco em memória (SQLite local) e Redis instanciado em modo *fake* isolado (`fakeredis`), garantindo que o sistema completo seja percorrido — do roteador ao banco de dados — simulando com máxima fidelidade o fluxo do usuário, sem realizar conexões com infraestruturas externas pesadas.
3. **Casos de Falha Importam Mais que Casos de Sucesso:** Todo desenvolvimento de rotas foca primariamente nos testes que visam **quebrar** a segurança. Se uma regra foi concebida para barrar (HTTP 401, 403, 409), o teste de integração dela tem precedência sobre o cenário feliz (HTTP 200).
4. **Isolamento Robusto:** Os testes usam o isolamento garantido pelas *fixtures* do pytest. Um teste nunca pode depender de um estado residual deixado por outro teste no banco de dados.

### Estrutura Base das Fixtures

Fixtures devem ser desenhadas para registrar fluxos inteiros do sistema de forma limpa. Exemplo da nossa abordagem em `conftest.py` ou `test_*_routes.py`:

```python
# Correto (Aproveitando a estrutura injetada no backend e gerando contextos logados reais)
@pytest.fixture
def admin_logado(client, db_session):
    return _registrar_e_logar(client, db_session, "admin@teste.com", ROLE_ADMIN)
```

## Linting e Formatação (Ruff)

Nós utilizamos o **Ruff** como motor único para substituição do Flake8, Black, isort e Pylint. 
Isso nos garante uma performance absurda na verificação e uma única fonte da verdade.

### Regras Adotadas

O projeto obedece ao `ruff.toml` que já traz:
- **E / F / W**: Regras padrão do Flake8 (erros de sintaxe e código morto).
- **I (isort):** Ordenação alfabética e categorizada dos `imports`.
- **C90 (mccabe):** Controle estrito de complexidade ciclomática.
- **RUF:** Regras próprias do motor Ruff (variáveis não utilizadas, formatação errática).
- **UP (pyupgrade):** Força o uso da sintaxe moderna do Python (type hinting avançado).

### Tolerância Zero a *Dead Code*

Qualquer *pull request* submetida não pode conter nenhuma variável declarada não utilizada (como `RUF059`). O código deve ser rigorosamente limpo ou as variáveis suprimidas com o prefixo `_` (ex: `_user, token = usuario_logado` se o `user` não for consumido pelas asserções subsequentes do teste).
