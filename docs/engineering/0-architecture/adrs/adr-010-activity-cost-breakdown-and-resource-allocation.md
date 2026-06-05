# ADR-010: Activity Cost Breakdown: Direct + Indirect Resource Allocation & Mobilization

**Status:** Implementado  
**Date Decided:** 2026-05-02  
**Date Implemented:** 2026-05-02  
**Implementers:** canonical.py (AtividadeCustoCompleto, CustoIndiretoAtividade), models/cost_breakdown.py  
**Context:** From ADR-009, we have **insumo cost pools** at the project level:
- **Indirect Permanência** (shared across all activities): TOP, ADM, LAB, QSMS
- **Indirect One-Time** (project setup/teardown): MOB

However, **activities are the unit of execution and cost tracking**. Each activity:
1. Has its own **direct costs** (labor, equipment, materials specific to the deliverable)
2. **Consumes shares** of the indirect cost pools (e.g., Activity A uses 15% of TOP, 8% of LAB)
3. May have **activity-specific mobilization** (setup phase, teardown phase)
4. Has a **weekly schedule** (ADR-003) during which costs are incurred

**Problem:** ADR-009 defines pools, but doesn't clarify:
- How activities request resources from pools
- How to allocate indirect costs to activities (by effort? by duration? by consumption?)
- How activity-level costs roll up to project total
- How activity replanning affects cost distribution

---

## Decision

We formalize **activity-level cost model** where each activity decomposes costs into:
1. **Direct costs** (activity-specific insumos)
2. **Indirect cost consumption** (share of project-wide pools)
3. **Activity-specific mobilization** (optional one-time setup/teardown)

### D1 — Activity Direct Costs

Each activity has explicit direct cost components (same structure as ADR-009 insumos):

```python
class AtividadeInsumo(BaseModel):
    """Direct cost insumo for an activity."""
    
    categoria: str  # e.g., "Escavação", "Fundações", "Estrutura", "Acabamento"
    
    # Components (universal: MO, EQUIP, MATERIAL)
    mao_de_obra: Optional[InsumoComponent]
    equipamentos: Optional[InsumoComponent]
    material: Optional[InsumoComponent]
    
    # Base cost (total for activity duration)
    custo_total_direto: float = (
        (mao_de_obra.custo_fixo_base or 0) +
        (equipamentos.custo_fixo_base or 0) +
        (material.custo_fixo_base or 0)
    )
    
    # Breakdown by component
    def componentes_breakdown(self) -> dict[str, float]:
        return {
            "mao_de_obra": mao_de_obra.custo_fixo_base or 0,
            "equipamentos": equipamentos.custo_fixo_base or 0,
            "material": material.custo_fixo_base or 0,
        }
```

---

### D2 — Indirect Cost Allocation (Pool Share Per Activity)

Each activity consumes a **share** of the indirect cost pools. Three allocation strategies:

#### Strategy A: By Effort (MO Hours)
Activity's MO hours ÷ Total MO hours across all activities → % of indirect pools

#### Strategy B: By Duration (Weeks)
Activity's duration ÷ Total project duration → % of indirect pools

#### Strategy C: By Explicit Consumption Factor
Activity specifies: "I need 20% TOP, 10% LAB, 5% QSMS" (negotiated with project manager)

```python
class IndiretoAlocacao(BaseModel):
    """How activity shares indirect cost pools."""
    
    estrategia: Literal["esforco_mo", "duracao", "fator_explicito"]
    
    if estrategia == "esforco_mo":
        # Calculated from MO hours
        percentual_horas_mo: float  # Activity MO hours ÷ Total MO hours
    
    elif estrategia == "duracao":
        # Calculated from activity duration
        semanas_atividade: int
        semanas_projeto: int
        percentual_duracao: float = semanas_atividade / semanas_projeto
    
    elif estrategia == "fator_explicito":
        # Manually assigned
        fator_top: float      # % of TOP pool consumed
        fator_adm: float      # % of ADM pool consumed
        fator_lab: float      # % of LAB pool consumed
        fator_qsms: float     # % of QSMS pool consumed
        
        # Validation
        assert fator_top + fator_adm + fator_lab + fator_qsms <= 1.0, \
            "Total factors cannot exceed 100%"

class CustoIndiretoAtividade(BaseModel):
    """Calculated indirect cost share for an activity."""
    
    atividade_id: str
    alocacao: IndiretoAlocacao
    
    # Calculated shares (from pools in ADR-009)
    custo_top_atribuido: float     # % of total TOP cost
    custo_adm_atribuido: float     # % of total ADM cost
    custo_lab_atribuido: float     # % of total LAB cost
    custo_qsms_atribuido: float    # % of total QSMS cost
    
    custo_total_indireto: float = (
        custo_top_atribuido +
        custo_adm_atribuido +
        custo_lab_atribuido +
        custo_qsms_atribuido
    )
```

---

### D3 — Activity-Specific Mobilization (Optional)

Some activities may require **setup/teardown** that is one-time within the activity, not the entire project.

Examples:
- **Fundações activity**: Setup (mobilize equipment, site prep) + Teardown (cleanup)
- **Estrutura activity**: Setup (crane mobilization) + Teardown (crane removal)

```python
class MobilizacaoAtividade(BaseModel):
    """One-time setup/teardown cost specific to an activity."""
    
    atividade_id: str
    fase: Literal["setup", "teardown", "both"]
    
    # Components (same universal structure)
    mao_de_obra: Optional[InsumoComponent]
    equipamentos: Optional[InsumoComponent]
    material: Optional[InsumoComponent]
    
    custo_total: float = (
        (mao_de_obra.custo_fixo_base or 0) +
        (equipamentos.custo_fixo_base or 0) +
        (material.custo_fixo_base or 0)
    )
    
    # Allocation
    alocacao: Literal["semana_inicio", "semana_fim", "ambas"]
    
    def alocacao_por_semana(self, semana_inicio: int, semana_fim: int) -> dict[int, float]:
        if self.alocacao == "semana_inicio":
            return {semana_inicio: self.custo_total}
        elif self.alocacao == "semana_fim":
            return {semana_fim: self.custo_total}
        else:  # ambas
            return {
                semana_inicio: self.custo_total / 2,
                semana_fim: self.custo_total / 2,
            }
```

---

### D4 — Complete Activity Cost Breakdown

```python
class AtividadeCustoCompleto(BaseModel):
    """Full cost breakdown for an activity."""
    
    atividade_id: str
    nome: str  # e.g., "Escavação e Preparo do Solo"
    
    # Schedule (from ADR-003)
    semana_inicio: int
    semana_fim: int
    duracao_semanas: int = semana_fim - semana_inicio + 1
    
    # DIRECT COSTS
    custos_diretos: list[AtividadeInsumo]
    
    custo_direto_total: float = sum(insumo.custo_total_direto for insumo in custos_diretos)
    
    custo_direto_por_componente: dict[str, float] = {
        "mao_de_obra": sum(insumo.componentes_breakdown()["mao_de_obra"] for insumo in custos_diretos),
        "equipamentos": sum(insumo.componentes_breakdown()["equipamentos"] for insumo in custos_diretos),
        "material": sum(insumo.componentes_breakdown()["material"] for insumo in custos_diretos),
    }
    
    # INDIRECT COSTS (from pools)
    indireto_alocacao: IndiretoAlocacao
    custo_indireto_atribuido: float  # Calculated based on strategy
    
    # ACTIVITY-SPECIFIC MOBILIZATION (optional)
    mobilizacao: Optional[MobilizacaoAtividade] = None
    custo_mobilizacao_atividade: float = mobilizacao.custo_total if mobilizacao else 0
    
    # TOTALS
    custo_total_atividade: float = (
        custo_direto_total +
        custo_indireto_atribuido +
        custo_mobilizacao_atividade
    )
    
    # BREAKDOWN
    def resumo_custos(self) -> dict:
        return {
            "direto": {
                "mao_de_obra": self.custo_direto_por_componente["mao_de_obra"],
                "equipamentos": self.custo_direto_por_componente["equipamentos"],
                "material": self.custo_direto_por_componente["material"],
                "total": self.custo_direto_total,
            },
            "indireto": self.custo_indireto_atribuido,
            "mobilizacao_atividade": self.custo_mobilizacao_atividade,
            "total": self.custo_total_atividade,
        }
```

---

### D5 — Weekly Cost Allocation Per Activity

Each activity's costs are **pro-rated across its active weeks**:

```python
class AtividadeCustoSemanal(BaseModel):
    """Weekly cost breakdown for an activity."""
    
    atividade_id: str
    semana: int
    
    # Direct costs pro-rated (distributed evenly across activity duration)
    custo_direto_semanal: float = (
        custo_direto_total ÷ duracao_semanas
    )
    
    # Indirect costs pro-rated (same as direct)
    custo_indireto_semanal: float = (
        custo_indireto_atribuido ÷ duracao_semanas
    )
    
    # Mobilization (one-time, specific weeks)
    custo_mobilizacao_semanal: float  # 0 unless mobilizacao applies this week
    
    # Weekly total
    custo_total_semanal: float = (
        custo_direto_semanal +
        custo_indireto_semanal +
        custo_mobilizacao_semanal
    )
```

---

### D6 — Project Weekly Cost Aggregation

All activities + indirect project pools combine into **weekly project cost**:

```python
class CustoProjetoSemanal(BaseModel):
    """Complete weekly project cost (activities + project-level indirect)."""
    
    semana: int
    
    # Project-level indirect pools (from ADR-009)
    # Already calculated and distributed to activities, so:
    # We aggregate what activities consume, plus MOB (one-time)
    
    # Aggregate from all activities
    atividades_custo_direto_semanal: float = sum(
        atividade.custo_direto_semanal 
        for atividade in atividades_ativas_semana
    )
    
    atividades_custo_indireto_semanal: float = sum(
        atividade.custo_indireto_semanal 
        for atividade in atividades_ativas_semana
    )
    
    atividades_custo_mobilizacao_semanal: float = sum(
        atividade.custo_mobilizacao_semanal 
        for atividade in atividades_ativas_semana
    )
    
    # Project-level one-time (MOB from ADR-009)
    custo_mob_projeto_semanal: float = (
        indiretos_config["MOB"].alocacao_por_semana()[semana] 
        if semana in [0, final_week] else 0
    )
    
    # TOTALS
    custo_total_semanal: float = (
        atividades_custo_direto_semanal +
        atividades_custo_indireto_semanal +
        atividades_custo_mobilizacao_semanal +
        custo_mob_projeto_semanal
    )
    
    # BREAKDOWN
    def resumo_semanal(self) -> dict:
        return {
            "atividades_direto": atividades_custo_direto_semanal,
            "atividades_indireto": atividades_custo_indireto_semanal,
            "atividades_mobilizacao": atividades_custo_mobilizacao_semanal,
            "projeto_mob": custo_mob_projeto_semanal,
            "total": custo_total_semanal,
        }
```

---

### D7 — Indirect Cost Pool Validation

**Constraint:** All activities' indirect allocations must sum to 100% (or ≤ 100% if shared service overhead exists).

```python
def validar_alocacao_indireto(atividades: list[AtividadeCustoCompleto]) -> bool:
    """Ensure indirect pool allocations don't exceed 100%."""
    
    total_fator_top = sum(a.indireto_alocacao.fator_top for a in atividades)
    total_fator_adm = sum(a.indireto_alocacao.fator_adm for a in atividades)
    total_fator_lab = sum(a.indireto_alocacao.fator_lab for a in atividades)
    total_fator_qsms = sum(a.indireto_alocacao.fator_qsms for a in atividades)
    
    # Each pool should be 100% allocated (or flagged as unallocated)
    assert total_fator_top <= 1.01, f"TOP overallocated: {total_fator_top * 100}%"
    assert total_fator_adm <= 1.01, f"ADM overallocated: {total_fator_adm * 100}%"
    assert total_fator_lab <= 1.01, f"LAB overallocated: {total_fator_lab * 100}%"
    assert total_fator_qsms <= 1.01, f"QSMS overallocated: {total_fator_qsms * 100}%"
    
    # If < 100%, some pool capacity is unused (flag for review)
    if total_fator_top < 0.99:
        warn(f"TOP underallocated: {total_fator_top * 100}%")
    # ... repeat for others
    
    return True
```

---

### D8 — Integration with ADR-003 (Schedule) and ADR-006 (Replanning)

**From ADR-003 (Weekly Schedule):**
- Activity schedule provides: semana_inicio, semana_fim
- When schedule changes, activity duration changes → indirect allocation recalculated

**From ADR-006 (Replanning):**
- If activity is delayed/extended, its cost allocation shifts to different weeks
- If activity is accelerated, duration decreases → costs decrease proportionally
- Indirect pools may need reallocation (if using duracao strategy)

```python
def recalcular_custos_atividade_apos_replan(
    atividade: AtividadeCustoCompleto,
    novo_cronograma: ScheduleChange,
) -> AtividadeCustoCompleto:
    """Recalculate activity costs when schedule changes."""
    
    # Direct costs: stay same (no change to labor/equipment/material budget)
    # (Assumption: activity scope unchanged, only timing)
    
    # Indirect costs: recalculate if using duracao strategy
    if atividade.indireto_alocacao.estrategia == "duracao":
        nova_duracao = novo_cronograma.semana_fim - novo_cronograma.semana_inicio + 1
        novo_percentual = nova_duracao / novo_cronograma.duracao_projeto_semanas
        
        atividade.custo_indireto_atribuido = (
            novo_percentual * total_indireto_pools
        )
    
    # Mobilization: recalculate based on new weeks
    if atividade.mobilizacao:
        atividade.mobilizacao.alocacao_por_semana(
            novo_cronograma.semana_inicio,
            novo_cronograma.semana_fim
        )
    
    return atividade
```

---

## Configuration Template (Activities + Resources)

```yaml
# atividades_custos_v1.0.yml

atividades:
  
  escavacao:
    nome: "Escavação e Preparo do Solo"
    semana_inicio: 0
    semana_fim: 3
    
    custos_diretos:
      escavacao:
        categoria: "Escavação"
        componentes:
          mao_de_obra:
            itens:
              - funcao: "Operador escavadeira"
                quantidade: 2
                salario_semanal: 2500
                total: 5000
              - funcao: "Ajudante"
                quantidade: 4
                salario_semanal: 1200
                total: 4800
            subtotal: 9800
          
          equipamentos:
            itens:
              - equipamento: "Escavadeira 350"
                aluguel_semanal: 3500
                combustivel: 800
                total: 4300
            subtotal: 4300
          
          material:
            descricao: "Materiais de apoio (combustível, ferramentas)"
            valor: 1500
        
        custo_total: 15600
    
    custo_direto_total: 15600
    
    # Indirect allocation
    indireto_alocacao:
      estrategia: "esforco_mo"
      # Or: "duracao" (4 weeks ÷ 24 weeks = 16.7%)
      # Or: "fator_explicito" with manual percentages
    
    # Activity-specific mobilization
    mobilizacao:
      fase: "setup"
      componentes:
        mao_de_obra:
          itens:
            - funcao: "Encarregado mobilização"
              quantidade: 1
              custo: 3000
          subtotal: 3000
        
        equipamentos:
          itens:
            - equipamento: "Escavadeira: transporte e setup"
              custo: 2000
          subtotal: 2000
        
        material:
          descricao: "Materiais setup"
          valor: 1000
      
      custo_total: 6000
      alocacao: "semana_inicio"
  
  fundacoes:
    nome: "Fundações (Sapatas e Vigas)"
    semana_inicio: 4
    semana_fim: 8
    
    custos_diretos:
      # ... (similar structure)
    
    indireto_alocacao:
      estrategia: "duracao"  # 5 weeks ÷ 24 weeks = 20.8%
    
    mobilizacao:
      fase: "both"  # Setup + teardown
      # ...
  
  estrutura:
    nome: "Estrutura (Pilares, Vigas, Lajes)"
    semana_inicio: 9
    semana_fim: 16
    
    custos_diretos:
      # ... (similar structure)
    
    indireto_alocacao:
      estrategia: "fator_explicito"
      fator_top: 0.10     # 10% of TOP (topography minimal during structure)
      fator_adm: 0.25     # 25% of ADM (more admin during main phase)
      fator_lab: 0.30     # 30% of LAB (concrete testing, reinforcement inspection)
      fator_qsms: 0.20    # 20% of QSMS (safety critical phase)
```

---

## Interfaces / Calculations

### Calculate Total Project Cost (ADR-009 + ADR-010)

```python
def calcular_custo_total_projeto(
    indiretos_config: dict,  # From ADR-009
    atividades: list[AtividadeCustoCompleto],  # From ADR-010
    cronograma: WeeklySchedule,  # From ADR-003
) -> dict:
    
    # Validate indirect allocations
    validar_alocacao_indireto(atividades)
    
    # Calculate by week
    custos_por_semana = {}
    
    for week in range(cronograma.duration_weeks):
        atividades_ativas = [
            a for a in atividades
            if a.semana_inicio <= week <= a.semana_fim
        ]
        
        # Aggregate all costs for this week
        custo_semanal = CustoProjetoSemanal(
            semana=week,
            atividades_ativas_semana=atividades_ativas,
        )
        
        custos_por_semana[week] = custo_semanal
    
    # Totals and breakdown
    return {
        "by_week": custos_por_semana,
        "by_activity": {a.atividade_id: a.custo_total_atividade for a in atividades},
        "by_component": {
            "mao_de_obra": sum_all_mo(),
            "equipamentos": sum_all_equip(),
            "material": sum_all_material(),
        },
        "by_cost_type": {
            "direto": sum_all_direct(),
            "indireto": sum_all_indirect(),
            "mobilizacao_projeto": indiretos_config["MOB"]["custo_total"],
            "mobilizacao_atividades": sum_all_activity_mob(),
        },
        "total_projeto": sum(custos_por_semana.values()),
    }
```

---

## Related ADRs / Skills

- **ADR-003** (Weekly Schedule): Provides semana_inicio, semana_fim per activity
- **ADR-006** (Replanning): Triggers recalculation of activity costs on schedule changes
- **ADR-009** (Indirect Costs Pools): Defines TOP, ADM, LAB, QSMS, MOB pools that activities share
- **Skill 02B-cronograma-semanal**: Generates weekly schedule, feeds into activity cost allocation

---

## Definition of Done

- [x] `AtividadeInsumo` model (direct cost components)
- [x] `IndiretoAlocacao` model (three allocation strategies)
- [x] `CustoIndiretoAtividade` model (calculated indirect share)
- [x] `MobilizacaoAtividade` model (activity-specific setup/teardown)
- [x] `AtividadeCustoCompleto` model (full activity cost breakdown)
- [x] Integration with ADR-003 (schedule → activity duration → cost allocation)
- [x] Integration with ADR-006 (replanning → cost recalculation)
- [x] 10+ test cases (test_adr010_activity_costs.py)
- [ ] `AtividadeCustoSemanal` model (weekly pro-ration per activity) — embedded in skill, no standalone model
- [ ] `CustoProjetoSemanal` model (aggregation of all activities + project MOB) — embedded in skill
- [ ] Indirect cost allocation validation (no overallocation)
- [ ] Configuration loader (activities YAML, cost matrix model)
- [ ] CLI: `concilium custos activity <id> --cronograma <version>`

---

## Summary

**Decision:** Each activity has **explicit cost breakdown** combining:

```
CUSTO_ATIVIDADE = DIRETO + INDIRETO_SHARE + MOBILIZACAO_ATIVIDADE

DIRETO:
  = MÃO_DE_OBRA + EQUIPAMENTOS + MATERIAL (activity-specific)

INDIRETO_SHARE:
  = (% of TOP) + (% of ADM) + (% of LAB) + (% of QSMS)
  (allocated via esforco_mo, duracao, or fator_explicito)

MOBILIZACAO_ATIVIDADE:
  = Optional setup/teardown specific to activity
```

**Weekly aggregation:**
```
CUSTO_SEMANA = (all atividades_direto_semanal)
             + (all atividades_indireto_semanal)
             + (all atividades_mobilizacao_semanal)
             + (project MOB if applicable)
```

**Benefits:**
- Activities are unit of cost tracking and management
- Indirect pools are distributed explicitly (visible allocation)
- Activity replanning has transparent cost impact
- Activity-specific mobilization is separate from project MOB
- Weekly cost visibility enables forecasting and variance analysis
- Supports multiple allocation strategies (match project needs)
- Clear decomposition: direct vs. indirect vs. mobilization vs. project-level
