# Módulo de Controle de Horas

Esta documentação descreve as regras de negócio, a arquitetura e os endpoints implementados no módulo de **Controle de Horas** do Sistema Weeklies Backend.

---

## 1. Objetivo do Módulo

O módulo de Controle de Horas registra e acompanha as sessões de trabalho dos membros vinculados aos setores do sistema.

Cada sessão registra:

- usuário responsável;
- setor em que o trabalho foi realizado;
- horário de entrada;
- horário de saída;
- horário de expiração;
- status atual da sessão;
- motivo de encerramento;
- pausas realizadas durante a sessão.

O tempo trabalhado **não é armazenado diretamente no banco de dados**. Ele é calculado pelo Service a partir dos horários registrados, descontando as pausas aplicáveis.

---

## 2. Arquitetura

O módulo segue a organização por funcionalidade adotada pelo backend:

```text
app/work_sessions/
├── __init__.py
├── repository.py
├── router.py
├── scheduler.py
├── schemas.py
└── service.py
```

### Responsabilidades

- **Router (`router.py`)**: recebe as requisições HTTP, aplica autenticação, valida parâmetros e encaminha a operação ao Service.
- **Service (`service.py`)**: concentra regras de negócio, permissões, transições de estado, cálculo de horas, expiração e métricas.
- **Repository (`repository.py`)**: concentra consultas e operações de persistência com SQLAlchemy.
- **Schemas (`schemas.py`)**: define os contratos de entrada e saída da API com Pydantic.
- **Scheduler (`scheduler.py`)**: processa periodicamente sessões abertas que já atingiram o horário de expiração.
- **Models (`app/models/`)**: `WorkSession` e `Pause` representam as entidades persistidas no PostgreSQL.

Fluxo principal:

```text
Usuário → Frontend → Router → Service → Repository → PostgreSQL
```

---

## 3. Modelos

### 3.1. Sessão de Trabalho (`WorkSession`)

Tabela: `sessoes_trabalho`

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | UUID | Identificador da sessão |
| `usuario_id` | UUID | Usuário responsável |
| `setor_id` | UUID | Setor da sessão |
| `entrada` | DateTime | Horário de início |
| `saida` | DateTime \| null | Horário de encerramento |
| `expiracao` | DateTime | Horário limite da sessão |
| `status` | Enum | Estado atual |
| `motivo_encerramento` | Enum \| null | Motivo do encerramento |

### 3.2. Pausa (`Pause`)

Tabela: `pausas`

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | UUID | Identificador da pausa |
| `sessao_trabalho_id` | UUID | Sessão associada |
| `inicio` | DateTime | Início da pausa |
| `fim` | DateTime \| null | Fim da pausa |

---

## 4. Estados e Motivos de Encerramento

### Status da sessão

```text
ATIVA
EM_PAUSA
FINALIZADA
EXPIRADA_SISTEMA
```

### Motivo de encerramento

```text
MANUAL
LIMITE_ATINGIDO
```

---

## 5. Regras de Negócio

### 5.1. Início da sessão

- Apenas membros e líderes podem registrar ponto.
- `admin` e `super_admin` não podem iniciar uma sessão de trabalho.
- O usuário deve possuir vínculo com o setor informado.
- O setor deve existir e estar ativo.
- Um usuário pode possuir apenas **uma sessão aberta por vez**, independentemente do setor.
- A expiração inicial é definida com base no limite configurado em `WORK_SESSION_LIMIT_HOURS`.

### 5.2. Pausas

- Apenas o próprio usuário pode iniciar ou encerrar sua pausa.
- Só é possível iniciar pausa quando a sessão está `ATIVA`.
- Uma sessão pode possuir apenas uma pausa aberta por vez.
- Ao iniciar uma pausa, a sessão passa para `EM_PAUSA`.
- Ao encerrar a pausa, a sessão volta para `ATIVA`.
- Não é permitido iniciar ou encerrar manualmente uma pausa após a expiração da sessão.
- Caso uma sessão expire com uma pausa aberta, essa pausa é encerrada automaticamente no horário de expiração.

### 5.3. Encerramento

- O encerramento manual define `status = FINALIZADA`, `motivo_encerramento = MANUAL` e `saida = horário atual`.
- Se a sessão estiver em pausa, a pausa aberta é encerrada no mesmo instante.
- Caso o usuário tente encerrar uma sessão que já atingiu o prazo, o sistema preserva o horário original de expiração e finaliza como `EXPIRADA_SISTEMA`, com motivo `LIMITE_ATINGIDO`.

### 5.4. Expiração automática

O scheduler verifica periodicamente sessões abertas cujo horário de expiração já foi atingido.

Ao expirar:

1. eventual pausa aberta é encerrada no horário de expiração;
2. `saida` recebe o horário de expiração;
3. o status passa para `EXPIRADA_SISTEMA`;
4. o motivo passa para `LIMITE_ATINGIDO`.

O atraso da execução do scheduler **não aumenta o tempo contabilizado**.

### 5.5. Prorrogação

A sessão pode ser prorrogada através do endpoint de continuação.

Regras:

- a sessão deve estar `ATIVA` ou `EM_PAUSA`;
- ainda não pode ter expirado;
- a continuação só é permitida dentro da janela configurada em `WORK_SESSION_EXTENSION_WINDOW_MINUTES`;
- cada prorrogação acrescenta `WORK_SESSION_EXTENSION_HOURS` ao horário atual de expiração;
- novas prorrogações continuam permitidas, desde que respeitem novamente a janela da nova expiração.

---

## 6. Cálculo de Tempo

O tempo trabalhado é calculado dinamicamente no Service.

```text
tempo trabalhado = (saída - entrada) - soma das pausas
```

Para sessão aberta, o cálculo utiliza o menor valor entre o horário atual e a expiração da sessão. Isso impede que atraso do scheduler seja contabilizado como trabalho.

Em consultas por período, somente a parte da sessão e das pausas que intercepta o intervalo solicitado é considerada.

---

## 7. Permissões de Consulta

- **Membro:** consulta apenas suas próprias sessões.
- **Líder:** pode consultar sessões de membros dos setores que atualmente lidera, respeitando o setor informado.
- **Admin e Super Admin:** podem consultar sessões de todos os usuários.
- **Métricas administrativas:** exclusivas para `admin` e `super_admin`.

---

## 8. Endpoints — Controle de Horas (`/work-sessions`)

### 8.1. `POST /work-sessions`

Inicia uma sessão de trabalho para o usuário autenticado.

**Body:**

```json
{
  "setor_id": "4fa85f64-5717-4562-b3fc-2c963f66afa1"
}
```

**Response (201 Created):**

```json
{
  "id": "11111111-1111-4111-8111-111111111111",
  "usuario_id": "22222222-2222-4222-8222-222222222222",
  "setor_id": "4fa85f64-5717-4562-b3fc-2c963f66afa1",
  "entrada_em": "2026-10-04T12:00:00Z",
  "saida_em": null,
  "expira_em": "2026-10-04T20:00:00Z",
  "status": "ATIVA",
  "motivo_encerramento": null,
  "tempo_trabalhado_segundos": 0
}
```

### 8.2. `POST /work-sessions/{session_id}/pauses`

Inicia uma pausa na sessão.

### 8.3. `PATCH /work-sessions/{session_id}/pauses/{pause_id}/end`

Encerra uma pausa aberta e retorna a sessão para `ATIVA`.

### 8.4. `PATCH /work-sessions/{session_id}/end`

Encerra manualmente a sessão. Se houver pausa aberta, ela é finalizada no mesmo instante.

### 8.5. `PATCH /work-sessions/{session_id}/continue`

Prorroga o horário de expiração da sessão dentro da janela permitida.

### 8.6. `GET /work-sessions/current`

Retorna a sessão aberta do usuário autenticado ou `null` quando não houver sessão ativa.

### 8.7. `GET /work-sessions/{session_id}`

Retorna os detalhes da sessão, suas pausas e o tempo líquido calculado.

### 8.8. `GET /work-sessions`

Lista sessões com paginação e filtros.

| Parâmetro | Tipo | Padrão | Descrição |
|---|---|---|---|
| `usuario_id` | UUID | `null` | Filtra por usuário |
| `setor_id` | UUID | `null` | Filtra por setor |
| `inicio` | datetime | `null` | Início do período |
| `fim` | datetime | `null` | Fim do período |
| `pagina` | int | `1` | Página atual |
| `limite` | int | `20` | Itens por página |

### 8.9. `GET /work-sessions/summary`

Retorna o total de tempo trabalhado no período informado.

Parâmetros principais: `inicio`, `fim`, `usuario_id` e `setor_id`.

---

## 9. Métricas Administrativas

Todos os endpoints desta seção exigem role `admin` ou `super_admin`.

### 9.1. `GET /work-sessions/metrics/summary`

Retorna totais gerais de tempo trabalhado, pausas, sessões iniciadas e usuários com tempo trabalhado.

### 9.2. `GET /work-sessions/metrics/users`

Retorna métricas agrupadas por usuário, com paginação.

### 9.3. `GET /work-sessions/metrics/sectors`

Retorna métricas agrupadas pelo setor registrado em cada sessão.

### 9.4. `GET /work-sessions/metrics/timeline`

Retorna a evolução do tempo trabalhado e pausado agrupada por:

```text
dia
semana
mes
```

O agrupamento utiliza o fuso:

```text
America/Sao_Paulo
```

Sessões que atravessam a mudança de intervalo têm seus tempos distribuídos corretamente entre os intervalos, sem duplicação.

---

## 10. Scheduler

O scheduler é iniciado no ciclo de vida da aplicação e processa periodicamente sessões abertas expiradas.

```text
Aplicação inicia
    ↓
Scheduler inicia
    ↓
Busca sessões abertas expiradas
    ↓
Service aplica regras de expiração
    ↓
Repository persiste sessão e eventual pausa
```

---

## 11. Persistência e Transações

Operações relacionadas são persistidas em uma única transação quando necessário, por exemplo:

- iniciar pausa + atualizar status da sessão;
- encerrar pausa + retornar sessão para `ATIVA`;
- encerrar sessão + encerrar eventual pausa aberta;
- expiração automática + encerramento de pausa.

Isso evita estados inconsistentes entre `WorkSession` e `Pause`.

---

## 12. Testes

Os testes do módulo ficam em `tests/work_sessions/` e são separados por contexto funcional.

A suíte cobre:

- criação e encerramento de sessões;
- bloqueio de múltiplas sessões abertas;
- permissões;
- pausas;
- persistência explícita no banco de teste;
- expiração;
- prorrogação;
- consultas e listagens;
- resumo por período;
- métricas administrativas;
- timeline;
- divisão correta de sessões que atravessam a meia-noite.

Para executar:

```bash
python -m pytest tests/work_sessions -v -s
```

Para executar o linter:

```bash
ruff check .
```

---

## 13. Configurações

As principais configurações do módulo ficam em `app/config.py`:

```text
WORK_SESSION_LIMIT_HOURS
WORK_SESSION_EXTENSION_HOURS
WORK_SESSION_EXTENSION_WINDOW_MINUTES
```

---

## 14. Documentação Interativa

Com a aplicação em execução, os endpoints também podem ser visualizados e testados pelo Swagger:

```text
http://localhost:8000/docs
```
