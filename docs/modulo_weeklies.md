# Módulo de Weeklies, Tarefas e Governança

Esta documentação detalha a arquitetura, regras de negócio, ciclo de vida, modelos relacionais, automações do scheduler, protocolos de concorrência e endpoints implementados no **Módulo de Weeklies** do backend do Learning Lab UFC.

---

## Índice

1. [Visão Geral](#1-visão-geral)
2. [Estrutura de Arquivos e Camadas](#2-estrutura-de-arquivos-e-camadas)
3. [Modelos e Esquema do Banco de Dados](#3-modelos-e-esquema-do-banco-de-dados)
4. [Ciclo de Vida e Estados da Weekly](#4-ciclo-de-vida-e-estados-da-weekly)
5. [Gestão de Tarefas (Tasks) e Rollover Automático](#5-gestão-de-tarefas-tasks-e-rollover-automático)
6. [Atribuição e Colaboração em Tarefas](#6-atribuição-e-colaboração-em-tarefas)
7. [Governança, Concorrência e Proteções de Escrita](#7-governança-concorrência-e-proteções-de-escrita)
8. [Automação e Agendamento (APScheduler)](#8-automação-e-agendamento-apscheduler)
9. [Recuperação Resiliente de Paradas do Servidor](#9-recuperação-resiliente-de-paradas-do-servidor)
10. [Sistema Disciplinar de Advertências e Desligamento](#10-sistema-disciplinar-de-advertências-e-desligamento)
11. [Serviço de Auditoria e Notificações por E-mail](#11-serviço-de-auditoria-e-notificações-por-e-mail)
12. [Dashboards e Métricas Analíticas](#12-dashboards-e-métricas-analíticas)
13. [Migrações e Banco de Dados (Alembic)](#13-migrações-e-banco-de-dados-alembic)
14. [Referência dos Endpoints da API](#14-referência-dos-endpoints-da-api)
15. [Testes Automatizados e Qualidade](#15-testes-automatizados-e-qualidade)

---

## 1. Visão Geral

O **Módulo de Weeklies** é o núcleo de acompanhamento de produtividade e governança operacional do Learning Lab. Ele gerencia:
- O ciclo semanal de planejamento e prestação de contas dos membros por setor.
- A persistência e o ciclo de vida individual de tarefas (`Tasks`).
- A herança automática (*rollover*) de pendências não concluídas entre semanas consecutivas.
- A auditoria semanal e o escalonamento automático de sanções disciplinares para ausências repetidas.
- A mediação de colaboração entre participantes (atribuição cruzada de tarefas).
- Dashboards consolidadores com métricas de adesão, atrasos e produtividade setorial e global.

---

## 2. Estrutura de Arquivos e Camadas

O módulo segue o padrão **Modular by Feature** (*Vertical Slicing*):

```text
app/weeklies/
├── __init__.py           # Exportação dos submódulos
├── router.py             # Rotas FastAPI (/tasks, /weeklies, /advertencias, /atribuicoes, /dashboard)
├── schemas.py            # Contratos Pydantic de entrada e saída com validações estritas
├── service.py            # Lógica de negócio, governança, validações de janela e transações
├── repository.py         # Camada de persistência, consultas otimizadas e locks no PostgreSQL
├── scheduler.py          # Jobs recorrentes do APScheduler, advisory locks e rotina de recuperação
└── timezone_utils.py     # Utilitários de fuso horário de referência (America/Fortaleza)
```

### Modelos ORM Relacionados (`app/models/`):
- `weekly.py` (`Weekly`): Relatório semanal do membro em determinado setor.
- `task.py` (`Task`): Tarefa global pertencente a um usuário e setor.
- `weekly_task.py` (`WeeklyTask`): Tabela associativa com snapshots semanais e progresso.
- `task_assignment.py` (`TaskAssignment`): Convites e vínculos colaborativos em tarefas.
- `weekly_warning.py` (`WeeklyWarning`): Registro de advertências emitidas pelo sistema.
- `weekly_scheduler_execution.py` (`WeeklySchedulerExecution`): Registro idempotente das execuções do cron.

---

## 3. Modelos e Esquema do Banco de Dados

### 3.1. Tabela `weeklies`
Representa a entrega semanal de um membro em um setor:
- `id`: UUID (Primary Key).
- `usuario_id`: UUID (Foreign Key `usuarios.id`).
- `setor_id`: UUID (Foreign Key `setores.id`).
- `semana_referencia`: Date (segunda-feira da semana correspondente).
- `status`: String (Enum: `RASCUNHO`, `ENVIADA`, `APROVADA`, `REJEITADA`, `EXPIRADA`).
- `enviada_em`: DateTime com timezone.
- `avaliada_em`: DateTime com timezone.
- `avaliada_por`: UUID (Foreign Key `usuarios.id`, líder/admin avaliador).
- `observacao_lider`: Text (obrigatório em caso de rejeição).
- `motivo_expiracao`: Text (motivo quando expirada pelo scheduler).
- `detalhe_expiracao`: Text.
- **Unique Constraint:** `(usuario_id, setor_id, semana_referencia)`.

### 3.2. Tabela `tasks`
Representa a tarefa de longo prazo gerenciada pelo membro:
- `id`: UUID (Primary Key).
- `usuario_id`: UUID (Foreign Key `usuarios.id`, criador/responsável).
- `setor_id`: UUID (Foreign Key `setores.id`).
- `titulo`: String(255).
- `descricao`: Text.
- `prazo_conclusao`: Date.
- `status`: String (Enum: `PENDENTE`, `CONCLUIDA`, `EM_AUDITORIA`, `REMOVIDA_PELO_LIDER`).
- `removida_por`: UUID (Foreign Key `usuarios.id`, líder que removeu a tarefa).
- `motivo_remocao`: Text.

### 3.3. Tabela `weekly_tasks`
Associação entre uma weekly e uma tarefa:
- `id`: UUID (Primary Key).
- `weekly_id`: UUID (Foreign Key `weeklies.id`, cascade delete).
- `task_id`: UUID (Foreign Key `tasks.id`).
- `concluida`: Boolean (marcação semanal de conclusão).
- `impedimento`: Text (justificativa de impedimento para não conclusão no prazo).
- `posicao`: Integer (ordem na lista da weekly).
- `origem`: String (`NOVA` ou `HERDADA`).
- `snapshot_titulo`: String(255).
- `snapshot_descricao`: Text.
- `snapshot_prazo_conclusao`: Date.
- **Unique Constraint:** `(weekly_id, task_id)` — impede que a mesma tarefa seja adicionada duas vezes no mesmo relatório.

### 3.4. Tabela `atribuicoes_task`
Delegação ou convite colaborativo para tarefas compartilhadas:
- `id`: UUID (Primary Key).
- `task_id`: UUID (Foreign Key `tasks.id`).
- `usuario_atribuido_id`: UUID (Foreign Key `usuarios.id`).
- `atribuido_por_id`: UUID (Foreign Key `usuarios.id`).
- `papel`: String (`RESPONSAVEL`, `COLABORADOR`).
- `status`: String (`PENDENTE`, `ACEITO`, `RECUSADO`).

### 3.5. Tabela `advertencias_weekly`
Histórico de sanções disciplinares geradas por não envio:
- `id`: UUID (Primary Key).
- `usuario_id`: UUID (Foreign Key `usuarios.id`).
- `setor_id`: UUID (Foreign Key `setores.id`).
- `semana_referencia`: Date.
- `tipo`: String (`1a_ADVERTENCIA`, `2a_ADVERTENCIA`, `DESLIGAMENTO`).
- `justificativa`: Text.
- `gerado_por`: String (`SISTEMA` ou `LIDER`).
- **Unique Constraint:** `(usuario_id, setor_id, semana_referencia)`.

### 3.6. Tabela `weekly_scheduler_execucoes`
Registro idempotente de execuções dos jobs automáticos do agendador:
- `id`: UUID (Primary Key).
- `tipo`: String (ex: `CRIAR_WEEKLIES`, `VERIFICAR_AUSENCIAS`).
- `semana_referencia`: Date.
- `executado_em`: DateTime com timezone.
- **Unique Constraint:** `(tipo, semana_referencia)`.

---

## 4. Ciclo de Vida e Estados da Weekly

### Diagrama de Estados

```text
    ┌──────────────┐
    │  [CRIAÇÃO]   │
    └──────┬───────┘
           │
           ▼
    ┌──────────────┐   Submeter (W05)   ┌──────────────┐
    │   RASCUNHO   │ ─────────────────> │   ENVIADA    │
    └──────┬───────┘                    └──────┬───────┘
           │                                   │
           │ Reabrir (W06)                     │ Avaliar (W07)
           │ <─────────────────────────────────┤
           │                                   │
           │                                   ├─────────────────┐
           │                                   ▼                 ▼
           │                             ┌───────────┐     ┌───────────┐
           │                             │ APROVADA  │     │ REJEITADA │
           │                             └───────────┘     └─────┬─────┘
           │                                                     │
           │ Expirar pelo Scheduler (sexta 00h)                  │ Reabrir / Reenviar (W06)
           │                                                     │ (Grace Period 24h)
           ▼                                                     ▼
    ┌──────────────┐                                      ┌──────────────┐
    │   EXPIRADA   │ <────────────────────────────────────┤   RASCUNHO   │
    └──────────────┘                                      └──────────────┘
```

### Regras de Transição e Janela de Submissão:
1. **Fuso Horário:** Todas as datas de corte operam sob o fuso horário oficial `America/Fortaleza` (UTC-3).
2. **Janela Regular:**
   - **Abertura:** Sexta-feira às 00:00 da semana vigente.
   - **Fechamento:** Segunda-feira às 23:59:59.
3. **Reabertura pelo Membro (W06):**
   - Um relatório com status `ENVIADA` pode ser voluntariamente reaberto para `RASCUNHO` pelo próprio membro desde que ainda esteja dentro da janela regular e não tenha sido avaliado pelo líder.
4. **Período de Tolerância após Rejeição (Grace Period de 24h):**
   - Caso o líder avalie a weekly como `REJEITADA`, o membro possui 24 horas contadas a partir de `avaliada_em` para editar e reenviar o relatório, mesmo se a janela de segunda-feira já houver encerrado.
5. **Expiração Automática:**
   - Na virada de ciclo de sexta-feira (00:00), relatórios que permaneceram em `RASCUNHO` ou `ENVIADA` sem avaliação são transicionados para `EXPIRADA`.

---

## 5. Gestão de Tarefas (Tasks) e Rollover Automático

### Ciclo de Vida da Tarefa:
- `PENDENTE`: Tarefa em execução ou planejada.
- `CONCLUIDA`: Tarefa cuja entrega foi homologada pelo líder na aprovação da weekly.
- `EM_AUDITORIA`: Tarefa cujo prazo civil foi ultrapassado e que foi detectada pela rotina semanal de auditoria.
- `REMOVIDA_PELO_LIDER`: Tarefa cancelada administrativamente pelo líder do setor.

### Rollover Automático (Fase 4):
Quando a nova weekly é criada na sexta-feira às 00:00:
1. O sistema busca todas as tarefas do membro no setor que ainda estejam com status `PENDENTE`.
2. As tarefas são inseridas na nova weekly com `origem = "HERDADA"`, `concluida = False` e `impedimento = None`.
3. É gerado um novo snapshot das informações da tarefa (`snapshot_titulo`, `snapshot_descricao`, `snapshot_prazo_conclusao`).
4. Tarefas que já foram concluídas ou removidas não sofrem rollover.

### Regras de Integridade:
- **Conteúdo Mínimo:** Nenhuma weekly pode ser enviada com 0 tarefas vinculadas.
- **Proteção contra Esvaziamento:** Em relatórios já `ENVIADA` ou `REJEITADA`, é proibido remover a última tarefa existente.

---

## 6. Atribuição e Colaboração em Tarefas

Para suportar trabalhos em equipe no mesmo setor:
1. Um membro pode convidar outro integrante do setor para colaborar em sua tarefa (`POST /tasks/{task_id}/assignments`).
2. O convidado recebe notificação e pode responder aceitando ou recusando (`PATCH /atribuicoes/{assignment_id}/aceitar` ou `recusar`).
3. Ao aceitar o convite:
   - Se o colaborador possuir uma weekly em `RASCUNHO` no setor, a tarefa é vinculada automaticamente à weekly dele sob transação protegida por lock (`with_for_update`).
   - Se a weekly do colaborador já estiver `ENVIADA` ou `APROVADA`, a tarefa permanece atribuída na lista pessoal dele como avulsa, sem violar a imutabilidade do relatório já entregue.

---

## 7. Governança, Concorrência e Proteções de Escrita

Para evitar condições de corrida em ambientes com múltiplos workers e réplicas:

### 7.1. Protocolo de Bloqueio Pessimista (`with_for_update`)
Todas as operações de alteração de estado adquirem bloqueio exclusivo nas linhas afetadas antes de validar e alterar dados:
1. **Weeklies:** Bloqueio na linha da weekly antes de submeter, reabrir ou avaliar para serializar requisições simultâneas.
2. **Tasks (Prorrogação e Auditoria):** `svc_update_task_prazo` e `svc_concluir_task_auditoria` adquirem lock exclusivo (`for_update=True`) na `Task`. Isso impede condições de corrida onde uma prorrogação de prazo reativaria acidentalmente uma tarefa já concluída ou removida (`REMOVIDA_PELO_LIDER`).
3. **Atribuições (Convites):** `svc_respond_task_assignment` bloqueia a linha de `TaskAssignment` para serializar respostas ao mesmo convite. A tarefa de origem é carregada para revalidar seu status.

### 7.2. Projeção Dinâmica em Relatórios Abertos e Imutabilidade de Snapshots
- **Relatórios Abertos (`RASCUNHO` e `REJEITADA`):** Durante o preenchimento ou no período de carência de 24h após rejeição, o sistema projeta os dados vivos da `Task` (`titulo`, `descricao`, `prazo_conclusao`), permitindo conferência visual imediata das correções antes e durante a reavaliação.
- **Relatórios Enviados ou Finalizados (`ENVIADA`, `APROVADA`, `EXPIRADA`):** O snapshot é congelado no envio e preservado na aprovação de uma weekly `ENVIADA`, mesmo que o prazo da tarefa seja prorrogado depois. A aprovação direta de `REJEITADA` congela a versão corrigida; o reenvio também gera um novo snapshot. Campos nulos fazem parte do snapshot e são preservados. Registros legados sem snapshot usam os dados da tarefa como fallback.

### 7.3. Notificações Desacopladas fora do Event Loop (`BackgroundTasks`)
- Todas as notificações transacionais por e-mail (convites de tarefas, respostas de aceite/recusa e relatos de impedimentos) são disparadas fora do ciclo síncrono da requisição através de `BackgroundTasks` do FastAPI.
- O agendamento ocorre estritamente **após** a confirmação da transação no banco de dados (`commit`).
- Conexões SMTP possuem timeout configurável por `SMTP_TIMEOUT` (10s por padrão). Notificações em background capturam e registram falhas de SMTP e de conexão sem desfazer a operação já persistida. Não há retentativa automática de e-mails.

### 7.4. Restrição Estrita a Setores Ativos em Colaborações
- Apenas usuários vinculados a setores ativos (`Sector.ativo is True`) são listados como elegíveis ou podem receber convites de colaboração.
- No momento do aceite, o sistema revalida o status do setor de destino: se o setor foi desativado após o convite e o membro não possuir outro setor ativo, o aceite é recusado e o convite é cancelado/expirado, impedindo a persistência de tarefas em setores inativos.

### 7.5. Atualizações Condicionais Atômicas no Banco
Na aprovação da weekly, a consolidação de conclusão das tarefas é realizada via `UPDATE` condicional direto no PostgreSQL:
```sql
UPDATE tasks
SET status = 'CONCLUIDA'
WHERE id = :task_id AND status = 'PENDENTE';
```
Dessa forma, caso outra transação concorrente tenha movido a tarefa para `EM_AUDITORIA` ou `REMOVIDA_PELO_LIDER`, o status anterior não é sobrescrito indevidamente.

### 7.6. Atomicidade em Criação Inline
A criação de tarefas diretamente vinculadas à weekly (`POST /weeklies/{weekly_id}/tasks`) realiza a gravação da Task e do vínculo `WeeklyTask` em transação única com `db.flush()`. Havendo qualquer falha, o rollback é integral, sem deixar tarefas órfãs desvinculadas.

---

## 8. Automação e Agendamento (APScheduler)

Os jobs em segundo plano são agendados e orquestrados por `app/weeklies/scheduler.py`:

| Job ID | Frequência / Gatilho | Responsabilidade |
| :--- | :--- | :--- |
| `criar_weeklies` | Toda sexta-feira às 00:00 (Fortaleza) | Expira weeklies pendentes anteriores e cria em lote as novas weeklies para todos os membros ativos, executando o rollover de tarefas. |
| `verificar_ausencias` | Toda terça-feira às 01:00 (Fortaleza) | Varre membros sem entrega na semana recém-fechada para gerar advertências automáticas e audita tarefas vencidas. |
| `recuperar_weeklies` | A cada 5 minutos (e no startup) | Verifica execuções não realizadas e reprocessa semanas pendentes de forma segura e ordenada. |

### PostgreSQL Advisory Locks:
Para coordenar execuções em deploys com múltiplos containers/workers:
- `LOCK_ID_CRIAR_WEEKLIES` = `771001`
- `LOCK_ID_VERIFICAR_AUSENCIAS` = `771002`

A conexão física é reservada exclusivamente do engine (`engine.connect()`) durante toda a duração do lock, garantindo que `pg_try_advisory_lock` e `pg_advisory_unlock` sejam executados rigorosamente na mesma conexão física, prevenindo deadlocks e locks fantasmas no pool.

### Registro de Conclusão sem Falhas:
O job `executar_criacao_weeklies_lote` só grava o registro de conclusão em `weekly_scheduler_execucoes` quando `erros == 0`. Caso ocorram falhas parciais em membros individuais, a transação faz rollback para esses membros e a recuperação posterior retenta apenas os faltantes sem duplicar os existentes.

---

## 9. Recuperação Resiliente de Paradas do Servidor

Caso o servidor passe semanas desligado (ex: manutenção prolongada ou indisponibilidade de infraestrutura):

1. **Ponto de Partida Confiável:** A rotina `_recuperar_ausencias` busca a última execução registrada (`func.max(WeeklySchedulerExecution.semana_referencia)`) ou o marco de implantação configurado (`settings.WEEKLY_MARCO_IMPLANTACAO`).
2. **Iteração Estrita de 7 em 7 Dias:** Percorre cronologicamente semana a semana (`semana += timedelta(days=7)`) até a última semana fechada.
3. **Preservação da Escala Disciplinar:** Essa ordem cronológica rigorosa garante que nenhuma semana intermediária seja ignorada, assegurando que o membro receba a 1ª advertência, a 2ª advertência e, se persistir, o desligamento, sem pular etapas do processo.

---

## 10. Sistema Disciplinar de Advertências e Desligamento

O Learning Lab adota uma política de sanções automáticas para faltas não justificadas na entrega semanal:

| Ausências Consecutivas | Sanção Emitida | Efeito no Sistema |
| :---: | :--- | :--- |
| **1 semana** | `1a_ADVERTENCIA` | Notificação por e-mail e registro no histórico do membro. |
| **2 semanas consecutivas** | `2a_ADVERTENCIA` | Notificação com aviso de risco de desligamento iminente. |
| **3 ou mais semanas consecutivas** | `DESLIGAMENTO` | Emissão de registro formal de desligamento para deliberação da coordenação. |

### Regras de Isenção:
- **Administradores e Superadministradores:** Estão isentos da obrigatoriedade semanal e não sofrem advertências.
- **Membros Recém-ingressados:** A obrigatoriedade tem início apenas na primeira semana fechada subsequente à data de ingresso do membro no setor (`setor_usuarios.data_ingresso`).

---

## 11. Serviço de Auditoria e Notificações por E-mail

### Auditoria de Tarefas Vencidas:
Toda terça-feira às 01:00, o serviço inspeciona tarefas que:
- Possuam status `PENDENTE`.
- Possuam `prazo_conclusao < hoje`.
- Transiciona o status para `EM_AUDITORIA` e notifica o líder do setor por e-mail com as opções de dilação de prazo ou cancelamento.

### Templates de E-mail HTML (`app/templates/`):
- `advertencia_template.html`: Layout corporativo com detalhes da advertência, semana de referência e contagem de penalidades.
- `impedimento_template.html`: Notificação ao líder informando que um membro registrou impedimento para entrega de uma tarefa.
- `task_atribuida_template.html`: Convite de colaboração em tarefa compartilhada.
- `task_auditoria_template.html`: Alerta ao líder sobre tarefas vencidas que entraram em auditoria.

---

## 12. Dashboards e Métricas Analíticas

### 12.1. Dashboard do Setor (`GET /dashboard/weeklies/sector/{sector_id}`)
Permite ao líder do setor acompanhar sua equipe:
- **Resumo:** Total de membros ativos, weeklies entregues, rascunhos, weeklies pendentes de avaliação, semana de referência.
- **População e Taxa de Adesão:** Percentual de membros obrigados que enviaram relatório dentro do prazo.
  > **Nota de Governança:** Administradores e super administradores são isentos por regra do sistema: seus relatórios opcionais, inclusive rascunhos, são excluídos tanto do numerador quanto do denominador. A contagem considera membros e líderes ativos com vínculo iniciado até a data consultada, preservando também a contagem de autores não isentos com relatório histórico após seu desligamento. Os totais de tarefas pendentes e em auditoria continuam representando o setor inteiro.
- **Tarefas:** Total de tarefas planejadas, concluídas e com impedimento no ciclo.
- **Membros Ausentes:** Lista de membros sem envio para a semana selecionada.

### 12.2. Dashboard Global (`GET /dashboard/weeklies/global`)
Visão macro disponível para administradores e coordenadores:
- Total geral de membros obrigados vinculados a setores ativos.
- Taxa global de submissão da semana consolidando apenas os setores e membros obrigados.
- Tabela comparativa de adesão setor por setor.
- Alertas de tarefas em auditoria e membros reincidentes em advertências.

---

## 13. Migrações e Banco de Dados (Alembic)

O esquema do banco de dados para weeklies é gerenciado por migrações dedicadas:

### 1. `9176f5980bb7_criar_tabelas_weeklies_tasks_.py`
- Cria as tabelas `weeklies`, `tasks`, `weekly_tasks`, `atribuicoes_task`, `advertencias_weekly` e `weekly_scheduler_execucoes`.
- Adiciona os campos `data_ingresso` e `criado_em` na tabela `setor_usuarios`.

### 2. `b7f3a920d641_corrigir_id_execucoes_scheduler.py`
- Alinha o identificador da tabela `weekly_scheduler_execucoes` de `Integer` para `UUID(as_uuid=True)`, compatibilizando o banco de dados diretamente com o modelo ORM.
- Suporta upgrade e downgrade com conversão determinística e segura de dados pré-existentes.

---

## 14. Referência dos Endpoints da API

Todas as rotas exigem cabeçalho `Authorization: Bearer <token_acesso>`.

### 14.1. Tarefas (`/tasks`)

| Método | Rota | Papel Mínimo | Descrição |
| :--- | :--- | :--- | :--- |
| `POST` | `/tasks` | `usuario` | Cria uma nova task pessoal para o setor indicado. |
| `GET` | `/tasks/me` | `usuario` | Lista as tasks do usuário autenticado (com paginação e filtros). |
| `PATCH` | `/tasks/{task_id}` | `usuario` | Atualiza título, descrição ou prazo de uma task pendente. |
| `DELETE` | `/tasks/{task_id}` | `usuario` | Remove uma task (se permitida pelo ciclo de vida). |
| `GET` | `/tasks/sector/{sector_id}/audit` | `lider` / `admin` | Lista tarefas do setor que entraram em auditoria por atraso. |
| `PATCH` | `/tasks/{task_id}/prazo` | `lider` / `admin` | Prorroga o prazo de uma tarefa em auditoria e restaura para pendente. |
| `PATCH` | `/tasks/{task_id}/concluir-auditoria`| `lider` / `admin` | Conclui manualmente uma tarefa em auditoria. |
| `GET` | `/tasks/{task_id}/colaboradores-elegiveis` | `usuario` | Lista membros do setor elegíveis para convite na tarefa. |
| `POST` | `/tasks/{task_id}/assignments` | `usuario` | Envia convite de colaboração para outro membro do setor. |

### 14.2. Relatórios Semanais (`/weeklies`)

| Método | Rota | Papel Mínimo | Descrição |
| :--- | :--- | :--- | :--- |
| `GET` | `/weeklies/current` | `usuario` | Obtém (ou cria se aplicável) a weekly da semana atual no setor. |
| `GET` | `/weeklies/me` | `usuario` | Lista o histórico de weeklies do usuário (com paginação e filtros). |
| `GET` | `/weeklies/sector/{sector_id}` | `lider` / `admin` | Lista todas as weeklies do setor para acompanhamento do líder. |
| `POST` | `/weeklies` | `usuario` | Criação explícita de weekly para o ciclo atual no setor. |
| `GET` | `/weeklies/{weekly_id}` | `usuario` | Detalhes da weekly com tarefas e snapshots. |
| `PATCH` | `/weeklies/{weekly_id}/send` | `usuario` | Submete a weekly para avaliação do líder (`ENVIADA`). |
| `PATCH` | `/weeklies/{weekly_id}/reopen` | `usuario` | Reabre weekly enviada ou rejeitada para o estado `RASCUNHO`. |
| `PATCH` | `/weeklies/{weekly_id}/evaluate` | `lider` / `admin` | Avalia o relatório como `APROVADA` ou `REJEITADA` (com feedback). |
| `POST` | `/weeklies/{weekly_id}/tasks` | `usuario` | Cria e vincula uma nova tarefa atômica ao relatório. |
| `PATCH` | `/weeklies/{weekly_id}/tasks/{weekly_task_id}` | `usuario` | Atualiza conclusão (`concluida`) ou impedimento no item da weekly. |
| `DELETE` | `/weeklies/{weekly_id}/tasks/{weekly_task_id}` | `usuario` | Remove o vínculo de uma tarefa da weekly (respeitando proteções). |

### 14.3. Atribuições e Colaborações (`/atribuicoes`)

| Método | Rota | Papel Mínimo | Descrição |
| :--- | :--- | :--- | :--- |
| `GET` | `/atribuicoes/me` | `usuario` | Lista atribuições e convites recebidos pelo usuário. |
| `PATCH` | `/atribuicoes/{assignment_id}/aceitar` | `usuario` | Aceita o convite e vincula à weekly (se aplicável). |
| `PATCH` | `/atribuicoes/{assignment_id}/recusar` | `usuario` | Recusa o convite de colaboração da tarefa. |

### 14.4. Advertências (`/advertencias`)

| Método | Rota | Papel Mínimo | Descrição |
| :--- | :--- | :--- | :--- |
| `GET` | `/advertencias/me` | `usuario` | Consulta o histórico pessoal de advertências do usuário autenticado. |
| `GET` | `/advertencias/sector/{sector_id}` | `lider` / `admin` | Consulta histórico de advertências emitidas aos membros do setor. |

### 14.5. Dashboards (`/dashboard`)

| Método | Rota | Papel Mínimo | Descrição |
| :--- | :--- | :--- | :--- |
| `GET` | `/dashboard/weeklies/sector/{sector_id}` | `lider` / `admin` | Métricas e taxa de adesão do setor para a semana de referência. |
| `GET` | `/dashboard/weeklies/global` | `admin` / `super_admin` | Métricas consolidadas de todos os setores do Learning Lab. |

---

## 15. Testes Automatizados e Qualidade

O módulo conta com uma suíte abrangente de testes automatizados (`tests/weeklies/`), totalizando mais de 300 cenários no projeto:

```bash
# Executar toda a suíte de testes do módulo de weeklies
.venv/bin/pytest tests/weeklies/ -v

# Executar testes específicos de migração em PostgreSQL temporário
.venv/bin/pytest tests/weeklies/test_scheduler_migrations.py -v

# Executar testes de concorrência e locks
.venv/bin/pytest tests/weeklies/test_concorrencia.py -v

# Regressões do PR #71, incluindo conexões PostgreSQL independentes e locks reais
.venv/bin/pytest tests/weeklies/test_revisao_pr71.py -v

# Executar testes de recuperação após paradas
.venv/bin/pytest tests/weeklies/test_scheduler_recovery.py -v

# Checagem de tipagem e linting com Ruff
.venv/bin/ruff check .
```
