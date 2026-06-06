# Algoritmos de Scheduling para Agendamento Semanal — Recomendações

**Contexto:** Concilium tem cronograma mensal (Skill 02) com duração derivada do modelo de eficiência. Agora precisa descer para agendamento semanal (Skill 02B) respeitando precedências, pool de recursos, deadline, margens regulatórias.

Este documento compara algoritmos com trade-offs implementação/qualidade e recomenda uma arquitetura em três camadas (MVP → Refinado → Otimizado).

---

## Mapa do problema

```
Entradas:
  - EAP com precedências (Skill 00B) ← activity_dag
  - Pool de recursos (Skill 01A) ← capacidade por tipo
  - Cronograma mensal (Skill 02) ← distribuição de equipes/meses
  - Durações estimadas ← modelo_eficiencia(produtividade, equipes, praticabilidade)
  - Prazos contratuais + multas

Saída desejada:
  - Agendamento semanal por atividade
  - Uso de recursos por semana ≤ pool
  - Precedências respeitadas
  - Ociosidade minimizada (reduz custo indireto)
  - Margem de segurança vs. deadline

Restrições:
  - Precedências (precedência simples, sem lag/lead obrigatório)
  - Capacidade de recursos (hard constraint C3)
  - Finalização ≤ data_termino (hard constraint C2)
  - Continuidade de equipes (soft: não fragmentar)
  - Regularidade tributária (indiretos por permanência)
```

---

## Categoria 1: Métodos Determinísticos Clássicos

### 1.1 — Critical Path Method (CPM) + ES/LS

**O que é:**
- Calcula caminhos críticos (slack = 0)
- Earliest Start (ES) e Latest Start (LS) para cada atividade
- Atividades no caminho crítico: ES = LS (sem folga)
- Outras atividades: margem de folga disponível

**Implementação:**
```python
def compute_earliest_start_times(dag, durations):
    """Forward pass: quando cada atividade pode começar."""
    es = {node: 0 for node in dag.nodes}
    for node in topological_order:
        for succ in dag.successors(node):
            es[succ] = max(es[succ], es[node] + durations[node])
    return es

def compute_latest_start_times(dag, durations, deadline):
    """Backward pass: quando deve começar para respeitar deadline."""
    ls = {node: deadline for node in dag.nodes}
    for node in reversed(topological_order):
        for pred in dag.predecessors(node):
            ls[pred] = min(ls[pred], ls[node] - durations[node])
    return ls
```

**Pros:**
- Implementação trivial (já temos a base)
- Determinístico
- Identifica gargalos (caminho crítico)

**Cons:**
- Ignora recursos totalmente
- LS pode estar infeasible dado pool limitado
- Não otimiza nada — apenas calcula bounds

**Complexidade:** O(V + E) — linear

---

### 1.2 — Serial Scheduling com Priority Rules (PRB)

**O que é:**
- Versão refinada do CPM que respeita recursos
- Processa atividades em ordem de prioridade
- Para cada atividade: aloca-a no primeiro slot disponível respeitando:
  - Precedências concluídas
  - Capacidade de recursos disponível
  - Não interrompe atividade em progresso (no-preemption)

**Variantes de prioridade (heurísticas):**

| Heurística | Quando usar |
|-----------|------------|
| **ES (Earliest Start)** | Reduz ociosidade |
| **LS (Latest Start)** | Aproveita folga para resource leveling |
| **MINSLK (Min Slack First)** | Foca em atividades críticas |
| **MAXRES (Max Resource First)** | Aloca pesadas primeiro |
| **SPT (Shortest Processing Time)** | Termina muitas atividades rápido |
| **LPT (Longest Processing Time)** | Evita fila de atividades longas |
| **GR (Greatest Rank)** | Topological order com tie-break |

**Pros:**
- Simples de implementar
- Rápido (polinomial)
- Respeita recursos (hard constraint)
- Determinístico
- Permite múltiplas heurísticas (testar para encontrar melhor)

**Cons:**
- Qualidade depende de escolha de heurística
- Não garante otimalidade (nem busca por ela)
- Sensível a ordem de entrada (se há tie em prioridade)

**Complexidade:** O(n² × m × w)

---

### 1.3 — Parallel Scheduling (Two-Pass)

**O que é:**
- Melhora serial scheduling com relaxamento de prioridades
- Passo 1: schedule usando serial (baseline)
- Passo 2: tenta realocar atividades não-críticas para "encher buracos" (resource leveling)

**Pros:**
- Melhora serial com low overhead
- Reduz fragmentação de recursos
- Ainda polinomial

---

## Categoria 2: Métodos Exatos (Programação Linear)

### 2.1 — Mixed-Integer Linear Programming (MILP)

**O que é:**
- Formulação exata do problema como sistema de inequações
- Variáveis: x[i,t] = 1 se atividade i inicia na semana t, 0 c.c.
- Constraints: precedências, recursos, bounds
- Objective: minimizar makespan (duração total) ou custo

**Pros:**
- Ótimo global (se converge)
- Responde perguntas "why" (dual variables)
- Formalizável com múltiplos objetivos

**Cons:**
- Escalabilidade limitada (exponencial em casos patológicos)
- Tempo de convergência imprevisível
- Requer solver externo (CBC, Gurobi, CPLEX)

**Complexidade:** NP-hard, mas prático para ~100 atividades em 30s–2min

---

## Categoria 3: Metaheurísticos (Busca Local)

### 3.1 — Genetic Algorithm (GA)

**Pros:**
- Paralelizável
- Robusto em landscapes complexos
- Pode encontrar boas soluções rápido

**Cons:**
- Requer tuning de parâmetros
- Não garante otimalidade
- Difícil debugar

---

### 3.2 — Tabu Search

**Pros:**
- Determinístico (reproduzível)
- Rápido (polinomial per iteração)
- Evita mínimos locais via tabu list

**Cons:**
- Ainda não garante otimalidade
- Sensível a parâmetros

---

## Resumo Comparativo

| Algoritmo | Otimalidade | Tempo | Determinístico | Implementação | Quando usar |
|-----------|-----------|-------|---|---|---|
| **CPM** | Non (baseline) | O(V+E) | ✅ | Trivial | Baseline, identifica críticos |
| **Serial+PRB** | Non | O(n²×m×w) | ✅ | Simples | MVP, múltiplas heurísticas |
| **Parallel** | Non | O(n²×m×w) | ✅ | Moderada | Melhorar serial com leveling |
| **MILP** | Ótimo | NP-hard | ✅ | Moderada* | Obras críticas, budget otimização |
| **GA** | Non | Tuning | ❌ | Complexa | Landscape irregular |
| **Tabu** | Non | O(iter×neighbor) | ✅ | Moderada | Exploração rápida de vizinhança |

---

## Recomendação de Arquitetura em 3 Camadas

### MVP (Sprint 1) — Serial Scheduling com PRB

**Objetivo:** Schedule viável, determinístico, rápido.

**Heurísticas a testar (em paralelo):**
1. MINSLK (Min Slack First)
2. LPT (Longest Processing Time)
3. MAXRES (Max Resource First)
4. GR (Greatest Rank)

Retornar top-3 para revisão humana (com métrica de qualidade).

**Estimativa de esforço:** 3–5 dias  
**Complexidade implementação:** Baixa–Média

---

### Refinamento (Sprint 2) — Parallel Scheduling + Resource Leveling

**Objetivo:** Melhorar serial com local optimization.

**Estimativa de esforço:** 2–3 dias  
**Quando introduzir:** Após testes de MVP com dados reais

---

### Otimização (Sprint 3+) — MILP ou Metaheurístico

**Objetivo:** Otimalidade ou exploração de trade-offs.

**Estimativa de esforço:** 5–7 dias  
**Quando introduzir:** Após validação de MVP com obras reais

---

## Procedimento de Seleção para uma Obra Específica

```python
def choose_scheduling_method(
    num_activities,
    num_resources,
    project_duration_weeks,
    criticality,
):
    problem_size = num_activities * num_resources * project_duration_weeks
    
    # Pequenas obras: MILP é viável
    if num_activities <= 50 and criticality == "high":
        return SchedulingMethod.MILP  # exato, rápido
    
    # Médias obras: Parallel scheduling
    if num_activities <= 150:
        return SchedulingMethod.PARALLEL  # bom balanço
    
    # Grandes obras: Serial + Tabu fallback
    if num_activities > 150:
        return SchedulingMethod.SERIAL_TABU  # escalável
    
    # Default: Serial + múltiplas heurísticas
    return SchedulingMethod.SERIAL_MULTISTART
```

---

## Métricas de Qualidade do Schedule

| Métrica | Interpretação |
|---------|---|
| **Makespan** | Duração total — minimizar |
| **Resource Utilization** | % utilização — maximizar |
| **Idle Time** | Tempo ocioso — minimizar |
| **Resource Leveling Score** | Suavidade de uso — minimizar variance |
| **Activity Fragmentation** | Continuidade — minimizar gaps |
| **Critical Path Slack** | Margem de segurança — maximizar |

---

## Implementação Recomendada — Estrutura

```
src/concilium/scheduling/
├── __init__.py
├── base.py                 ← BaseScheduler abstrato
├── models.py              ← ScheduleOutput, Activity
├── cpm.py                 ← CPM: ES/LS, critical path
├── serial.py              ← SerialScheduler + priority rules
├── parallel.py            ← ParallelScheduler + leveling
├── milp.py               ← MILPScheduler (PuLP-based)
├── metaheuristic/
│   ├── genetic.py        ← GeneticScheduler
│   ├── tabu.py          ← TabuScheduler
│   └── common.py        ← utilities
└── validators.py         ← check_feasibility, metrics
```

---

## Próximos Passos

1. **Imediato:** Implementar Serial Scheduler (MVP) com 4–5 heurísticas
   - Integração com Skill 02 (receber durations estimadas)
   - CLI: `concilium schedule weekly --project <id> --heuristic <name>`
   - Output: JSON com 3 alternativas rankeadas

2. **Curto prazo:** Testar com 5–10 obras reais AGIS
   - Coletar métricas de qualidade
   - Identificar qual heurística é "padrão" para cada tipo

3. **Médio prazo:** Parallel Scheduler + resource leveling
   - Se Serial produz muitos picos → Parallel ajuda

4. **Longo prazo:** MILP para obras críticas
   - `pip install pulp`
   - Configurar solver open-source (CBC)