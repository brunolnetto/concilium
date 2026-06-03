# ADR-009: Indirect Costs: Cost Matrix Model (Scaling × Components)

**Status:** IMPLEMENTED  
**Date Decided:** 2026-04-30  
**Date Implemented:** 2026-04-30  
**Implementers:** canonical.py (IndirectoCategoria, IndiretoSemanal), skills/05-indiretos  
**Context:** From AGIS reference spreadsheet analysis, **insumos** (inputs: labor, equipment, materials) are **not primarily differentiated by category name**, but by:

1. **Who consumes them:** Direct (activity-tied) vs. Indirect (shared across activities)
2. **How they scale:** Permanência-based (project duration) vs. One-time (fixed)

Each insumo type can be decomposed into:
- **MÃO_DE_OBRA** (labor)
- **EQUIPAMENTOS** (equipment/assets)
- **MATERIAL** (consumables, supplies, infrastructure)

### Insumo Classification Matrix

```
                    PERMANÊNCIA-BASED          ONE-TIME ONLY
                    (scales with project)      (fixed, non-recurring)
───────────────────────────────────────────────────────────────
INDIRECT
(shared across     TOP (topografia)            MOB (mobilização/
 activities)       ADM (administração)         demobilização)
                   LAB (laboratório)
                   QSMS (qualidade/segurança)

DIRECT
(activity-tied)    Cost per activity           Setup/teardown per
                   × permanência fa### The Five Indirect Categories (AGIS### The Five Indirect Categories (AGIS v2.4 — Monthly)

**Permanência-Based (recurring, scales with project duration):**

| Category | MÃO DE OBRA | EQUIPAMENTOS | MATERIAL | Calculation |
|----------|---|---|---|---|
| **TOP** | Topógrafos (3), Auxiliares (3), Sala técnica = R$ 94.433,76 | Veículos leves (3), combustível = R$ 22.384 | Custos diversos = R$ 3.000 | CUSTO_TOTAL = CUSTO_FIXO_MENSAL × (SEMANAS ÷ 4.33) |
| **ADM** | Administrativo, Gerente, Engenheiro, etc. = R$ 474.667,38 | Veículos, equipamentos = R$ 280.658,57 | Gastos administrativos = R$ 464.142,29 | CUSTO_TOTAL = CUSTO_FIXO_MENSAL × (SEMANAS ÷ 4.33) |
| **LAB** | Laboratorista (3), Auxiliares (5) = R$ 68.634,60 | Equipamentos de teste = R$ 14.922,67 | — | CUSTO_TOTAL = CUSTO_FIXO_MENSAL × (SEMANAS ÷ 4.33) |
| **QSMS** | Técnico Segurança (4), Gerente QSMS (1) = R$ 54.750 | Veículos, EPI = R$ 14.922,67 | Custos diversos = R$ 8.220 | CUSTO_TOTAL = CUSTO_FIXO_MENSAL × (SEMANAS ÷ 4.33) |

**One-Time Fixed (no permanência scaling):**

| Category | MÃO DE OBRA | EQUIPAMENTOS | MATERIAL | Allocation |
|----------|---|---|---|---|
| **MOB** | Operários, Motoristas = R$ 310.080 | Contêineres, banheiro, gerador = R$ 151.980 | Infraestrutura temporária = R$ 5.803.124 | CUSTO_TOTAL = CUSTO_FIXO (split: week 0 + final week) |

**Key insight:** MOB is NOT an anomaly—it's a distinct **indirect one-time cost**, not a permanência-scaled category.

---

## Decision

We formalize **detailed indirect cost model** refactored to **weekly granularity**:

### D1 — Three-Component Structure (Preserved)

```python
class IndirectoCostComponent(BaseModel):
    """Represents MÃO_DE_OBRA, EQUIPAMENTOS, or VERBAS."""
    
    nome: str                    # "MÃO DE OBRA", "EQUIPAMENTOS", "VERBAS"
    custo_fixo_mensal: float    # R$/month
    
    # Breakdown per item (for transparency)
    itens: list[dict]  # [
                       #   {"funcao": "Topógrafo", "qt": 3, "salario": 18000, ...},
                       #   {"equipamento": "Veiculo leve", "aluguel": 4000, ...},
                       # ]

class IndirectoCategoria(BaseModel):
    """Complete indirect cost category (TOP, ADM, LAB, QSMS, MOB)."""
    
    categoria: Literal["TOP", "ADM", "LAB", "QSMS", "MOB"]
    
    # Components
    mao_de_obra: Optional[IndirectoCostComponent]
    equipamentos: Optional[IndirectoCostComponent]
    verbas: Optional[IndirectoCostComponent]
    
    # Aggregate (for convenience)
    custo_fixo_mensal: float = (
        (mao_de_obra.custo_fixo_mensal or 0) +
        (equipamentos.custo_fixo_mensal or 0) +
        (verbas.custo_fixo_mensal or 0)
    )
    
    # Scaling rule
    driver: Literal["permanencia", "one_time"]
    
    if driver == "permanencia":
        permanencia_meses: float  # Derived from schedule
        custo_total: float = custo_fixo_mensal × permanencia_meses
    else:
        custo_total: float = custo_fixo_mensal  # MOB: fixed, not scaled
```

---

### D2 — Weekly Granularity Conversion

Refactor monthly model to weekly (like ADR-003 for schedule):

```python
class IndirectoSemanal(BaseModel):
    """Weekly breakdown of indirect costs."""
    
    categoria: str
    semana: int  # 0, 1, 2, ..., n
    
    # Components pro-rated to week
    mao_de_obra_semanal: float = (
        mao_de_obra.custo_fixo_mensal / 4.33
    )
    
    equipamentos_semanal: float = (
        equipamentos.custo_fixo_mensal / 4.33
    )
    
    verbas_semanal: float = (
        verbas.custo_fixo_mensal / 4.33
    )
    
    # Total for this week (only if categoria is active this week)
    custo_semanal: float = (
        mao_de_obra_semanal +
        equipamentos_semanal +
        verbas_semanal
    )
    
    # Is this week "active" (does the category operate in this week)?
    ativa: bool  # TOP works from week X to Y, not full project
```

**Conversion factor:** 1 month = 4.33 weeks (average: 52 weeks ÷ 12 months)

---

### D3 — Category-Specific Activation Rules

**NOT all categories active all weeks.**

```python
class IndirectoAtivacao(BaseModel):
    """When is each indirect category active?"""
    
    # TOP: Runs throughout project (surveys needed continuously)
    TOP:
        semana_inicio: 0
        semana_fim: deadline_week
        ativa_toda_duracao: True
    
    # ADM: Runs from start to end (administration continuous)
    ADM:
        semana_inicio: 0
        semana_fim: deadline_week
        ativa_toda_duracao: True
    
    # LAB: Runs throughout (testing as activities complete)
    LAB:
        semana_inicio: 0
        semana_fim: deadline_week
        ativa_toda_duracao: True
    
    # QSMS: Runs throughout (safety/compliance continuous)
    QSMS:
        semana_inicio: 0
        semana_fim: deadline_week
        ativa_toda_duracao: True
    
    # MOB: Only weeks 0 and final (mobilization/demobilization)
    MOB:
        semana_inicio: 0  # Mobilization week 0
        semana_fim: 0
        semana_desmob: deadline_week  # Demobilization final week
        ativa_toda_duracao: False
```

---

### D4 — Cost Calculation by Category (Weekly)

#### TOP (Topografia)

```
CUSTO_FIXO_MENSAL_TOP = R$ 119.817,76

Componentes:
  MÃO_DE_OBRA: R$ 94.433,76
    - Topógrafo (3): 3 × R$ 18.000 = R$ 54.000
    - Auxiliar topografia (3): 3 × R$ 2.217,60 + extras + encargos = R$ 20.587,92
    - Sala técnica (1): 1 × R$ 12.000 = R$ 12.000
    - Alimentação: R$ 7.845,84
    - Total MO: R$ 94.433,76
  
  EQUIPAMENTOS: R$ 22.384
    - Veículo leve (3): 3 × R$ 4.000 (aluguel) + combustível (3.461,33) = R$ 22.384
  
  VERBAS: R$ 3.000
    - Custos diversos

CUSTO_SEMANAL_TOP = R$ 119.817,76 ÷ 4.33 = R$ 27.665,65/semana

Para cronograma de 24 semanas:
  CUSTO_TOTAL_TOP = R$ 27.665,65 × 24 = R$ 663.975,60
```

#### ADM (Administração)

```
CUSTO_FIXO_MENSAL_ADM = R$ 1.219.468,24

Componentes:
  MÃO_DE_OBRA: R$ 474.667,38
    - Administrativo (1): R$ 11.950
    - Auxiliares administrativos (3): 3 × R$ 9.173,14 = R$ 27.519,42
    - Almoxarife (1): R$ 8.144,96
    - Auxiliar almoxarife (1): R$ 6.412,92
    - Gerente contrato (1): R$ 31.950
    - Técnico planejamento (1): R$ 15.950
    - Encarregados gerais (2): 2 × R$ 19.950 = R$ 39.900
    - Engenheiro civil (1): R$ 23.950
    - Mecânicos (2): R$ 16.905
    - Auxiliares mecânicos (2): R$ 6.877,92
    - Borracheiros (2): R$ 8.609,96
    - Etc.
    - Total: R$ 474.667,38
  
  EQUIPAMENTOS: R$ 280.658,57
    - Vários tipos de veículos e equipamentos
  
  VERBAS: R$ 464.142,29
    - Gastos administrativos gerais

CUSTO_SEMANAL_ADM = R$ 1.219.468,24 ÷ 4.33 = R$ 281.431,72/semana

Para cronograma de 24 semanas:
  CUSTO_TOTAL_ADM = R$ 281.431,72 × 24 = R$ 6.754.361,28
```

#### LAB (Laboratório)

```
CUSTO_FIXO_MENSAL_LAB = R$ 83.557,27

Componentes:
  MÃO_DE_OBRA: R$ 68.634,60
    - Laboratorista (3): 3 × R$ 11.415 = R$ 34.245
    - Auxiliar laboratório (5): 5 × R$ 6.877,92 = R$ 34.389,60
  
  EQUIPAMENTOS: R$ 14.922,67
  
  VERBAS: R$ 0

CUSTO_SEMANAL_LAB = R$ 83.557,27 ÷ 4.33 = R$ 19.293,05/semana
```

#### QSMS (Qualidade, Segurança, Meio Ambiente, Saúde)

```
CUSTO_FIXO_MENSAL_QSMS = R$ 77.892,67

Componentes:
  MÃO_DE_OBRA: R$ 54.750
    - Técnico segurança (4): 4 × R$ 9.450 = R$ 37.800
    - Gerente QSMS (1): R$ 16.950
  
  EQUIPAMENTOS: R$ 14.922,67
    - Veículo leve, EPI
  
  VERBAS: R$ 8.220

CUSTO_SEMANAL_QSMS = R$ 77.892,67 ÷ 4.33 = R$ 17.986,96/semana
```

#### MOB (Mobilização) — SPECIAL CASE

```
MOB é NÃO-ESCALÁVEL (one-time, not permanência-based)

CUSTO_FIXO_MOB = R$ 6.265.184,86  (sum of all mobilization items)

Componentes:
  EQUIPAMENTOS: R$ 151.980
    - Mob conteiner (9 viaturas): R$ 8.550
    - Desmob conteiner (9 viaturas): R$ 8.550
    - Mob banheiro químico (4): R$ 2.400
    - Desmob banheiro químico (4): R$ 2.400
    - Gerador mob/desmob: R$ 2.640 + R$ 2.640
    - Etc.
  
  MÃO_DE_OBRA: R$ 310.080
    - Transporte: Operários, motoristas (month-long operations)
  
  VERBAS: R$ 5.803.124,86
    - Site office, temporary infrastructure, etc.

CUSTO_TOTAL_MOB = R$ 6.265.184,86 (FIXED, NOT SCALED)

Alocação semanal (for tracking):
  - Week 0: R$ 6.265.184,86 ÷ 2 = R$ 3.132.592,43 (mobilization)
  - Weeks 1–23: R$ 0
  - Week 24: R$ 3.132.592,43 (demobilization)
  
  OR (if preferred): Spread over first month
  - Weeks 0–4: R$ 6.265.184,86 ÷ 4.33 ÷ 4 = R$ 361.642,54/semana
```

---

### D5 — Integration with Weekly Schedule (ADR-003)

When Skill 02B generates weekly schedule, indiretos recalculate:

```python
def calculate_indiretos_semanal(
    cronograma_semanal: WeeklySchedule,
    indiretos_config: dict,  # Loaded from AGIS profile
) -> dict[int, float]:  # week → cost
    
    permanencia_meses = cronograma_semanal.duration_weeks / 4.33
    
    indiretos_semanal = {}
    
    for week in range(cronograma_semanal.duration_weeks):
        
        custo_semana = 0
        
        # TOP: active every week
        custo_semana += indiretos_config["TOP"]["custo_fixo_mensal"] / 4.33
        
        # ADM: active every week
        custo_semana += indiretos_config["ADM"]["custo_fixo_mensal"] / 4.33
        
        # LAB: active every week
        custo_semana += indiretos_config["LAB"]["custo_fixo_mensal"] / 4.33
        
        # QSMS: active every week
        custo_semana += indiretos_config["QSMS"]["custo_fixo_mensal"] / 4.33
        
        # MOB: only week 0 (mobilization) + final week (demobilization)
        if week == 0 or week == cronograma_semanal.duration_weeks - 1:
            custo_semana += indiretos_config["MOB"]["custo_fixo"] / 2
        
        indiretos_semanal[week] = custo_semana
    
    # Total for project
    custo_total = sum(indiretos_semanal.values())
    
    # Breakdown
    return {
        "by_week": indiretos_semanal,
        "by_category": {
            "TOP": (indiretos_config["TOP"]["custo_fixo_mensal"] / 4.33) × duration_weeks,
            "ADM": (indiretos_config["ADM"]["custo_fixo_mensal"] / 4.33) × duration_weeks,
            "LAB": (indiretos_config["LAB"]["custo_fixo_mensal"] / 4.33) × duration_weeks,
            "QSMS": (indiretos_config["QSMS"]["custo_fixo_mensal"] / 4.33) × duration_weeks,
            "MOB": indiretos_config["MOB"]["custo_fixo"],
        },
        "total": custo_total,
    }
```

---

### D6 — Impact of Replanning on Indiretos

When ADR-006 replanning changes schedule:

```python
# Original schedule: 24 weeks
permanencia_original = 24 / 4.33 = 5.54 months

custo_top_original = R$ 119.817,76 × 5.54 = R$ 664.173,22
custo_adm_original = R$ 1.219.468,24 × 5.54 = R$ 6.754.857,68
# ... (all permanência-scaled categories)

# Replan option 1: Extend to 26 weeks
permanencia_new = 26 / 4.33 = 6.00 months

custo_top_new = R$ 119.817,76 × 6.00 = R$ 718.906,56
custo_adm_new = R$ 1.219.468,24 × 6.00 = R$ 7.316.809,44

delta_top = 718.906,56 - 664.173,22 = +R$ 54.733,34
delta_adm = 7.316.809,44 - 6.754.857,68 = +R$ 561.951,76
delta_total_permanencia = +R$ 616.685,10

MOB unchanged (still R$ 6.265.184,86)

Total indiretos delta: +R$ 616.685,10
```

---

## Interfaces / Implementation

### Configuration Template (AGIS Profile)

```yaml
# indiretos_agis_v2.5.yml

indiretos:
  
  TOP:
    categoria: "topografia"
    driver: "permanencia"
    custo_fixo_mensal: 119817.76
    componentes:
      mao_de_obra:
        itens:
          - funcao: "Topógrafo PJ"
            quantidade: 3
            salario_base: 18000
            alimentacao: 1950
            total: 59950
          - funcao: "Auxiliar topografia"
            quantidade: 3
            salario_base: 2217.60
            horas_extras: 554.40
            alimentacao: 2415
            encargos: 1690.92
            total: 20587.92
          - funcao: "Sala técnica PJ"
            quantidade: 1
            salario_base: 12000
            alimentacao: 1950
            total: 13950
        subtotal: 94433.76
      
      equipamentos:
        itens:
          - equipamento: "Veículo leve"
            quantidade: 3
            aluguel_mensal: 4000
            km_mes: 4800
            consumo_l_km: 9
            custo_combustivel: 3461.33
            total: 22384
        subtotal: 22384
      
      verbas:
        descricao: "Custos diversos topografia"
        valor: 3000
    
    total_mensal: 119817.76
  
  ADM:
    categoria: "administracao"
    driver: "permanencia"
    custo_fixo_mensal: 1219468.24
    componentes:
      mao_de_obra:
        subtotal: 474667.38
      equipamentos:
        subtotal: 280658.57
      verbas:
        subtotal: 464142.29
    
    total_mensal: 1219468.24
  
  LAB:
    categoria: "laboratorio"
    driver: "permanencia"
    custo_fixo_mensal: 83557.27
    # ... detalhes omitidos
  
  QSMS:
    categoria: "qualidade_seguranca"
    driver: "permanencia"
    custo_fixo_mensal: 77892.67
    # ... detalhes omitidos
  
  MOB:
    categoria: "mobilizacao"
    driver: "one_time"
    custo_fixo: 6265184.86
    componentes:
      equipamentos: 151980
      mao_de_obra: 310080
      verbas: 5803124.86
    
    alocacao_semanal: "split_first_last"  # or "spread_first_month"
```

---

## Related ADRs / Skills

- **ADR-003** (Weekly Schedule): Provides duration_weeks → permanência_meses conversion
- **ADR-006** (Replanning): Triggers indiretos recalculation on timeline change
- **Skill 05-indiretos** (existing): Reference implementation for monthly model
- **Skill 02B-cronograma-semanal**: Feeds duration_weeks to indiretos calculation

---

## Definition of Done

- [x] `IndirectoCostComponent` model (MO, EQUIP, VERBAS)
- [x] `IndirectoCategoria` model (TOP, ADM, LAB, QSMS, MOB)
- [x] `IndirectoSemanal` model (weekly breakdown)
- [x] Category-specific calculation functions (TOP/ADM/LAB/QSMS/MOB)
- [x] Weekly pro-ration formula (÷ 4.33)
- [x] MOB special handling (one-time, not permanência-scaled)
- [x] Integration with ADR-003 (cronograma_semanal → permanência_meses)
- [x] Integration with ADR-006 (replan changes → indiretos recalc)
- [x] Configuration loader (AGIS profile YAML)
- [x] 8+ test cases (test_adr009_indirect_costs.py)
- [ ] `IndirectoAtivacao` rules (when each category is active) — partial
- [ ] Validation (total indiretos within budget)
- [ ] CLI: `concilium indiretos calculate --project <id> --cronograma <version>`

---

## Summary

**Decision:** Indirect costs follow **AGIS reference structure** with **three components** (MÃO DE OBRA, EQUIPAMENTOS, VERBAS) scaled by **permanência** (weeks ÷ 4.33 months), except **MOB** which is one-time.

```
CUSTO_TOTAL_CATEGORIA = CUSTO_FIXO_MENSAL × (DURATION_WEEKS ÷ 4.33)

Except:
  MOB = CUSTO_FIXO (one-time, weeks 0 + final)
```

**Weekly granularity enables:**
- Real weekly cost tracking (matches ADR-003 schedule)
- Early cost forecasting (as replan options change permanência)
- Integration with ADR-006 (cost delta in replan decision)
- Transparent breakdown per category

This is the **artefato de primeira classe** (first-class artifact) for indirect costs, mirroring your actual AGIS methodology.
TAL_CATEGORIA = CUSTO_FIXO_MENSAL × (DURATION_WEEKS ÷ 4.33)

Except:
  MOB = CUSTO_FIXO (one-time, weeks 0 + final)
```

**Weekly granularity enables:**
- Real weekly cost tracking (matches ADR-003 schedule)
- Early cost forecasting (as replan options change permanência)
- Integration with ADR-006 (cost delta in replan decision)
- Transparent breakdown per category

This is the **artefato de primeira classe** (first-class artifact) for indirect costs, mirroring your actual AGIS methodology.
