# NEP-048 — Review: Composição de Times Indiretos

**Data:** 2026-06-19  
**Status:** ✅ Fechado — B1/B2 curados; B3/B4 deprecados como limitações aceitas _(2026-06-19)_  
**Contexto:** Revisão da lógica de times indiretos (skill-06/_skill_helpers_b.py)  
**Relacionado:** ADR-009 (Indirect Costs as First-Class), ADR-090 (BDI Sistemático), ADR-105 (Mob/Demob)

---

## Decisão de fechamento (2026-06-19)

- **B1, B2:** ✅ **Curados** — `mob_result` conectado; `custo*0.15` → `custo` real.
- **B3** (`custo_pessoa_mes=1850` legado): ⬜ **Deprecado como limitação aceita.** Só
  dispara no path legado sem `IndirectoCategoria`. Projetos atuais usam o path novo.
  Não há demanda para derivar do catálogo enquanto o legado não for reativado.
- **B4** (`_comp_custo` mistura `custo_total`/`custo_fixo_mensal`): ⬜ **Deprecado como
  limitação estrutural conhecida.** Mitigado pela correção de 2026-06-11 (resíduo→verba).
  Cura completa exige refatorar `IndirectoCategoria` para carregar duração nos componentes
  — escopo de ADR próprio, sem demanda concreta. Documentado para não recorrer ao
  diagnóstico do zero.

---

## Achados do Review

### B1 — Bug Crítico: `mob_costs` calculado e descartado (dead code)

**Localização:** `_indiretos/_skill_helpers_b.py:256-271` (antes da correção)

O bloco `if mob_schedule:` em `_process_mob_categoria()` calculava
`mob_costs = calcular_custo_indireto_mob(...)` mas terminava com `pass`,
descartando silenciosamente o resultado. O custo MOB sempre usava o caminho legado,
mesmo quando `mob_schedule` estava disponível (que é o caso normal após skill-04/RCPSP).

```python
# ANTES (bug — dead code):
mob_costs = calcular_custo_indireto_mob(indiretos_mob, mob_schedule)
# TODO: Melhorar distribuição com dados de spec.indiretos
pass  # Fallback para comportamento legado

# DEPOIS (corrigido):
mob_result = calcular_custo_indireto_mob(indiretos_mob, mob_schedule)
mob_total = mob_result.get("custo_mob_total", 0.0)
if mob_total > 0:
    custo = round(mob_total, 2)
    cat_obj = cat_obj.model_copy(update={"custo_fixo_total": custo})
```

**Impacto antes da correção:** Custo MOB nunca refletia as janelas reais de mobilização
do mob_schedule (ADR-105). O custo MOB era sempre calculado pelo método legado
(distância × custo_km + pessoas × prazo), independentemente do cronograma otimizado.

### B2 — Bug: `custo * 0.15` hardcoded como input de calcular_custo_indireto_mob

**Localização:** Mesmo bloco, linha anterior à B1

`indiretos_mob` passava `"custo_fixo_total": custo * 0.15` — 15% arbitrário sem
justificativa. O correto é passar o custo total da categoria MOB.

**Corrigido:** usar `custo` diretamente (o valor total já calculado de spec ou legado).

### B3 — Limitação Conhecida: `custo_pessoa_mes = 1850` hardcoded no legado

**Localização:** `_custo_mob_composicional()`, linha `custo_pessoa_mes = dados_mob.get("custo_pessoa_mes", 1850)`

R$ 1.850/pessoa/mês é um valor de 2024 não atualizado. Idealmente derivar do catálogo
(custo de diária de campo ou similar). Documentado com comentário `# B3-known`.

**Impacto:** Apenas ativa quando `dados_mob` não fornece `custo_pessoa_mes` explícito.
Para projetos com `IndirectoCategoria` bem preenchido (path novo), não é acionado.

### B4 — Limitação Estrutural: `_comp_custo` mistura `custo_total` e `custo_fixo_mensal`

**Localização:** `_sub_custos_indireto()`, função `_comp_custo`

```python
def _comp_custo(comp) -> float:
    if hasattr(comp, "custo_total") and (comp.custo_total or 0.0) > 0:
        return float(comp.custo_total)
    return float(comp.custo_fixo_mensal or 0.0)  # ← unidades diferentes!
```

`custo_total` é valor absoluto (já escalado pela duração).
`custo_fixo_mensal` é taxa mensal (precisa multiplicar por n_meses).

Quando a composição tem alguns componentes com `custo_total` e outros apenas com
`custo_fixo_mensal`, o escalonamento via `scale = custo_total / c_base` compensa
parcialmente mas pode gerar proporções erradas entre componentes.

**Mitigação existente:** A correção de 2026-06-11 (linha 360-369) já endereça o caso
mais comum (resíduo vai para verba). Mas o problema fundamental permanece para
composições mistas.

**Não corrigido neste NEP:** Requer refatorar como `IndirectoCategoria` armazena
durações nos componentes — escopo de ADR separado.

---

## O que está funcionando corretamente

- **Decomposição por sub-categoria (ADR-090):** `_sub_custos_indireto` escala os
  sub-custos proporcionalmente ao `custo_total` final — a soma sempre fecha.
- **BDI diferenciado por categoria_insumo:** MO→30%, EQUIP→30%, COMB→4%, VERBA→25.2%
- **Encargos separados em MO indireta (NEP-037 D4):** `frac_enc` isola encargos sociais
  da base salarial.
- **Validação de razão indireto/direto:** `_validate_razao_indireto_direto` emite
  `VAL-IND-RAZ-01` quando razão está fora do alvo do perfil.
- **Fallback conservador:** Quando composição está ausente, tudo vai para verba
  (taxa mais alta → posição conservadora no BDI).

---

## Correções Aplicadas (2026-06-19)

| Bug | Arquivo | Linha | Fix |
|---|---|---|---|
| B1 | `_skill_helpers_b.py` | 255-271 | Conectar `mob_result` ao `custo` e `cat_obj`; `logger.warning` se falhar |
| B2 | `_skill_helpers_b.py` | 265 | `custo * 0.15` → `custo` |
| Logger | `_skill_helpers_b.py` | topo | Adicionar `logger = logging.getLogger(__name__)` |
| B3 | `_skill_helpers_b.py` | 192 | Comentário `# B3-known` para rastreabilidade |

---

## Trabalho Futuro

1. **ADR-105 F5-F6** (pendente): distribuição completa MOB por fase (mobilização,
   operação, desmobilização) com timing do mob_schedule
2. **B4**: refatorar `IndirectoCategoria` para armazenar duração explícita em componentes,
   eliminando a ambiguidade `custo_total` vs `custo_fixo_mensal`
3. **B3**: derivar `custo_pessoa_mes` do catálogo de insumos de MO quando disponível
