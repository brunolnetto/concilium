# NEP-043 — Reconciliação C_r: Custo Operacional de Equipe deve ser idêntico ao PU de Catálogo

**Status:** ✅ Resolvido — com revisão de premissa _(2026-06-19)_  
**Prioridade:** ~~ALTA~~ — divergência metodológica curada; resíduo é eficiência de pool legítima (ADR-085)  
**Relacionado:** NEP-029 (calibração operacional↔catálogo), ADR-106 (LifecycleEngine), ADR-085 (Custo Instancial), ADR-114 (Golden invariante)

---

## Resolução (2026-06-19)

Os três bugs documentados foram **curados** em trabalho subsequente:

| Bug | Fix aplicado | Onde |
|---|---|---|
| 1 — ADR-091 divide sem compensar | `custo_total × num_equipes_base` na consolidação | `_consolidacao/_skill_helpers_a.py:95` (comentário NEP-043) |
| 2 — encargos ausentes em skill-06 | skill-06 usa `encargo_resolver.resolver_encargo()` | `_indiretos/_skill_helpers_a.py:208` |
| 3 — `custo_hora_total_referencia` ambíguo | `custo_inst_*` separa custo por frente; `num_equipes_base` aplicado. **Fechado definitivamente 2026-07-28** (worktree ADR-162, ver NEP-029): em vez de separar os dois usos por ADR (Fase 3 original), o campo foi removido de todo caminho de cálculo — bottom-up (corrigido ADR-132) já reproduz o valor sem precisar de referência alguma | `_consolidacao/_skill_helpers_a.py:486` |

**Evidência:** `test_cost_decomposition_adr104::test_agis_custo_direto_matches_reference`
passa com `custo_direto = 16.5M` (antes 22M divergente).

### Revisão de premissa (importante)

O título original exige **igualdade** (`custo_operacional = PU×Q`). Após o **ADR-085**
(Custo Instancial Composicional-Temporal), a relação correta é **desigualdade**:

```
custo_instancial ≤ custo_catálogo (Σ PU×Q)
```

O gap residual NÃO é bug — é a **eficiência de pool** (compartilhamento de recursos entre
atividades reduz o custo real abaixo da soma dos PU standalone). Esse invariante está
codificado como teste vivo no **ADR-114 Golden Example** (invariante 6:
`custo.direto_equipes ≤ Σ subtotal_sem_bdi`).

A divergência de 3.4× original era bug (n_frentes + encargos); o gap legítimo pós-fix é
muito menor e representa economia real de pool. **Esta NEP está fechada**; a vigilância
contínua é feita pelo golden invariante, não por uma meta de igualdade exata.

---

## Histórico original (pré-resolução)

---

## Problema

O custo operacional da atividade e o PU de catálogo derivam da **mesma fonte** (composição de equipes), mas seguem caminhos de código que não compartilham `C_r`. Resultado: no benchmark AGIS, `custo_execucao_pool = 22M` enquanto `PU×Q = 48M` — diferença de 3.4× que não representa economia de pool, mas divergência metodológica.

---

## Identidade Fundamental

O custo operacional de uma atividade `i` é:

```
custo_operacional_i = Σ_{j=1}^{N_i} n_j · Σ_{r ∈ R_i} C_r^{sem}
```

Onde `C_r^{sem}` é o custo semanal do recurso `r`:

| Tipo | C_r^{sem} |
|------|-----------|
| MO   | `(salário_base_r × (1 + encargos_r)) / semanas_por_mês` |
| EQ   | `(custo_locacao_r + custo_manutencao_r) / semanas_por_mês` |
| COMB | `consumo_r_L_h × horas_semana × preço_diesel` |

E o PU de catálogo é:

```
PU_i = Σ_{r ∈ R_i} C_r^{sem} / (P_i × horas_semana)
```

Logo, para `fator_clima = 1`:

```
custo_operacional_i = PU_i × Q_i
```

Esta identidade deve valer **tanto para o caminho skill-05 (equipe) quanto para o caminho skill-06 (precificação)**.

---

## Bugs Identificados (2026-06-11)

### Bug 1 — ADR-091 divide por n_frentes sem compensar na agregação (`custo.direto_equipes`)

**Localização:** `_skill_helpers_a.py:827` e `_consolidacao/_skill_helpers_a.py:252`

```python
# skill-05: armazena custo de 1 frente (divide por num_equipes_paralelas)
custo_total_ajustado = custo_total / max(num_equipes_paralelas, 1)

# consolidação: soma apenas 1-frente de cada atividade — ERRADO para n_max > 1
custo_direto_equipe = sum(float(e.custo_total or 0.0) for e in canonical_in.equipes_diretas)
```

**Impacto:** Para atividades com `n_max = k`, `custo.direto_equipes` contabiliza `1/k` do custo real.  
**Correção:** `custo_direto_equipe = Σ(e.custo_total × e.num_equipes_base)` na consolidação.

---

### Bug 2 — Encargos CLT incluídos em skill-05 mas ausentes em skill-06

**Localização:**  
- skill-05: `_skill_helpers_a.py:783` — `custo_mo = custo_mo_base + custo_encargos` ✓  
- skill-06: `_skill_helpers_b.py` — `PU_mo = Σ(preco_unitario_funcao / P_i)` — sem encargos ✗

**Mecanismo:** `encargo_resolver.resolver_encargo()` (centralizamos em NEP-037) é chamado em skill-05 mas não em skill-06. O `preco_unitario` dos insumos MO é a taxa base; o custo real é `preco_unitario × (1 + encargos)`.

**Impacto:** Para encargos CLT de 177.7% (`ENCARGOS_CLT = 0.7172` + demais grupos ≈ 1.777):  
`C_r_mo_skill06 = C_r_mo_skill05 / 2.777` → PU subestima o custo MO em ~64%.

**Correção:** skill-06 deve aplicar `encargo_resolver.resolver_encargo(atrib)` ao componente MO na derivação de PU a partir da `composicao_padrao_equipe`, quando `precos_unitarios_sbdi` não estiver disponível como fallback.

**Nota:** Para CPUs com `precos_unitarios_sbdi` preenchido (que já inclui encargos), skill-06 deve usar esse campo diretamente — sem recomputar. O recompute parcial via `composicao_itens` (incompleta em várias CPUs AGIS) gera inconsistência adicional.

---

### Bug 3 — `custo_hora_total_referencia` alimenta dois caminhos sem isolar impacto

**Localização:** `_skill_helpers_a.py:686-736` (`_calibrar_custos_por_cref`) e `:975-990` (`_resolve_custo_hora_ref_sem`)

O campo `custo_hora_total_referencia` na producao é lido tanto para:
1. Recalibrar custos mensais standalone (equipe autônoma)
2. Calcular `custo_hora_ref_sem` no caminho de pool contracts (pool path)

Quando setado como `sbdi.total × P_i`, o path de pool usa `C_ref` como custo de **1 recurso do pool por hora** — mas `C_ref` representa o custo de **toda a equipe (n recursos)** simultaneamente. Resulta em multiplicação por `n` implícita → inflação de `n×` no pool path.

**Correção:** Isolar os dois usos. Para pool path, `custo_hora_ref_sem` deve ser `C_ref / n_max` (custo por frente). Ou separar em dois campos distintos no catálogo.

---

## Plano de Correção

**Fase 1 (Bug 1 — sem impacto em gates externos):**
- Alterar `_br_build_venda_custo` para `Σ(e.custo_total × e.num_equipes_base)`
- Atualizar `custo_execucao_pool` na projection.py proporcionalmente

**Fase 2 (Bug 2 — requer alinhamento com referência planilha):**
- Decidir se PU_cat deve incluir encargos (comparar com referência AGIS planilha)
- Se sim: skill-06 usa `precos_unitarios_sbdi` como fonte primária de PU (já inclui encargos)
- Usar `encargo_resolver.resolver_encargo()` no caminho de fallback para CPUs sem sbdi

**Fase 3 (Bug 3 — requer ADR):**
- Definir semântica de `custo_hora_total_referencia`: custo da equipe completa ou por frente
- Separar em `custo_hora_total_equipe` (para calibração standalone) e `custo_hora_ref_frente` (para pool path)
- Documentar em ADR-091 ou novo ADR

---

## Relação com `encargo_resolver.py`

O módulo `src/concilium/domain/services/encargo_resolver.py` (criado nesta sessão) centraliza a resolução de encargos. Ele DEVE ser a fonte única para:
- skill-05 (já usa via `_resolve_encargo_funcao`)
- skill-06 (quando recomputar PU_mo a partir de insumos)
- `_calibrar_custos_por_cref` (via fração inferida de encargos)
- `equipe_custo_engine.py` (ADR-106)

Qualquer cálculo de `salário × (1 + x)` onde `x` é encargo trabalhista deve passar por `resolver_encargo()`.
