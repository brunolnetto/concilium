# ADR-079: Ativação Econômica de Compartilhamento — G_r^viável, Matching Econômico, λ₀, custo_standby_idle, Desmobilização Antecipada

**Status:** Implementado  
**Data:** 2026-05-26  
**Autores:** Bruno Peixoto / Concilium  
**Dependências:** ADR-071, ADR-072, ADR-073, ADR-075, ADR-077, ADR-078

---

## 1. Contexto

O ADR-078 construiu a infraestrutura de pré-processamento estrutural: calcula `gap_r^max`,
`η`, `Ω`, `ΔC_pot` e `λ₀` para todos os pares de atividades que compartilham recursos.
O §11.2 do ADR-078 listou quatro lacunas que só seriam fechadas em uma próxima iteração:

| Lacuna | Componente afetado |
|---|---|
| `_build_perpetuation_chains` ignora `gap_r^max` — perpetua além do limite econômico | `_skill_helpers_a.py` |
| `_build_contratos_recurso` passa `custo_mob_unit=0.0` (TODO) | `_skill_helpers_a.py` |
| `custo_standby` usa `custo_unit_semanal` (custo plano) em vez de `c_idle` real | `_skill_helpers_a.py` |
| LNS inicia com `lambdas = {}` (ignora `λ₀` calculado pelo ADR-078) | `lns_scheduler.py` / `selector.py` |

O ADR-077 §8 também identificou:

| Lacuna | Componente afetado |
|---|---|
| Desmobilização antecipada não detectada | `_skill_helpers_a.py` / `canonical.py` |

Este ADR fecha todas essas lacunas.

---

## 2. Decisão

### A. custo_standby_idle

Substituir `contrato.custo_unit_semanal` por `contrato.custo_idle_semanal_unit` no cálculo
de `custo_standby` por instância e no `custo_standby_total` do `ResumoUtilizacaoContrato`,
**quando o campo estiver disponível** (`custo_idle_semanal_unit > 0`).

Motivação: `custo_unit_semanal` é a taxa média ponderada por machine-weeks (inclui
componentes produtivos como hora de operador). `c_idle` é o custo real incorrido quando
o recurso está parado — tipicamente 15–25% do custo produtivo. Usar o campo errado
superestima o custo de standby, distorcendo tanto o relatório ADR-077 quanto os limiares
de desmobilização antecipada.

### B. Desmobilização Antecipada

Identificar, por instância, as **semanas de standby no final do contrato** que poderiam
ser evitadas liberando o recurso mais cedo.

Definição: para a instância `i` do tipo `r`, com `last_active_week_idx[i]` e
`contract_end_idx` conhecidos:

```
trailing_standby_weeks_i = contract_end_idx - last_active_week_idx_i - 1
economia_desmob_i = max(0, c_idle × trailing_weeks_i - c_demob_unit)
```

A desmobilização só é vantajosa quando a economia de idle supera o custo de desmob.

Novos campos em `InstanciaRecurso`:
- `semana_ultima_atividade: str = ""` — última semana com atividade atribuída
- `semanas_antecipacao_possivel: int = 0` — semanas de trailing standby evitáveis
- `economia_desmobilizacao_antecipada: float = 0.0` — R$ economizáveis (≥ 0)

### C. G_r^viável — gap_max no chain builder

Adicionar parâmetro `gap_max: int = 9999` a `_build_perpetuation_chains`.
Quando `gap > gap_max`, **forçar quebra de cadeia**, independente do threshold de custo.

Isso garante que o grafo de perpetuações `Π` passado ao min-cost flow contém
apenas arestas que satisfazem `G_r^viável` (definido pelo ADR-078).

### D. Matching Econômico

Em `_build_contratos_recurso`, ler `resource_costs[tipo]` do `rcpsp_spec` e
passar os valores reais de `custo_mob_unit`, `custo_demob_unit` e
`custo_idle_semanal_unit` (como `custo_standby_unit`) ao `_build_perpetuation_chains`.

Também atualizar `RecursoContrato.custo_mob_desmob_contrato` com o valor real:

```
custo_mob_desmob = n_cadeias × (c_mob + c_demob) × quantidade_contratada
```

Antes do ADR-079, esse campo era fixado em `0.0` (TODO comment).

### E. λ₀ — Inicialização do LNS

Adicionar campo `initial_lambdas: dict[tuple[str,str,str], float] | None = None`
ao `LnsScheduler` dataclass.

No `schedule()`, inicializar:
```python
lambdas = dict(self.initial_lambdas) if self.initial_lambdas else {}
```

Em `explore_schedules()` de `selector.py`, aceitar parâmetro opcional
`initial_lambdas: dict | None = None` e passá-lo ao `LnsScheduler`.

Em `skill-04`, extrair `relatorio_oportunidades` do `canonical_in` e construir o
dicionário de lambdas a partir das oportunidades viáveis:
```python
{(op.atividade_i, op.atividade_j, op.tipo_id): op.lambda0
 for op in relatorio.oportunidades if op.economicamente_viavel}
```

---

## 3. Consequências

### 3.1 Imediatas (este ADR)

- **custo_standby** nas instâncias e resumos reflete o custo real de idle, não o custo produtivo
- **Desmobilização antecipada** detectável por instância, com economia potencial em R$
- **Perpetuação** nunca ultrapassa `gap_r^max` — grafo `Π` é `G_r^viável`
- **Matching** usa objetivos econômicos reais em vez de contagem
- **LNS** arranca de `λ₀ > 0` quando o pré-processamento ADR-078 foi executado,
  potencialmente reduzindo iterações necessárias para convergência

### 3.2 Compatibilidade retroativa

Todos os campos novos têm `default=0` / `default=""`. Projetos sem `resource_costs`
continuam funcionando exatamente como antes.

---

## 4. Testes

Arquivo: `tests/unit/test_adr079_ativacao_economica.py`

| Classe | Nº testes | O que cobre |
|---|---|---|
| `TestCustoIdleStandby` | 6 | `c_idle × standby` vs fallback para `custo_unit_semanal` |
| `TestDesmobilizacaoAntecipada` | 8 | trailing standby, economia, `semana_ultima_atividade` |
| `TestGrViavel` | 7 | `gap_max` pruning em `_build_perpetuation_chains` |
| `TestMatchingEconomico` | 5 | leitura de custos e passagem ao chain builder |
| `TestLambdaInicializacao` | 6 | `initial_lambdas` no LNS + wiring no selector |

Total: **32 testes**.

---

## 5. Relacionados

[[adr077-recurso-instancial]] [[adr078-pre-processamento-compartilhamento]]
[[adr073-adr074-implementation]] [[adr075-phase3-comparison-and-financial-analysis]]
