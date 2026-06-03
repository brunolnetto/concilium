# ADR-091 — Pool Mínimo como Variável de Otimização: Eliminação de `rcpsp_spec.resource_pool` como Entrada

**Status:** ✅ Implementado — UI do objetivo de pool no formulário fica com ADR-092
**Data:** 2026-05-30
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-046 (RCPSP), ADR-071 (Pool Contracts), ADR-088 (sub-campos EQ), ADR-092

---

## Contexto

### Problema

P1. `rcpsp_spec.resource_pool` é um dicionário `{tipo_recurso: N_r}` que o usuário
fornece explicitamente. Expõe detalhe de implementação do RCPSP: o usuário precisa
saber o que é "tipo de recurso", quantas unidades contratar e o que é um pool —
conceitos técnicos irrelevantes para um engenheiro de obra.

P2. O pool correto é função do makespan desejado, não um dado externo independente.
Fornecer um pool errado torna o RCPSP inviável ou subótimo, sem indicação clara para
o usuário de como corrigi-lo.

P3. A composição de cada atividade (CPU → equipamentos) já define implicitamente
a necessidade de recursos. Exigir que o usuário reexprima essa informação como
`resource_pool` é redundância que cria oportunidade de inconsistência.

---

## Decisão

D1. **`resource_pool` deixa de ser entrada de usuário.** O parâmetro é eliminado da
interface pública. O sistema o deriva internamente como `peak_demand_r` do schedule
RCPSP sem restrição de pool.

D2. **Entrada do usuário: objetivo de prazo.** A única entrada necessária é:

```python
pool_config = {
    "objetivo": "minimizar_prazo" | "minimizar_custo" | "balanceado",
    "prazo_maximo_semanas": int | None,
    "restricoes_mercado": {"ESC-3CAT": 4}   # disponibilidade de mercado (opcional)
}
```

D3. **Pipeline de derivação automática `_inferir_pool_minimo`.**

```python
def _inferir_pool_minimo(canonical_in, pool_config) -> dict[str, int]:
    """
    1. Extrai e_{i,r} de EquipeDireta.equipamentos (composição por atividade)
    2. Executa RCPSP sem restrição de pool (recursos ilimitados)
    3. Calcula peak_demand_r por tipo de recurso no schedule resultante
    4. Aplica restrições de mercado se fornecidas
    5. Retorna {tipo_r: N_r*} — o pool mínimo para o objetivo escolhido
    """
```

- `objetivo="minimizar_prazo"` → pool = `peak_demand` do schedule sem restrição
- `objetivo="minimizar_custo"` → pool = `max_i(e_{i,r})` (schedule totalmente serial)
- `"balanceado"` → Pareto-optimal via bisect entre os dois extremos

D4. **`e_{i,r}` derivado de `EquipeDireta.equipamentos`.**

```python
e_i_r = sum(
    equip.num_unidades
    for equip in equipe.equipamentos
    if equip.equip_id == tipo_recurso_r
)
```

O mapeamento `equip_id → tipo_recurso` vem do catálogo.

D5. **`rcpsp_spec` completo é artefato interno** — construído em skill-05, nunca
exposto na interface do usuário ou no MCP.

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| R1 | Manter `resource_pool` como entrada obrigatória | Vaza detalhe técnico; usuário não sabe o que é |
| R2 | Derivar pool fixo sempre como `max_i(e_{i,r})` | Ignora paralelismo; subotimiza makespan |
| R3 | Expor o tradeoff como configuração avançada opcional | Complexidade desnecessária para o caso comum |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Interface limpa | Usuário exposto apenas a objetivos de negócio (prazo, custo, equilíbrio) |
| Pool sempre correto | Pool mínimo derivado do problema, sem risco de inconsistência manual |
| Backward compat | Projetos de calibração histórica com `resource_pool` explícito continuam funcionando como override |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Mapeamento `equip_id → tipo_recurso` precisa manutenção | Centralizar no catálogo com validação automática |
| Pool "balanceado" requer múltiplas execuções RCPSP | Implementar bisect eficiente; cache do schedule por makespan |
| Objetivo mal definido pelo usuário gera pool subótimo | Defaults sensatos; mostrar tradeoff tempo-custo antes de confirmar |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| 1 | `tipo_recurso_de_equip` + `derivar_required_resources` + `validar_equipamentos_mapeaveis`; derivação de `e_{i,r}` de `EquipeDireta.equipamentos` integrada à inferência | ✅ Implementado |
| 2 | `inferir_pool_minimo` + `inferir_pool_minimo_from_spec` (módulo `scheduling/pool_inference.py`) | ✅ Implementado |
| 3 | `resource_pool` ausente/vazio → pool derivado (skill-04 `_extract_pool_from_spec`; fallback idempotente em skill-05); pool explícito vira override | ✅ Implementado |
| 4 | `pool_config` como entrada first-class (inputs→rcpsp_spec→inferência em skill-04; `pool_config` na referência via spec_loader). Widget no formulário QQP/EAP fica com ADR-092 | ✅ Implementado (plumbing) |
| 5 | Testes unitários (19) + regressão AGIS (override, exit 0) | ✅ Implementado |

### Notas de implementação

- **Onde a inferência roda:** `_extract_pool_from_spec` (skill-04) é o consumidor
  primário do pool e onde o RCPSP executa — portanto é o ponto natural de derivação.
  O pool inferido é gravado de volta em `spec['resource_pool']` (visto por skill-05 e
  pela persistência) e o tradeoff tempo×custo é registrado em `spec['pool_inferido_diag']`
  + validação `VAL-POOL-INFER`. Skill-05 tem fallback idempotente.
- **Estratégia de derivação:** `peak_demand` (RCPSP sem restrição via `SerialScheduler`)
  define o extremo de prazo mínimo; `serial_min = max_i(e_{i,r})` o extremo de custo
  mínimo. `balanceado` faz bisseção entre os dois respeitando `prazo_maximo_semanas`
  (ou `deadline_weeks`).
- **Fase 1 (equip→tipo):** `tipo_recurso_de_equip` resolve via mapa explícito do
  catálogo ou convenção `EQUIP-{equip_id}`; `derivar_required_resources` produz
  `e_{i,r} = num_equipes_base × Σ num_unidades`. Quando a spec não traz
  `required_resources`, a inferência usa esse `e_{i,r}` derivado das equipes.
- **Backward compat:** `resource_pool` explícito (AGIS) segue como override — gate verde.

### Notas de implementação

- **Onde a inferência roda:** `_extract_pool_from_spec` (skill-04) é o consumidor
  primário do pool e onde o RCPSP executa — portanto é o ponto natural de derivação.
  O pool inferido é gravado de volta em `spec['resource_pool']` (visto por skill-05 e
  pela persistência) e o tradeoff tempo×custo é registrado em `spec['pool_inferido_diag']`
  + validação `VAL-POOL-INFER`. Skill-05 tem fallback idempotente para o caso de o
  `rcpsp_spec` ser serializado entre skills.
- **Estratégia de derivação:** `peak_demand` (RCPSP sem restrição de pool, via
  `SerialScheduler`) define o extremo de prazo mínimo; `serial_min = max_i(e_{i,r})` o
  extremo de custo mínimo. `balanceado` faz bisseção entre os dois respeitando
  `prazo_maximo_semanas` (ou `deadline_weeks` do projeto) — menor pool que ainda cumpre
  o prazo, o default economicamente sensato.
- **Backward compat:** projetos de calibração (AGIS) com `resource_pool` explícito
  seguem como override — zero mudança de comportamento (gate AGIS verde).

## Definition of Done

### Fase 1
- [ ] Tabela de mapeamento `equip_id → tipo_recurso` no catálogo
- [ ] Validação: toda EquipeDireta tem todos equipamentos mapeáveis

### Fase 2
- [ ] `_inferir_pool_minimo` retorna pool válido para os três objetivos
- [ ] Pool derivado produz schedule RCPSP factível
- [ ] Restrições de mercado aplicadas corretamente

### Fase 3
- [ ] Pipeline skill-05 funciona sem `rcpsp_spec.resource_pool` no input
- [ ] Backward compat: `resource_pool` explícito no input ainda funciona como override

### Fase 4
- [ ] `pool_config` integrado ao formulário QQP/EAP (ADR-092)

### Fase 5
- [ ] Projeto de produção executado end-to-end sem `resource_pool` manual
- [ ] Projeto de calibração histórica (AGIS) ainda funciona como caso de regressão

---

## Relacionados

[[adr046-rcpsp-complete-implementation]] [[adr071-resource-contract-model]]
[[adr088-decomposicao-subcomposicional-equipamento]] [[adr092-formulario-qqp-eap]]
