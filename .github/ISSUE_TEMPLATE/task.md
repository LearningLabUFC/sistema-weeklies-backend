---
name: Task
about: Suggest an idea for this project
title: 'Task: '
labels: documentation, enhancement
assignees: ''
type: Task

---

---

### 1. Contexto (O Quê e Por Quê)
> Descreva em 1 ou 2 frases a necessidade ou o problema que esta task resolve.

**Exemplo:** Precisamos de um endpoint no FastAPI que receba o ID do membro e salve o horário atual no PostgreSQL como registro de entrada.

---

### 2. Checklist de Execução (O Como)
- [ ] Passo técnico 1 (Ex: Validar se o payload da requisição contém o Token JWT)
- [ ] Passo técnico 2 (Ex: Criar a query no SQLAlchemy para a tabela de Pontos)
- [ ] Passo técnico 3 (Ex: Retornar status 200 com a mensagem de sucesso)

---

### 3. Critérios de Aceite (Definition of Done)
> O que precisa acontecer/ser testado para considerarmos essa task 100% finalizada?

- [ ] Condição 1 (Ex: Se tentar bater ponto sem estar logado, deve retornar erro 401)
- [ ] Condição 2 (Ex: O horário salvo no banco deve respeitar o fuso horário de Brasília UTC-3)
