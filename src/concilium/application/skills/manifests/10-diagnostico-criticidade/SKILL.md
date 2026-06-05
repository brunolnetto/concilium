---
name: 10-diagnostico-criticidade
description: Use when producing a 360° health diagnosis of the project — ranks activities by schedule criticality, cost exposure, resource conflicts and margin sensitivity using Pareto classification.
---

# Skill 10 — Diagnóstico de Criticidade

Produz o diagnóstico de saúde 360° do projeto em quatro dimensões: Prazo, Custo, Recurso e Sensibilidade. Classifica atividades em A+/A/B/C usando ranking Pareto lexicográfico e identifica quais atividades concentram maior risco. Consolida as antigas skills 08 e 09.

## Quando ativar

Após `06-precificacao-unitaria` ter calculado os preços e `05-equipes-e-alocacao` ter calculado equipes e alocações. Não requer `08-consolidacao-financeira` — pode rodar em paralelo com ela.

## Inputs

Nenhum input do usuário — opera exclusivamente sobre o canônico já construído pelas skills predecessoras.

## Depende de

**Skills predecessoras**:
- [`04-cronograma`](../04-cronograma/SKILL.md) — `cronograma.scheduled_activities` com `distribuicao_semanal`
- [`05-equipes-e-alocacao`](../05-equipes-e-alocacao/SKILL.md) — `equipes_diretas` com custos e `alocacoes`
- [`06-precificacao-unitaria`](../06-precificacao-unitaria/SKILL.md) — `planejamento` com PU e subtotais

## Produz

**Seção do canônico**: `cost_criticality_report` (`CostCriticalityResult`)

| Sub-campo | Tipo | Descrição |
|-----------|------|-----------|
| `profiles` | `list[CriticidadeProfile]` | Um perfil por atividade com scores nas 4 dimensões |
| `ranking_global` | list | Atividades ordenadas por score composto |
| `frontier_ids` | list | Atividades na fronteira de Pareto (dominam em ≥2 dimensões) |
| `summary` | dict | Contagem por classe A+/A/B/C; estatísticas de desvio |

**Campos por `CriticidadeProfile`**:
- `atividade_id`, `cpu_id`, `descricao`
- `dimensoes`: `{prazo, custo, recurso, sensibilidade}` — cada uma com `score`, `rank`, `classe`
- `classe_global`: classificação final A+/A/B/C
- `on_frontier`: True se domina em ≥2 dimensões simultaneamente

**Validações**:
- `VAL-DIAG-OK` — diagnóstico executado com sucesso

## Lógica de classificação

### Dimensão Prazo
- `score = semana_fim / makespan_total` — quanto mais tarde termina, mais crítica
- Atividades com float zero = mais críticas (no caminho crítico)

### Dimensão Custo
- `score = custo_total_equipe / custo_total_projeto`
- Ranking descendente: maior custo absoluto = maior criticidade

### Dimensão Recurso
- `score = max(utilizacao_semanal / pool_disponivel)` para o recurso mais demandado
- Detecta semanas de pico de utilização

### Dimensão Sensibilidade
- `score = |delta_margem_estimado_se_prazo_aumenta_10%|`
- Calcula o impacto na margem de um atraso de 10% na atividade

### Classificação Pareto (A+/A/B/C)
```
Para cada atividade, rank_global = rank lexicográfico ponderado:
  score_composto = 0.4×prazo + 0.3×custo + 0.2×recurso + 0.1×sensibilidade

Limites:
  A+ : on_frontier AND rank ≤ ceil(N × 0.20)
  A  : rank ≤ ceil(N × 0.40)
  B  : rank ≤ ceil(N × 0.70)
  C  : demais
```

## Exemplo de output

```json
{
  "cost_criticality_report": {
    "profiles": [
      {
        "atividade_id": "eap-1_0",
        "classe_global": "A+",
        "on_frontier": true,
        "dimensoes": {
          "prazo":       {"score": 0.91, "rank": 1, "classe": "A+"},
          "custo":       {"score": 0.43, "rank": 2, "classe": "A"},
          "recurso":     {"score": 0.87, "rank": 1, "classe": "A+"},
          "sensibilidade": {"score": 0.62, "rank": 3, "classe": "A"}
        }
      }
    ],
    "frontier_ids": ["eap-1_0", "eap-3_0"],
    "summary": {"A+": 2, "A": 5, "B": 8, "C": 12}
  }
}
```

## Notas de implementação

- O `cost_criticality_report` é consumido por `11-avaliacao-intervencoes`, `13-assessor-replanejamento`, `14-explorador-cenarios` e `15-relatorio-executivo`. Skills que dependem desta devem verificar `canonical.cost_criticality_report is not None` antes de operar.
- A fronteira de Pareto (`frontier_ids`) é o conjunto de atividades que não são dominadas em todas as dimensões por nenhuma outra — representa o conjunto irredutível de riscos do projeto.
- O score de prazo usa `_periodo_to_ordinal()` para normalizar chaves de semanas ISO e períodos mensais para uma escala comparável.

## Próximas skills no pipeline

- [`11-avaliacao-intervencoes`](../11-avaliacao-intervencoes/SKILL.md)
- [`13-assessor-replanejamento`](../13-assessor-replanejamento/SKILL.md)
- [`14-explorador-cenarios`](../14-explorador-cenarios/SKILL.md)
- [`15-relatorio-executivo`](../15-relatorio-executivo/SKILL.md)
