# Linting — Ruff

## O que é o Ruff?

O [Ruff](https://docs.astral.sh/ruff/) é o linter que usamos para manter a qualidade e o padrão do código Python do projeto. Ele roda automaticamente na CI (GitHub Actions) em todo Push e Pull Request para as branches `main` e `develop`.

Se o Ruff encontrar erros, a pipeline falha e o merge é bloqueado.

## Como rodar localmente

Antes de fazer um push, rode o linter na sua máquina para evitar surpresas na CI:

```bash
# Verificar erros
ruff check .

# Corrigir automaticamente o que for seguro (imports, formatação)
ruff check --fix .
```

## Configuração do projeto

A configuração do Ruff fica no arquivo `ruff.toml` na raiz do repositório.

## Regras ignoradas

### B008 — Chamadas de função em argumentos padrão

```toml
[lint]
ignore = ["B008"]
```

**O que a regra diz:** "Não faça chamadas de função nos valores padrão dos parâmetros de uma função."

**Por que ignoramos:** O FastAPI usa `Depends()` nos parâmetros das rotas como mecanismo de **injeção de dependência**. Esse é o padrão oficial do framework e está em toda a documentação do FastAPI.

```python
# Exemplo: o Ruff reclama disso, mas é o padrão do FastAPI
@router.get("/me")
async def get_my_profile(
    current_user: User = Depends(get_current_user),  # ← B008 reclamaria aqui
    db: Session = Depends(get_db),                    # ← e aqui
):
```

Em Python normal, chamar funções no valor padrão de argumentos pode causar bugs porque o valor é avaliado uma única vez (na carga do módulo). Porém, o FastAPI não usa esses valores da forma tradicional — ele inspeciona a assinatura e resolve as dependências a cada requisição HTTP.

**Referência:** [Documentação oficial do FastAPI sobre Depends](https://fastapi.tiangolo.com/tutorial/dependencies/)

### BLE001 — `except Exception` genérico (ignorado pontualmente via `noqa`)

Em alguns pontos do código usamos `except Exception` de forma **intencional** e marcamos com `# noqa: BLE001` para que o Ruff ignore apenas aquela linha. Os casos são:

| Arquivo | Motivo |
|---|---|
| `app/main.py` (health check) | Qualquer exceção indica que o banco está fora do ar. Listar cada tipo de erro possível seria impraticável. |
| `run.py` (cleanup do Docker) | Se parar os containers falhar, queremos apenas avisar e seguir em frente. |
| `scripts/create_admin.py` | Script utilitário. Qualquer erro deve fazer rollback e mostrar a mensagem. |

**O que é `noqa`?** É um comentário especial (`# noqa: CÓDIGO`) que diz ao Ruff: *"Eu sei que isso parece errado, mas é intencional. Ignore apenas esta linha."* Diferente do `ruff.toml`, que ignora uma regra no projeto inteiro, o `noqa` é cirúrgico — só se aplica à linha onde está escrito.
