# ADR-046: RCPSP — Implementação Completa do Escalonamento Restrito por Recursos

**Status:** Implementado  
**Data de Decisão:** 2026-05-12  
**Implementadores:** `application/scheduling/`, `application/skills/manifests/02-cronograma/skill.py`, `application/benchmarks/spec_loader.py`  
**ADRs Relacionados:** ADR-004 (algorithm selection), ADR-006 (team composition), ADR-007 (productivity), ADR-016 (resource sharing taxonomy)

---

## Contexto

### Problema

O Skill 02 (Cronograma) possui dois modos de operação:
- **MANUAL_ALLOCATION**: o planejador fornece `num_equipes_por_item` por semana → determinístico, auditável, mas dependente de dados humanos
- **AUTO_SCHEDULE**: otimização automática via RCPSP (Resource-Constrained Project Scheduling Problem) → autônomo, mas com três lacunas críticas que o tornavam inoperante:

| Lacuna | Localização | Impacto |
|---|---|---|
| `_extract_activities()` cria atividades com `duration_weeks=1` e `required_resources={}` | `skill.py` linhas 119–138 | RCPSP resolve sem restrições reais → cronograma trivial |
| `_extract_pool()` retorna pool vazio se `canonical.recurso_pool` estiver vazio | `skill.py` linhas 151–159 | Sem restrições de capacidade → qualquer solução é factível |
| `spec_loader.py` sempre injeta `num_equipes_por_item` → modo MANUAL é sempre ativado em benchmarks | `spec_loader.py` linha 247 | AUTO_SCHEDULE nunca é exercitado nos benchmarks |

### O Problema RCPSP Formalmente

Dado:
- Conjunto de atividades $A = \{a_1, \ldots, a_n\}$ com durações $d_i \in \mathbb{Z}^+$ (semanas)
- DAG de precedência $G = (A, E)$ onde $(a_i, a_j) \in E \Rightarrow$ $a_i$ deve terminar antes de $a_j$ começar
- Conjunto de recursos renováveis $R = \{r_1, \ldots, r_m\}$ com capacidades $C_r \in \mathbb{Z}^+$ (unidades/semana)
- Demanda por recurso: $d_{ir} \in \mathbb{Z}^{\geq 0}$ (unidades de $r$ por semana enquanto $a_i$ está ativa)
- Horizonte de planejamento $T$ (deadline em semanas)

Minimizar o makespan $C_{max} = \max_i(s_i + d_i)$ sujeito a:

$$\forall (a_i, a_j) \in E: s_i + d_i \leq s_j \quad \text{(precedência)}$$

$$\forall t \in [1,T], r \in R: \sum_{a_i \text{ ativo em } t} d_{ir} \leq C_r \quad \text{(capacidade)}$$

$$s_i \geq 0, s_i \in \mathbb{Z} \quad \text{(integridade)}$$

### Dados Disponíveis (AGIS Benchmark)

| Campo | Fonte | Status |
|---|---|---|
| Durações $d_i$ | `cronograma.atividades[].duration_weeks` em `referencia.json` | ✅ Disponível |
| Demandas $d_{ir}$ | Derivado de `equipes.json` via mapeamento CPU → equipe | ✅ Modelado em `rcpsp_spec` |
| Capacidades $C_r$ | Máximo de equipes simultâneas por tipo | ✅ Modelado em `rcpsp_spec` |
| DAG de precedência | Regras de engenharia de terraplenagem ferroviária | ✅ Codificado em `rcpsp_spec` |

---

## Decisão

### D1 — Modelo de Recursos: Equipe como Tipo de Recurso

Recursos renováveis são **tipos de equipe** (`DESMAT`, `ESC-1CAT`, `ESC-2CAT`, `ESC-3CAT`, `ATERRO`), não recursos físicos individuais (operadores, escavadeiras). Cada unidade de recurso = uma equipe completa mobilizável.

**Justificativa**: Equipes são a unidade operacional de mobilização e custo. Esse nível de abstração corresponde aos dados de `equipes.json` e ao vocabulário dos planejadores.

**Conseqüência**: A composição interna de cada equipe (mão-de-obra + equipamentos) permanece em `equipes.json` como referência de custo, não como restrição de capacidade no RCPSP.

### D2 — Especificação RCPSP como Dado Explícito

A especificação RCPSP é codificada diretamente no `referencia.json` do benchmark como seção `rcpsp_spec`:

```json
{
  "rcpsp_spec": {
    "activities": [
      { "item_id": "<eap_id>", "duration_weeks": N, "required_resources": { "<tipo>": K } }
    ],
    "resource_pool": { "<tipo>": C },
    "precedence": [["<from_id>", "<to_id>"]]
  }
}
```

**Justificativa**: Separação de concerns — o _motor_ RCPSP (skill.py) é agnóstico ao domínio; os _dados_ RCPSP são responsabilidade do benchmark/projeto.

**Alternativas rejeitadas**:
- Derivar recursos automaticamente de CPU + catálogo: requer mapeamento CPU→equipe não trivial e introduce acoplamento entre catálogo e scheduler
- Usar `canonical.atividades` / `canonical.recurso_pool` (já existentes): exige enriquecimento por skills anteriores (Skill 00/01), que atualmente não injetam dados RCPSP

### D3 — Prioridade de Modo: `rcpsp_spec` Supera `num_equipes_por_item`

Quando `inputs["rcpsp_spec"]` está presente, Skill 02 usa **AUTO_SCHEDULE** independentemente de `num_equipes_por_item` estar também presente.

```
rcpsp_spec in inputs → AUTO_SCHEDULE (RCPSP)
                  ↓ else
num_equipes_por_item in inputs → MANUAL_ALLOCATION
                  ↓ else
canonical.activity_dag or canonical.atividades → AUTO_SCHEDULE (legacy canonical)
                  ↓ else
ERRO: modo não detectado
```

**Justificativa**: Permite que o mesmo benchmark execute em modo MANUAL (para validação de preços) e modo AUTO (para otimização de cronograma) sem modificação do código.

### D4 — Cadeia de Fallback RCPSP

```
[1] explore_schedules(heurísticas SGS)
    → se vazio:
[2] explore_schedules(pool relaxado ×1.1)
    → se vazio:
[3] MILPScheduler (CBC, 30s timeout)
    → se inviável:
[4] ERRO VAL-SCHED-05
```

**Justificativa**: SGS é fast e boa para problemas de médio porte. MILP garante ótimo para ≤50 atividades mas pode ser lento. Pool relax detecta infeasibility estrutural. (ADR-004 documentou a seleção de algoritmo.)

### D5 — Correção de `_infer_teams_from_resources`

`assigned_resources` em `ScheduledActivityCanonical` é **demanda por semana** (unidades/semana), não total acumulado. A função `_infer_teams_from_resources()` deve retornar `sum(assigned_resources.values())` diretamente.

**Justificativa**: O scheduler RCPSP atribui recursos por unidade de tempo (semana). O código antigo dividia pelo número total de semanas, que estava incorreto para este modelo.

### D6 — Precedência de Engenharia AGIS

Para o benchmark AGIS (terraplenagem ferroviária), as precedências codificadas em `rcpsp_spec.precedence` seguem as regras de domínio:

```
eap-1_0 (Desmatamento) → todos os itens de escavação (1_1, 1_2, 1_3, 1_4, 1_5, 1_6)
eap-1_5, eap-1_6 (Esc 3aCat) → eap-1_9 (Corpo Aterro 3aCat)
eap-1_9 (Corpo Aterro) → eap-1_7 (Compactação PN), eap-1_10 (Compactação Final)
```

**Justificativa**: Desmatamento é pré-condição física de qualquer escavação. O corpo de aterro é pré-condição de compactação. Escavações de 1ª e 2ª categoria podem correr em paralelo com 3ª categoria.

---

## Implementação

### Arquivos Modificados

| Arquivo | Mudança |
|---|---|
| `benchmarks/data/AGIS/referencia.json` | Adiciona seção `rcpsp_spec` com activities, resource_pool e precedence |
| `application/skills/manifests/02-cronograma/skill.py` | Adiciona `_extract_activities_from_spec()`, `_extract_pool_from_spec()`, `_extract_dag_from_spec()`; corrige `_infer_teams_from_resources()`; atualiza mode detection e `_run_auto_schedule_fallback_chain()` |
| `application/benchmarks/spec_loader.py` | Injeta `rcpsp_spec` em `inputs_cronograma` quando presente em `referencia.json` |

### Parâmetros RCPSP — AGIS

| Atividade | Duração (sem) | Recurso | Demanda/sem | Pool |
|---|---|---|---|---|
| eap-1_0 Desmatamento | 25 | DESMAT | 5 | 6 |
| eap-1_1 Esc 1aCat DMT≤2km | 45 | ESC-1CAT | 1 | 2 |
| eap-1_2 Esc 1aCat DMT≤3km | 45 | ESC-1CAT | 1 | 2 |
| eap-1_3 Esc 2aCat DMT≤2km | 51 | ESC-2CAT | 2 | 4 |
| eap-1_4 Esc 2aCat DMT≤3km | 51 | ESC-2CAT | 2 | 4 |
| eap-1_5 Esc 3aCat DMT≤2km | 49 | ESC-3CAT | 4 | 6 |
| eap-1_6 Esc 3aCat DMT≤3km | 49 | ESC-3CAT | 4 | 6 |
| eap-1_7 Compactação PN | 51 | ATERRO | 3 | 5 |
| eap-1_8 Compactação PI | 3 | ATERRO | 2 | 5 |
| eap-1_9 Corpo Aterro 3aCat | 52 | ESC-3CAT | 2 | 6 |
| eap-1_10 Compactação Final | 6 | ATERRO | 1 | 5 |

**Restrições vinculantes**: ESC-3CAT (pool=6; eap-1_5+eap-1_6 demandam 8 simultâneas → não podem rodar ao mesmo tempo) e ATERRO (pool=5; eap-1_7+eap-1_8+eap-1_10 demandam 6 total → eap-1_7 e eap-1_10 não podem ser simultâneas).

---

## Consequências

### Positivas
- AUTO_SCHEDULE agora é exercitável nos benchmarks AGIS
- rcpsp_spec é uma interface limpa: benchmarks declaram restrições sem codificação no motor
- Correção de `_infer_teams_from_resources` elimina bug de produção zero em AUTO mode
- Totalmente backward-compatible: benchmarks sem `rcpsp_spec` continuam em MANUAL mode

### Negativas / Limitações
- `rcpsp_spec` deve ser mantido manualmente para cada benchmark que usa AUTO mode
- CP-SAT (OR-Tools) não incluído nesta versão — MILP/SGS cobre o caso AGIS (11 atividades)
- A conversão de `assigned_resources → num_equipes → producao_semanal` ainda usa a produtividade horária do catálogo; para equipes cujo CPU não tem `producao_horaria`, produção será subestimada

### Decisões Futuras
- **ADR-047** (proposto): Derivação automática de `rcpsp_spec` a partir de CPU + `equipes.json` (eliminar especificação manual)
- **ADR-048** (proposto): Integração CP-SAT via OR-Tools para problemas com >50 atividades e alta criticidade
