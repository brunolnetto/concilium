# ADR-072 — Direção A: Duração Produtiva e Restrição de Janela de Corredor

**Status:** Implementado  
**Data:** 2026-05-25  
**Autores:** Bruno Peixoto, Claude Sonnet 4.6  
**Contexto:** ADR-004 (RCPSP), ADR-046 (Corredor Ferroviário), ADR-071 (Contrato de Recurso)

---

## Contexto

No modelo RCPSP atual (ADR-046), o campo `duration_weeks` de cada atividade em
`rcpsp_spec.activities` é definido manualmente pelo planejador como a duração
do corredor físico (janela calendário). Isso faz com que o custo de cada equipe
seja calculado como:

```
custo_total = custo_unit_semanal × duration_weeks
```

Como `duration_weeks` representa o span do corredor (ex.: 25 semanas para
desmatamento), e não o tempo efetivamente produtivo, o custo por unidade fica
muito acima do preço de catálogo, gerando avisos `VAL-COB-NEG` (cobertura
negativa) e margens distorcidas.

**Exemplo AGIS — eap-1_0 (Desmatamento):**

| Parâmetro | Valor |
|-----------|-------|
| Q | 2 400 000 m² |
| P (produtividade) | 738 m²/h |
| n_resources (DESMAT) | 5 equipes |
| Regime | 8 h/dia × 6 dias/sem |
| `duration_weeks` (spec) | 25 semanas |
| Duração produtiva ADR-072 | `⌈2 400 000 / (738 × 8 × 6 × 5)⌉` = **14 semanas** |

Com `duration_weeks = 25`, o custo/m² é 79% maior que o catálogo.  
Com `duration_weeks = 14` (produtivo), o custo/m² se alinha ao catálogo.

---

## Decisão

### D1 — `duration_weeks` = duração produtiva

A partir desta ADR, quando `rcpsp_spec` é processado em skill-04 com acesso
ao catálogo, `duration_weeks` de cada `Activity` é derivado como:

```
productive_weeks = max(1, ⌈Q / (P × horas_dia × dias_semana × n_resources)⌉)
```

Onde:
- `Q` = `eap[item_id].quantitativo`
- `P` = `producao_lookup[cpu.producao_id_ref].valor_horario`
- `n_resources` = `sum(required_resources.values())`
- `horas_dia`, `dias_semana` = `canonical.projeto.regime_trabalho`

Se `productive_weeks < window_weeks`, a substituição é aplicada.  
Se o cálculo não é possível (falta de dados), `duration_weeks` mantém o valor
original da spec (comportamento legado, sem regressão).

### D2 — `window_weeks` armazena a janela de corredor original

O campo `Activity.window_weeks: int | None` (adicionado em `models.py`)
armazena o `duration_weeks` original da spec, representando o span calendário
do corredor. É `None` quando não há restrição de janela diferente do deadline
global.

### D3 — O scheduler respeita `window_weeks`

**SGS (`scheduler.py`):** `_find_start` impõe
`latest_start ≤ min(deadline, window_weeks) - duration_weeks`.

**MILP (`milp.py`):** `_build_decision_vars` impõe
`hi = min(hi, window_weeks - duration_weeks)`.

Isso garante que cada atividade termina dentro de sua janela de corredor.

### D4 — Compatibilidade com ADR-071

O modelo de contrato de recurso (ADR-071) já usa o schedule produzido pelo
RCPSP para calcular `semanas_contrato`. Com duração produtiva menor, os
contratos se tornam mais curtos e os custos atribuídos (`custo_total`) às
equipes diretas ficam mais precisos.

---

## Consequências

### Positivas

- Elimina (ou reduz substancialmente) avisos `VAL-COB-NEG` para projetos com
  `rcpsp_spec` configurado.
- Custo unitário das equipes diretas converge para o preço de catálogo.
- Contratos de recurso (ADR-071) menores → orçamento mais realista.
- O scheduler tem liberdade para posicionar atividades curtas dentro de
  janelas longas, otimizando nivelamento de recursos.

### Restrições / Riscos

- Requer `producao_id_ref` configurado na CPU. Se ausente, a ADR não tem
  efeito (fallback silencioso para `duration_weeks` original).
- `productive_weeks` pode ser subestimado se a produtividade do catálogo não
  refletir restrições de campo (solo rochoso, interferências, etc.). O
  planejador deve validar a plausibilidade.
- Atividades com `productive_weeks < window_weeks` podem ter slack elevado —
  o scheduler usará esse slack para nivelamento de recursos, o que é o
  comportamento desejado (ADR-046, corredor ferroviário).

---

## Alternativas rejeitadas

**Opção A (anterior) — `duration_weeks` = janela de corredor manual:**  
Custo inflacionado, `VAL-COB-NEG` persistente. Rejeitado.

**Opção B — campo `productive_weeks` separado em `rcpsp_spec`:**  
Requer que o planejador calcule e mantenha dois campos. Mais propenso a erros.
Rejeitado em favor de derivação automática a partir de Q/P.

---

## Arquivos afetados

| Arquivo | Mudança |
|---------|---------|
| `src/concilium/application/scheduling/models.py` | Adiciona `window_weeks: int \| None = None` a `Activity` |
| `src/concilium/application/scheduling/scheduler.py` | `_find_start` respeita `window_weeks` |
| `src/concilium/application/scheduling/milp.py` | `_build_decision_vars` respeita `window_weeks` |
| `src/concilium/application/skills/manifests/04-cronograma/skill.py` | `_compute_productive_weeks` + `_extract_activities_from_spec` estendidos; threading de `cpu_lookup`/`producao_lookup` |
