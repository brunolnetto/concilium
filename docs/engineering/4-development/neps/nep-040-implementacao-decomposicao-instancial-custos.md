# NEP-040: Implementação de Decomposição Instancial para Custos

**Status:** Implementado ✅ _(auditado 2026-06-08)_  
**Data:** 2026-06-07  
**Autor:** Engenharia de Implementação  
**Categoria:** Refatoração de Camada de Dados / Skill 05  
**Implementa:** ADR-092  
**Tipo:** Refactor estrutural

> **Nota de auditoria (2026-06-08):** Fases 1–4 implementadas — 5 campos `custo_inst_*` em
> `EquipeDireta` (canonical.py), `_enrich_equipes_com_decomposicao_instancial` presente em
> skill-05, `_accumulate_equipes` em `projection.py` usa `custo_inst_mo/eq/comb` quando
> disponíveis. Testes em `tests/integration/test_cost_decomposition_adr104.py`.
> Fase 5 (testes adicionais) e checklist do documento ainda marcados como `[ ]` — atualizar.  

---

## Contexto

ADR-092 decide que EquipeDireta deve ter decomposição de custos (`custo_inst_*`) como campos oficiais, eliminando divergências entre Skill 05, Skill 08 e report builder. Este NEP detalha **como implementar** essa decisão em 5 fases, com validações em cada passo.

---

## Problema a Resolver

Auditoria de 2026-06-07 revelou:
- Breakdown de custos não fecha (MO + EQ + COMB ≠ TOTAL)
- Equipamentos desaparecem na agregação (R$ 27.9M → R$ 0)
- Skill 05 calcula decomposição mas não a propaga para EquipeDireta
- Report builder tenta adivinhar com heurística quebrada

Impacto: Relatórios de benchmark AGIS mostram custos incorretos (-59% de erro).

---

## Solução em 5 Fases

### **Fase 1: Extensão do Modelo (15 min)**

**Objetivo**: Adicionar campos de decomposição a EquipeDireta

**Arquivo**: `src/concilium/domain/models/canonical.py`

**Mudança**:

```python
@dataclass
class EquipeDireta:
    # ... campos existentes (28 campos) ...
    custo_total: float
    
    # NOVOS (Fase 1):
    custo_inst_mo: float | None = None
    """Mão de obra instancial (Estágio 4). None = Estágio 1/3."""
    
    custo_inst_eq: float | None = None
    """Equipamentos instancial (Estágio 4). None = Estágio 1/3."""
    
    custo_inst_comb: float | None = None
    """Combustível/diesel instancial (Estágio 4). None = Estágio 1/3."""
    
    custo_inst_mat: float | None = None
    """Materiais instancial (Estágio 4). None = Estágio 1/3."""
    
    custo_inst_mob_demob: float | None = None
    """Mob + Demob instancial (Estágio 4). None = Estágio 1/3."""
    
    # INVARIANTE (documentação):
    # Se custo_inst_mo is not None:
    #   assert abs(custo_inst_mo + custo_inst_eq + custo_inst_comb + 
    #              custo_inst_mat + custo_inst_mob_demob - custo_total) < 0.05
```

**Teste**: `test_equipedireta_has_custo_inst_fields`

---

### **Fase 2: Enriquecimento em Skill 05 (20 min)**

**Objetivo**: Copiar decomposição de `contratos_recurso` para `equipes_diretas`

**Arquivo**: `src/concilium/application/skills/manifests/05-equipes-e-alocacao/_skill_helpers_a.py`

**Nova função**:

```python
def _enrich_equipes_com_decomposicao_instancial(
    equipes: list[EquipeDireta],
    contratos: list[RecursoContrato],
    validacoes: list[ValidacaoItem]
) -> None:
    """
    Enriquece equipes com decomposição de custos instanciais após ADR-085.
    
    Precondição: _aplicar_custo_instancial_adr085 já foi executado.
    Postcondição: equipe.custo_inst_* preenchidos para items em contratos.
    Invariante: soma(custo_inst_*) == custo_total (tolerância: R$ 0.05)
    """
    eq_by_id = {eq.item_id: eq for eq in equipes}
    
    for contrato in contratos:
        for part in contrato.particao_por_item:
            eq = eq_by_id.get(part.item_id)
            if eq is None:
                continue
            
            # Copiar decomposição de CustoParticionadoItem
            eq.custo_inst_mo = part.custo_inst_mo
            eq.custo_inst_eq = part.custo_inst_eq
            eq.custo_inst_comb = part.custo_inst_comb
            eq.custo_inst_mat = part.custo_inst_mat
            eq.custo_inst_mob_demob = round(
                part.custo_mob_imputado + part.custo_demob_imputado,
                2
            )
            
            # Validar invariante (detecção precoce)
            soma = (eq.custo_inst_mo + eq.custo_inst_eq + 
                   eq.custo_inst_comb + eq.custo_inst_mat + 
                   eq.custo_inst_mob_demob)
            desvio = abs(soma - eq.custo_total)
            
            if desvio > 0.05:
                validacoes.append(ValidacaoItem(
                    codigo="VAL-DECOMP-INVARIANTE",
                    status="ERRO",
                    mensagem=(
                        f"Item {part.item_id}: soma decomposição (R$ {soma:,.2f}) "
                        f"≠ custo_total (R$ {eq.custo_total:,.2f}). "
                        f"Desvio: R$ {desvio:.2f}"
                    )
                ))
```

**Onde chamar**: Em `skill.py`, após `_aplicar_custo_instancial_adr085()`

**Teste**: `test_enrich_copies_decomposition_from_particao`

---

### **Fase 3: Validações em Skill 05 (15 min)**

**Objetivo**: Adicionar 3 checkpoints para garantir invariante em cada estágio

**Arquivo**: `src/concilium/application/skills/manifests/05-equipes-e-alocacao/skill.py`

**Checkpoint 1 - Após Estágio 1** (linha ~95):

```python
equipes = _build_dimensionamento(canonical_in, inputs, catalogo, ctx, validacoes)

# VAL-ESTAG1: Sem pool contracts ainda, custo_inst_* deve ser None
for eq in equipes:
    if eq.custo_inst_mo is not None:
        validacoes.append(ValidacaoItem(
            codigo="VAL-ESTAG1-INST-NONE",
            status="ERRO",
            mensagem=f"Item {eq.item_id}: custo_inst_* deve estar None no Estágio 1"
        ))
```

**Checkpoint 2 - Após Estágio 3** (linha ~114):

```python
# VAL-ESTAG3: Pool contracts aplicados, mas decomposição ainda não feita
for eq in equipes:
    if eq.item_id in atribuicao:
        if eq.custo_inst_mo is not None:
            validacoes.append(ValidacaoItem(
                codigo="VAL-ESTAG3-INST-NONE",
                status="AVISO",
                mensagem=f"Item {eq.item_id}: custo_inst_* preenchido antes de ADR-085?"
            ))
```

**Checkpoint 3 - Após Estágio 4** (linha ~177):

```python
if instancias_recurso:
    _aplicar_custo_instancial_adr085(contratos_recurso, instancias_recurso, equipes, validacoes)
    _enrich_equipes_com_decomposicao_instancial(equipes, contratos_recurso, validacoes)
    
    # VAL-ESTAG4: Decomposição deve estar preenchida para items em contratos
    items_em_contratos = {
        item_id 
        for c in contratos_recurso 
        for item_id in c.items_cobertos
    }
    for eq in equipes:
        if eq.item_id in items_em_contratos and eq.custo_inst_mo is None:
            validacoes.append(ValidacaoItem(
                codigo="VAL-ESTAG4-INST-MISSING",
                status="ERRO",
                mensagem=f"Item {eq.item_id}: custo_inst_* deve estar preenchido no Estágio 4"
            ))
```

**Teste**: `test_skill05_validates_custo_inst_invariant_at_each_stage`

---

### **Fase 4: Report Builder - Consumo de Dados Oficiais (15 min)**

**Objetivo**: Atualizar `projection.py` para usar `custo_inst_*` quando disponível

**Arquivo**: `src/concilium/application/benchmarks/projection.py`

**Substituir função** `_accumulate_equipes()` (linhas 143-152):

```python
def _accumulate_equipes(equipes_diretas: list) -> dict[str, float]:
    """
    Acumula custos por categoria a partir de custo_inst_* quando disponível.
    
    Dois paths:
    1. Estágio 4 (com pool): usa custo_inst_* (decomposição oficial)
    2. Estágio 1/3 (sem pool): fallback heurístico (menos preciso)
    """
    totals = {
        "mao_obra": 0.0,
        "equipamentos": 0.0,
        "diesel": 0.0,
        "materiais": 0.0,
        "total": 0.0,
    }
    
    for equipe in equipes_diretas:
        # PATH 1: Se tem decomposição instancial (Estágio 4), usar dados oficiais
        if equipe.custo_inst_mo is not None:
            totals["mao_obra"] += equipe.custo_inst_mo
            totals["equipamentos"] += equipe.custo_inst_eq
            totals["diesel"] += equipe.custo_inst_comb
            totals["materiais"] += equipe.custo_inst_mat
            # custo_inst_mob_demob já está em custo_total, não somar separado
        
        # PATH 2: Sem decomposição, fallback (Estágio 1/3, sem pool contracts)
        else:
            if equipe.custo_fixo_mensal > 0:
                fator = equipe.custo_total / equipe.custo_fixo_mensal
                totals["mao_obra"] += equipe.custo_mao_obra_mensal * fator
                totals["equipamentos"] += equipe.custo_equipamentos_mensal * fator
                totals["diesel"] += equipe.custo_combustivel_total_mensal * fator
                totals["materiais"] += getattr(equipe, "custo_material_mensal", 0.0) * fator
    
    # Soma oficial (sempre consiste em custo_total)
    totals["total"] = sum(equipe.custo_total for equipe in equipes_diretas)
    
    return totals
```

**Teste**: `test_projection_breakdown_closes_with_instancia_decomposition`

---

### **Fase 5: Testes de Validação (20 min)**

**Objetivo**: Validar que breakdown agora fecha e invariantes são respeitadas

**Arquivo**: `tests/integration/test_cost_decomposition.py` (novo)

```python
import pytest

class TestCostDecompositionInvariant:
    """Testa que decomposição de custos é consistente em todos os estágios."""
    
    def test_equipedireta_has_custo_inst_fields(self):
        """EquipeDireta tem 5 campos de decomposição."""
        from concilium.domain.models.canonical import EquipeDireta
        eq = EquipeDireta(item_id="test", custo_total=100.0)
        assert hasattr(eq, "custo_inst_mo")
        assert hasattr(eq, "custo_inst_eq")
        assert hasattr(eq, "custo_inst_comb")
        assert hasattr(eq, "custo_inst_mat")
        assert hasattr(eq, "custo_inst_mob_demob")
    
    def test_enrich_copies_decomposition_from_particao(self, agis_benchmark):
        """Enriquecimento copia dados de CustoParticionadoItem."""
        canonical = agis_benchmark.canonical
        
        # Verificar: todos os items em contratos têm decomposição preenchida
        items_em_contratos = set()
        for contrato in canonical.contratos_recurso:
            for part in contrato.particao_por_item:
                items_em_contratos.add(part.item_id)
                # Verificar que o item em equipes_diretas tem decomposição
                eq = next((e for e in canonical.equipes_diretas 
                          if e.item_id == part.item_id), None)
                assert eq is not None, f"Item {part.item_id} não encontrado em equipes"
                assert eq.custo_inst_mo is not None, f"Item {part.item_id}: custo_inst_mo é None"
    
    def test_cost_decomposition_closes_with_pool_contracts(self, agis_benchmark):
        """Válida que custo_total == soma(custo_inst_*) após ADR-085."""
        canonical = agis_benchmark.canonical
        
        for eq in canonical.equipes_diretas:
            # Apenas items com pool contracts têm decomposição
            if eq.custo_inst_mo is not None:
                soma = (eq.custo_inst_mo + eq.custo_inst_eq + 
                       eq.custo_inst_comb + eq.custo_inst_mat + 
                       eq.custo_inst_mob_demob)
                desvio = abs(soma - eq.custo_total)
                assert desvio < 0.05, \
                    f"Item {eq.item_id}: decomposição não fecha " \
                    f"(soma={soma:,.2f}, total={eq.custo_total:,.2f}, desvio={desvio:,.2f})"
    
    def test_projection_breakdown_sums_correctly(self, agis_benchmark):
        """Valida que breakdown em report (MO+EQ+COMB+MAT) == total."""
        from concilium.application.benchmarks.projection import BenchmarkProjection
        
        projection = BenchmarkProjection.from_canonical(agis_benchmark.canonical)
        breakdown = projection.ferramenta_breakdown_direto
        
        if breakdown:
            componentes = (
                breakdown.get("mao_obra_total", 0) +
                breakdown.get("equipamentos_total", 0) +
                breakdown.get("diesel_total", 0) +
                breakdown.get("materiais_total", 0)
            )
            total = breakdown.get("direto_total", 0)
            
            # Agora deve fechar!
            assert abs(componentes - total) < 1.0, \
                f"Breakdown não fecha: componentes={componentes:,.2f}, total={total:,.2f}"
    
    def test_agis_custo_direto_is_correct(self, agis_benchmark):
        """AGIS: custo_direto deve ser R$ 46,843,791.49 (PU×Q)."""
        canonical = agis_benchmark.canonical
        
        custo_direto = sum(eq.custo_total for eq in canonical.equipes_diretas)
        
        # Esperado: R$ 46,843,791.49
        expected = 46_843_791.49
        desvio = abs(custo_direto - expected)
        
        # Tolerância: 0.1% de desvio é aceitável
        assert desvio < expected * 0.001, \
            f"AGIS custo_direto={custo_direto:,.2f}, esperado={expected:,.2f}, desvio={desvio:,.2f}"
```

**Executar**:
```bash
pytest tests/integration/test_cost_decomposition.py -xvs
```

---

## Checklist de Implementação

- [x] **Fase 1**: Adicionar campos a EquipeDireta (5 campos, 10 linhas)
- [x] **Fase 2**: Criar `_enrich_equipes_com_decomposicao_instancial()` (30 linhas)
- [x] **Fase 2**: Chamar nova função em skill.py (1 linha)
- [x] **Fase 3**: Adicionar 3 checkpoints em skill.py (15 linhas)
- [x] **Fase 4**: Refatorar `_accumulate_equipes()` em projection.py (25 linhas)
- [x] **Fase 5**: Implementar testes em `tests/integration/test_cost_decomposition_adr104.py`
- [ ] **Validação**: Rodar `pytest tests/integration/test_cost_decomposition_adr104.py` → pass
- [ ] **Benchmark**: Verificar breakdown fecha com custo_direto = R$ 46.8M (pool path)
- [ ] **Regressão**: Rodar `pytest tests/` → sem quebras

---

## Impacto de Linhas de Código

| Fase | Arquivo | Linhas Novas | Tipo |
|------|---------|--------------|------|
| 1 | canonical.py | +10 | campos |
| 2 | _skill_helpers_a.py | +30 | função nova |
| 2 | skill.py | +1 | chamada |
| 3 | skill.py | +15 | validações |
| 4 | projection.py | -10, +25 | refactor |
| 5 | test_cost_decomposition.py | +120 | testes |
| **TOTAL** | **6 arquivos** | **+191** | |

Commits esperados: 6 (1 por fase)

---

## Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|--------|-----------|
| Invariante viola em caso raro | 10% | M | Validação em Fase 3, tolerance 0.05 |
| Regressão em items sem pool | 5% | M | Fase 4 fallback heurístico preservado |
| Performance (overhead 5 campos) | <1% | L | 40 bytes por equipe, negligenciável |
| Merge conflict em canonical.py | 20% | L | Coordenar com main branch |

---

## Rollback Plan

Se descobertas críticas durante teste:

1. **Revert commits nesta ordem**: Fase 5 → 4 → 3 → 2 → 1
2. **Manter fields em EquipeDireta**: None por padrão (backward compatible)
3. **Repositório em estado limpo**: No breaking changes

---

## Aprovação e Próximos Passos

- [ ] Code Review: Arquitetura de ADR-092
- [ ] Approval: ADR-092 + NEP-040
- [ ] **Implementação**: Começar Fase 1

**Esperado**: 60 minutos de desenvolvimento + 30 min testes = 90 min (1.5h)

