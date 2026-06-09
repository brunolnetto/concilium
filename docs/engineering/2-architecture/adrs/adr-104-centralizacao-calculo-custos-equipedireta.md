# ADR-104: Centralização de Cálculos de Custo em EquipeDireta

**Status:** Implementado ✅ _(auditado 2026-06-08)_  
**Data Proposta:** 2026-06-07  
**Autor:** Engenharia de Plataforma  
**Categoria:** Arquitetura de Dados / Modelos Canônicos  
**Relacionado:** NEP-040, Auditoria de Divergências de Custo (2026-06-07)

> **Nota de auditoria (2026-06-08):** 5 campos `custo_inst_*` presentes em `EquipeDireta`
> (canonical.py linhas 428–432) com invariante documentado. `_enrich_equipes_com_decomposicao_instancial`
> implementado em skill-05 `_skill_helpers_a.py`. Métricas de sucesso verificadas no AGIS.
> Próxima evolução: ADR-106 (engine unificado para diretas e indiretas).

---

## Contexto

### Problema Identificado

Skill 05 (Equipes e Alocação) calcula decomposição de custos instanciais (`custo_inst_mo`, `custo_inst_eq`, `custo_inst_comb`, `custo_inst_mat`, `custo_inst_mob_demob`) através da aplicação de ADR-085, mas **deixa essa decomposição confinada em `contratos_recurso[].particao_por_item[]`**.

Skill 08 (Consolidação Financeira) consome `equipes_diretas[].custo_total` **sem ter acesso** à decomposição, e o report builder (`projection.py`) tenta **adivinhar** a decomposição usando uma heurística inadequada:

```python
fator = equipe.custo_total / equipe.custo_fixo_mensal
totals["mao_obra"] += equipe.custo_mao_obra_mensal * fator
# ... resulta em breakdown que não fecha!
```

### Consequências

1. **Divergência de Dados**: Equipes com pool contracts têm decomposição correta em `contratos_recurso`, mas equipes_diretas não a reflete
2. **Breakdown Não Fecha**: `mao_obra + equipamentos + diesel ≠ total` no report
3. **Equipamentos Desaparecem**: Na agregação para benchmark, equipamentos (R$ 27.9M) não aparecem na soma
4. **Múltiplos Cálculos**: Skill 08 e report builder tentam recalcular o que Skill 05 já calculou
5. **Dificuldade de Debug**: Cálculo correto está em 3 lugares diferentes, com lógicas divergentes

### Situação Atual (Auditoria 2026-06-07)

```
Equipes com pool contracts (3 contratos):
  ✓ Estágio 4 (ADR-085): decomposição correta em particao_por_item
  ✓ custo_total = R$ 19,199,574.72 (agregado)
  ✗ equipes_diretas[]: custo_inst_* = None (sem decomposição)

Report builder:
  ✗ projection.py tenta recalcular com heurística quebrada
  ✗ Breakdown reporta: MO + EQ + COMB = 46.8M, mas total = 19.2M
  ✗ Diferença: R$ 27.6M (equipamentos desaparecem)
```

---

## Alternativas Consideradas

### A1: Status Quo (Rejeitada)
- Manter decomposição apenas em `contratos_recurso`
- ✗ Requer que skill 08 e report builder compiletem próprio accesso
- ✗ Impossível para itens sem pool contracts
- ✗ Proliferação de cálculos divergentes

### A2: CostCalculationEngine Sem Enriquecimento (Parcialmente Rejeitada)
- Criar `_cost_engine.py` que centraliza lógica de cálculo
- Skill 08 chama engine a cada vez que precisa decompor
- ✗ Requer recompute em cada acesso (performance)
- ✗ Skill 08 precisa de contexto (contratos, instâncias) que não possui
- ✓ Melhor que A1, mas incompleto

### A3: Enriquecer equipes_diretas Com Decomposição (Proposta ✅)
- Adicionar 5 campos `custo_inst_*` a EquipeDireta
- Após ADR-085, copiar decomposição de `contratos_recurso` para `equipes_diretas`
- Validar invariante em cada estágio
- Skill 08 e report builder consomem dados oficiais
- ✅ Single source of truth
- ✅ Sem recompute necessário
- ✅ Falha gracefully para itens sem pool contracts
- ✅ Suporta auditoria e rastreabilidade

---

## Decisão

Implementar **A3: Enriquecer equipes_diretas**.

Justificativa:
1. **Faz EquipeDireta completo**: `custo_total` + decomposição = fonte única de verdade
2. **Elimina recálculos**: Skill 08 usa dados pré-calculados
3. **Fix transitório**: Skill 05 garante invariante; report builder usa dados oficiais
4. **Escalável**: Futuros consumidores (análises, APIs) herdam dados corretos automaticamente
5. **Auditável**: Campo None → indicador de que Estágio 4 não foi executado

**Implementado via**: NEP-040 (5 fases, 1.5 horas de desenvolvimento)

---

## Design da Solução

### Extensão do Modelo CanonicalModel

```python
# src/concilium/domain/models/canonical.py

@dataclass
class EquipeDireta:
    # ... campos existentes ...
    custo_total: float  # Existente: custo agregado
    
    # Novos (Estágio 4): Decomposição instancial
    custo_inst_mo: float | None = None           # Mão de obra
    custo_inst_eq: float | None = None           # Equipamentos
    custo_inst_comb: float | None = None         # Combustível
    custo_inst_mat: float | None = None          # Materiais
    custo_inst_mob_demob: float | None = None    # Mob + Demob
    
    # Invariante (quando custo_inst_* != None):
    # custo_total == custo_inst_mo + custo_inst_eq + 
    #                custo_inst_comb + custo_inst_mat + custo_inst_mob_demob
```

### Fluxo de Preenchimento

```
Estágio 1 (_build_dimensionamento):
  equipe.custo_total = custo_total_final
  equipe.custo_inst_* = None  (não preenchido ainda)

Estágio 2 (_build_contratos_recurso):
  [cria contratos, não toca em equipes_diretas]

Estágio 3 (skill.py loop):
  equipe.custo_total = custo_attr  (atualiza com fração de pool)
  equipe.custo_inst_* = None  (ainda não decomposto)

Estágio 4 (_aplicar_custo_instancial_adr085):
  [calcula decomposição em particao_por_item]
  
Estágio 4b (NEW: _enrich_equipes_com_decomposicao_instancial):
  para cada contrato.particao_por_item[]:
    equipe.custo_inst_mo = part.custo_inst_mo
    equipe.custo_inst_eq = part.custo_inst_eq
    ... (copia 5 campos)
    
  Valida: soma(custo_inst_*) == custo_total (tolerância: R$ 0.05)
```

### Consumidores Beneficiados

| Consumidor | Atualmente | Com A3 |
|------------|-----------|--------|
| Skill 08 (_br_build_venda_custo) | Vê `custo_total` | Vê `custo_total` + `custo_inst_*` |
| Report builder (projection.py) | Tenta adivinhar decomposição | Usa dados oficiais direto |
| Análises futuras | Sem decomposição | Herdam automaticamente |
| Auditoria | Impossível rastrear | Campos None = Estágio 1, preenchido = Estágio 4 |

---

## Impacto

### Positivos
- ✅ Elimina divergências de cálculo (single source of truth)
- ✅ Report breakdown agora fecha (MO + EQ + COMB + MAT = TOTAL)
- ✅ Equipamentos deixam de desaparecer em agregações
- ✅ Skill 08 consome dados pré-calculados (sem overhead)
- ✅ Auditável: invariante validada em cada estágio
- ✅ Backwards compatible: campos None para Estágio 1/3

### Negativos / Riscos
- ⚠️ Ampliação de EquipeDireta em 5 campos (pequeno overhead de memória: ~40 bytes/equipe)
- ⚠️ Novo contrato entre Skill 05 e Skill 08 (mas melhora, não piora)
- ⚠️ Validação de invariante em Skill 05 (detecção precoce de bugs)

### Alternativas não Adotadas (Rejeitadas)
- **"Usar CustoParticionadoItem como novo EquipeDireta"**: Quebra contrato com Skill 08
- **"Copiar decomposição apenas em report builder"**: Permanece ad-hoc
- **"Criar sub-classe EquipeDiretaComDecomposicao"**: Overcomplica modelo

---

## Consequências

1. **Modelo**: EquipeDireta cresce para 33 campos (era 28)
2. **Skill 05**: Novo passo `_enrich_equipes_com_decomposicao_instancial()` após ADR-085
3. **Validações**: 3 checkpoints adicionados em skill.py para detectar invariante violada
4. **Skill 08**: Sem mudanças (backwards compatible, lê mesmos campos)
5. **Report Builder**: Simplificação: usa `custo_inst_*` quando preenchido, fallback heurístico caso contrário
6. **Testes**: 2 novos testes de invariante (`test_cost_decomposition_closes_*`)

---

## Implementação

Detalhes técnicos: **NEP-040** (5 fases, cronograma)

Arquivos a modificar:
1. `domain/models/canonical.py` — Adicionar 5 campos + invariante documentada
2. `_skill_helpers_a.py` — Nova função `_enrich_equipes_com_decomposicao_instancial()`
3. `skill.py` — Chamar nova função + 3 validações
4. `benchmarks/projection.py` — Atualizar `_accumulate_equipes()` para usar `custo_inst_*`
5. `tests/` — Novos testes de invariante

---

## Métricas de Sucesso

- [ ] EquipeDireta tem campos `custo_inst_*`
- [ ] Após Estágio 4, todos os items com pool contracts têm `custo_inst_*` preenchidos
- [ ] Invariante validada: desvio < R$ 0.05 em 100% das equipes
- [ ] Report breakdown fecha: `soma(custo_inst_*) == custo_total`
- [ ] AGIS benchmark: custo_direto reportado = R$ 46,843,791.49 (correto)
- [ ] Testes de regressão: 100% pass

---

## Referências

- **Auditoria de Divergências**: Documento de auditoria completo em `/tmp/cost_divergence_audit_final.md`
- **ADR-085**: Custo instancial (mob/demob/ocioso)
- **ADR-071**: Pool contract model
- **Skill 05**: `src/concilium/application/skills/manifests/05-equipes-e-alocacao/`
- **Skill 08**: `src/concilium/application/skills/manifests/08-consolidacao-financeira/`

---

## Aprovação

- [ ] Arquiteto: 
- [ ] Tech Lead Skill 05: 
- [ ] Tech Lead Skill 08: 
- [ ] Analista de Qualidade:
- [ ] Data: 

