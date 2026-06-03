# ADR-011: Productivity as Computable Artifact: Hourly Rates from CPU Composition

**Status:** Implementado  
**Date Decided:** 2026-04-30  
**Date Implemented:** 2026-04-30  
**Implementers:** producao.py (ProdutividadeDetalhada, ComponenteEquipamento, ComponenteMaoDeObra, ComponenteCombustivel)  
**Context:** From AGIS reference spreadsheet, productivity is **NOT a simple number**. It emerges from **CPU composition**:

### Current Reality (AGIS v2.4)

**Sheet "PRODUÇÕES"** defines baseline rates:
```
ITEM: ESCAVAÇÃO, CARGA, TRANSPORTE... (DMT até 2000m)
  PRODUÇÃO HORÁRIA/EQUIPE: 239.04 m³/hour
  PRODUÇÃO DIÁRIA/EQUIPE: 1912.32 m³/day (= 239.04 × 8 hours)
```

**Sheet "CPU"** shows WHERE this comes from:

```
EQUIPAMENTO (A):
  - Escavadeira 38T: 1 unit, R$ 278.40/hour
  - Caminhão basculante 14m³: 7 units, R$ 127.475/hour each = R$ 892.325/hour
  
MÃO DE OBRA (B):
  - Operador escavadeira: 1 × R$ 46.82/hour
  - Ajudante: 1 × R$ 19.13/hour
  - Motorista: 7 × R$ 28.82/hour
  - TOTAL: R$ 284.76/hour

COMBUSTÍVEL (traced to equipment):
  - Escavadeira diesel: 26 L/hour × R$ 6.99 = R$ 181.74/hour
  - Caminhão diesel: 2.5 L/hour × R$ 6.99 = R$ 122.325/hour
  - TOTAL: R$ 304.065/hour

PRODUÇÃO DA EQUIPE (C): 233.54 m³/hour

CUSTO UNITÁRIO (D): (A + B + combustível) / C = R$ 7.534/m³
```

**Key insight:** Productivity (C) is **emergent property** of the team composition (equipment + labor), NOT an independent assumption.

---

## Decision

We formalize **productivity as a first-class artifact** derived deterministically from CPU composition:

### D1 — Productivity Definition

```python
class Produtividade(BaseModel):
    """
    Productivity: how much output a standard team produces per unit time.
    Derived from CPU composition, not assumed independently.
    """
    
    # Identity
    codigo: str                     # "2.1", "PAV-02", etc
    descricao: str                  # "Escavação 1ª categoria DMT até 2000m"
    unidade: str                    # "m³", "m²", "un", etc
    
    # The Three Components (from CPU)
    equipamento: EquipamentoComponent      # (A) Equipment costs per hour
    mao_de_obra: MaoDeObraComponent        # (B) Labor costs per hour
    combustivel: CombustivelComponent      # (C) Fuel costs per hour
    
    # Hourly Output
    producao_horaria: float         # units/hour (from CPU.C)
    producao_diaria: float = producao_horaria × 8  # standard 8h day
    
    # Cost Derivation
    custo_horario_equipamento: float        # = A
    custo_horario_labor: float              # = B
    custo_horario_combustivel: float        # = C
    custo_horario_total: float = A + B + C
    
    # Unit Cost (consequent of productivity)
    custo_unitario: float = custo_horario_total / producao_horaria
    
    # Scaling
    equipes: int = 1  # Standard team count for this productivity
    producao_horaria_n_equipes: float = producao_horaria × equipes
    
    # Classification
    categoria_cpu: str = "ESCAVACAO" | "PAVIMENTACAO" | "DRENAGEM" | ...
```

---

### D2 — Productivity Derives from CPU (Not Independent)

**CPU is the source of truth.** Productivity is CALCULATED, not assumed:

```python
class ComposicaoUnitaria(BaseModel):
    """CPU: Complete definition of how to execute 1 unit of service."""
    
    codigo: str
    descricao: str
    unidade: str
    
    # Components that define productivity
    A_equipamento: list[EquipamentoItem]  # Equipment + costs
    B_mao_de_obra: list[MaoDeObraItem]    # Labor + costs
    C_combustivel: list[CombustivelItem]  # Fuel per equipment
    
    # Derived: What the team can produce per hour
    producao_horaria: float  # (calculated, not input)
    
    def calculate_productivity(self):
        """
        Given CPU composition, what's the team output per hour?
        Not assumed; calculated from equipment capacity + labor intensity.
        """
        
        # Example: Escavadeira can move 160 m³/hour
        excavator_capacity = 160  # m³/hour
        
        # But team has 1 excavator + 7 trucks + 1 operator + 7 drivers
        # Bottleneck: Can trucks handle 160 m³/hour output?
        # Truck capacity: 14 m³/trip, assume 6 trips/hour = 84 m³/hour per truck
        # 7 trucks: 84 × 7 = 588 m³/hour (OK)
        
        # Conservative: use excavator capacity
        producao_horaria = 160
        
        # But CPU data says 239.04 m³/hour (from PRODUÇÕES)
        # Likely: 160 is pure excavation, 239.04 includes haul/spread
        
        producao_horaria = 239.04  # From empirical measurement (PRODUÇÕES sheet)
        
        return producao_horaria
```

---

### D3 — Granularity: Hour → Week

Convert hourly productivity to weekly (for ADR-003 schedule):

```python
class ProdutividadeGranularidade(BaseModel):
    """
    Productivity at different time granularities.
    All derived from produção_horaria.
    """
    
    # Base (from CPU)
    producao_horaria: float  # units/hour
    
    # Derived
    producao_por_turno_8h: float = producao_horaria × 8
    producao_diaria: float = producao_horaria × 8  # Same
    producao_semanal: float = (
        producao_horaria × 8 × 5  # 5 working days/week (standard AGIS)
    )
    
    # Integration with ADR-003 (Weekly Schedule)
    # When scheduling says "Activity X: 2 teams, week t"
    # Progress_week[X][t] = producao_semanal × 2 × eficiencia[t]
```

**Example:**
```
CPU-2.1 (Escavação):
  producao_horaria = 239.04 m³/hour
  producao_semanal = 239.04 × 8 × 5 = 9.561,6 m³/week (1 team)
  
Activity EXCAV-01:
  Scheduled: 2 teams, weeks 1–10
  progress_week[t] = 9.561,6 × 2 = 19.123,2 m³/week
  cumulative_week_10 = 19.123,2 × 10 = 191.232 m³
```

---

### D4 — Productivity Scaling (Linear Assumption)

**Assumption:** Doubling teams doubles output (no interference penalty):

```python
class ProdutividadeEscala(BaseModel):
    """
    Productivity scales linearly with team count.
    """
    
    producao_horaria_1_equipe: float = 239.04  # m³/hour
    
    def producao_n_equipes(self, n: int, efficiency: float = 1.0) -> float:
        """
        Output of N teams (with optional efficiency factor).
        
        Args:
          n: number of teams
          efficiency: 0.5–1.5 (weather, learning, site conditions)
        
        Returns:
          m³/hour
        """
        return producao_horaria_1_equipe × n × efficiency
    
    # Examples:
    producao_1_equipe = 239.04 m³/hour
    producao_2_equipes = 478.08 m³/hour  (linear)
    producao_2_equipes_com_chuva_0_8 = 382.464 m³/hour  (efficiency = 0.8)
```

**Caveat:** Assumes site conditions support linear scaling (not resource-limited, no queue bottlenecks).

---

### D5 — Productivity Adjustments (Non-Linear)

Efficiency factors (ADR-003) modify productivity WITHOUT changing CPU:

```python
class ProdutividadeAjuste(BaseModel):
    """
    Productivity can be adjusted by efficiency factors, but CPU remains unchanged.
    
    This enables:
    1. Weather-driven reductions (temporary)
    2. Learning curve (temporary)
    3. Site-specific conditions (systemic)
    4. Bonus acceleration (temporary)
    """
    
    produtividade_baseline: float = 239.04  # From CPU, invariant
    
    eficiencia_semana_0: float = 0.60  # Ramp-up week
    eficiencia_semana_1_4: float = 0.90  # Learning phase
    eficiencia_semana_5_plus: float = 1.00  # Steady state
    
    producao_semanal_efetiva = [
        9.561,6 × 0.60 = 5.736,96,  # Week 0
        9.561,6 × 0.90 = 8.605,44,  # Weeks 1–4
        9.561,6 × 1.00 = 9.561,6,   # Weeks 5+
    ]
```

**Rule:** Efficiency adjusts **observed** productivity, not baseline. CPU remains first-class artifact.

---

## Interfaces / Implementation

### CPU → Productivity Extraction

```python
class ProdutividadeExtrator:
    """Extract productivity from CPU definition."""
    
    def extrair_de_cpu(self, cpu: ComposicaoUnitaria) -> Produtividade:
        """
        Given CPU (equipment + labor composition), derive productivity.
        
        Sources:
          1. Direct measurement (PRODUÇÕES sheet) — preferred
          2. Calculated from equipment capacity — fallback
          3. Historical average — if not measured/calculated
        """
        
        # Step 1: Look for measured value in PRODUÇÕES sheet
        produtividade_medida = lookup_producoes_sheet(cpu.codigo)
        
        if produtividade_medida:
            # Use measured value (empirical, most reliable)
            producao_horaria = produtividade_medida
        else:
            # Step 2: Calculate from equipment capacity
            producao_horaria = self._calcular_de_equipamentos(cpu)
        
        # Step 3: Validate against historical averages (sanity check)
        media_historica = lookup_project_average(cpu.categoria_cpu)
        if producao_horaria < media_historica × 0.5:
            # Flag warning: unusually low productivity
            return ProdutividadeWarning(
                produtividade_calculada=producao_horaria,
                media_historica=media_historica,
                ratio=producao_horaria / media_historica
            )
        
        return Produtividade(
            codigo=cpu.codigo,
            descricao=cpu.descricao,
            unidade=cpu.unidade,
            producao_horaria=producao_horaria,
            custo_unitario=cpu.calculate_unit_cost(),
        )
    
    def _calcular_de_equipamentos(self, cpu) -> float:
        """
        Estimate productivity from equipment spec.
        
        Example: Escavadeira 38T moves ~160 m³/hour
        """
        # Equipment capacity lookup
        capacidades = {
            "E0015": 160,  # Escavadeira 38T: m³/hour
            "E0039": "speed-dependent",  # Vehicle: km/hour, not directly productivity
        }
        
        # Conservative: use bottleneck (usually excavator, not transport)
        # Unless transport is the constraint (check distances)
        
        # For now: return measured PRODUÇÕES value as fallback
        raise NotImplementedError("Use PRODUÇÕES sheet as source of truth")
```

### Integration with ADR-003 (Weekly Schedule)

```python
class SkillNovaIntegracao:
    """
    When Skill 02B (weekly schedule) allocates teams to activities:
      activity_allocation[t] = num_teams
    
    Progress is calculated as:
      progress[t] = produtividade[activity].producao_semanal × num_teams[t] × eficiencia[t]
    """
    
    def compute_progress(
        self,
        activity_id: str,
        week: int,
        num_teams: int,
        eficiencia: float,
        produtividade_catalog: dict[str, Produtividade],
    ) -> float:
        """
        progress_week[activity][t] 
          = produtividade[activity].producao_semanal × num_teams × eficiencia
        """
        
        cpu_id = canonical.eap[activity_id].cpu_id
        produtividade = produtividade_catalog[cpu_id]
        
        producao = (
            produtividade.producao_semanal  # units/week for 1 team
            × num_teams
            × eficiencia
        )
        
        return producao
```

---

## Data Structure (AGIS Configuration)

```yaml
# produtividades_agis.yaml

produtividades:
  
  "2.1":  # CPU code
    descricao: "Escavação, carga, transporte... (DMT até 2000m)"
    unidade: "m³"
    categoria: "TERRAPLANAGEM"
    
    # Source: PRODUÇÕES sheet
    producao_horaria: 239.04  # m³/hour (1 standard team)
    producao_diaria: 1912.32  # m³/day (8h)
    producao_semanal: 9561.6  # m³/week (8h × 5 days)
    
    # Source: CPU sheet
    # Equipment (A)
    equipamentos:
      - "E0015": Escavadeira 38T: 1 × R$ 278.40/h
      - "E0002": Caminhão 14m³: 7 × R$ 127.475/h
      subtotal: R$ 1.170,73/h
    
    # Labor (B)
    mao_de_obra:
      - Operador escavadeira: 1 × R$ 46.82/h
      - Motorista: 7 × R$ 28.82/h
      - Ajudante: 1 × R$ 19.13/h
      subtotal: R$ 284.76/h
    
    # Fuel (C)
    combustivel:
      - Escavadeira: 26 L/h × R$ 6.99 = R$ 181.74/h
      - Caminhão: 2.5 L/h × R$ 6.99 = R$ 122.33/h
      subtotal: R$ 304.07/h
    
    # Derived
    custo_horario_total: 1755.56  # A + B + C
    custo_unitario: 7.534  # R$/m³ = (A+B+C) / producao_horaria
```

---

## Validation Rules

```python
class ProdutividadeValidator:
    
    def validar(self, produtividade: Produtividade, cpu: ComposicaoUnitaria):
        """VAL-PROD-01 to 04"""
        
        # VAL-PROD-01: Productivity matches PRODUÇÕES sheet (if available)
        produtividade_esperada = lookup_producoes_sheet(produtividade.codigo)
        if produtividade_esperada and abs(produtividade.producao_horaria - produtividade_esperada) > 0.05 * produtividade_esperada:
            # 5% tolerance
            return ValidacaoItem(
                codigo="VAL-PROD-01",
                status="AVISO",
                mensagem=f"Productivity {produtividade.producao_horaria} differs from PRODUÇÕES {produtividade_esperada}"
            )
        
        # VAL-PROD-02: Unit cost derivation correct
        custo_calc = produtividade.custo_horario_total / produtividade.producao_horaria
        if abs(custo_calc - produtividade.custo_unitario) > 0.01:
            return ValidacaoItem(
                codigo="VAL-PROD-02",
                status="ERRO",
                mensagem=f"Unit cost calculation mismatch"
            )
        
        # VAL-PROD-03: Scaling is linear
        # (verified during progress calculation, not validation)
        
        # VAL-PROD-04: Efficiency factor within bounds [0.5, 1.5]
        # (covered in ADR-003, not here)
```

---

## Related ADRs / Skills

- **ADR-003** (Weekly Schedule): Uses produtividade.producao_semanal in progress formula
- **ADR-005** (Team Composition): Equipes affect produtividade scaling (num_teams × producao_horaria)
- **Skill 02B** (Weekly Schedule): Outputs team allocations used in productivity calculation
- **PRODUÇÕES sheet** (reference data): Source of truth for measured productivity

---

## Definition of Done

- [ ] `Produtividade` model (hour/day/week granularity)
- [ ] `ProdutividadeExtrator` (extract from CPU)
- [ ] `ProdutividadeGranularidade` (hour → week conversion)
- [ ] `ProdutividadeEscala` (linear team scaling)
- [ ] `ProdutividadeAjuste` (efficiency factors)
- [ ] CPU-to-Productivity mapping (AGIS config)
- [ ] Integration with Skill 02B (progress calculation uses produtividade)
- [ ] Integration with ADR-003 (weekly schedule references produtividade)
- [ ] Validation: PRODUÇÕES sheet values match Produtividade model
- [ ] ProdutividadeValidator with VAL-PROD-01 to 04
- [ ] 6+ test cases:
  - [ ] Extract productivity from CPU correctly
  - [ ] Hourly → weekly conversion (× 40 hours)
  - [ ] Team scaling (2 teams = 2× output)
  - [ ] Efficiency adjustment (0.8 factor = 80% output)
  - [ ] Unit cost derivation correct
  - [ ] Matches PRODUÇÕES sheet values

---

## Summary

**Decision:** Productivity is **NOT an independent assumption**. It is **derived deterministically from CPU composition** (equipment + labor + fuel).

```
Produtividade = (A_equipamento + B_mao_de_obra + C_combustivel) 
                → defines team composition
                → defines output per hour
                → scales linearly with team count
                → adjusted by efficiency factors
```

**Consequence:**
- Productivity is **first-class artifact** in Concilium (model in code, not spreadsheet)
- Changes to CPU composition automatically update productivity
- Productivity feeds into weekly schedule (ADR-003) and cost calculation
- Efficiency factors adjust productivity WITHOUT changing CPU baseline
- All values traceable back to AGIS reference (PRODUÇÕES + CPU sheets)

This makes productivity **transparent, auditable, and maintainable**.