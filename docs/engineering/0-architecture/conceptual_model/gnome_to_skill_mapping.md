# Gnome-to-Skill Mapping

**Document ID:** IMPL-2026-05-12-GNOME-SKILLS  
**Status:** Implementation Guide  
**Author:** Engineering Team  
**Date:** 2026-05-12  

---

## Overview

This document maps the **6-phase Gnome workflow** (black box operations) to the **existing Concilium skills** (02-cronograma, 03-equipes, 05-indiretos, 06-consolidacao, etc.).

Each gnome phase corresponds to one or more skills. Understanding this mapping clarifies:
- Which skills implement which gnome operations
- Which outputs from one phase feed into the next
- Which data structures connect phases
- Where validation happens and error handling occurs

---

## Phase 1: Effort Calculation → Skill 02-cronograma (Stage 1)

### Gnome Operation
**Input:**
- Scope items from `escopo_eap.json` (CPU ID, quantity, unit)
- CPU compositions from master catalog (labor hours, equipment specs)
- Productivity reference data from `produtividade.json` (hours per unit)

**Processing:**
- For each CPU reference in scope: `total_hours = quantity × hours_per_unit`
- Aggregate by activity type (terraplenagem, pavimentação, etc.)
- Validate all CPUs exist and have valid compositions

**Output:**
```json
{
  "esforco_por_atividade": [
    {"cpu_id": "ATI-003", "atividade": "Escavação", "horas_totais": 2025},
    {"cpu_id": "ATI-019", "atividade": "Compactação", "horas_totais": 2240}
  ]
}
```

### Skill Implementation: `02-cronograma`

**Location:** `src/concilium/application/skills/cronograma.py`

**Data Gate Entry Point:**
```python
# In LifecycleCoordinator.avancar_plano()
if force_data_gate:
    assert_catalog_healthy(catalogo_id, catalogo)  # Validates all CPU compositions exist
```

**Phase 1 Code Flow:**
```python
# cronograma.py
def _calculate_effort(scope_items, catalog):
    """Calculate total hours per activity type."""
    effort_map = {}
    for item in scope_items:
        cpu = catalog.get_cpu(item['cpu_id'])
        if not cpu:
            raise CatalogGovernanceError(f"CPU {item['cpu_id']} not found")
        
        hours = item['quantidade'] * cpu['produtividade_horas_por_un']
        effort_map[item['cpu_id']] = {
            'cpu_id': item['cpu_id'],
            'atividade': cpu['tipo_atividade'],
            'horas_totais': hours
        }
    return effort_map
```

**Data Sources:**
- Scope items from `PlanoStore.get_escopo()` → `escopo_meta` field
- CPU composition from `runtime._load_catalogo_from_disk()` (master catalog)
- Productivity multipliers from `produtividade.json` (per-activity override)

**Outputs Stored:**
- `plano_store.skills_log/02-cronograma/esforco_por_atividade.json` (immutable)
- This becomes input to Phase 2 scheduling

**Error Handling:**
| Error | Root Cause | Gnome Response |
|-------|-----------|---|
| `CatalogGovernanceError` | CPU not found in catalog | Fail Phase 1 immediately |
| `InvalidProductivity` | Productivity value ≤ 0 | Fail with validation error |
| `QuantityMismatch` | Scope quantity = 0 | Warn but continue (degenerate case) |

---

## Phase 2: Weekly Distribution → Skill 02-cronograma (Stage 2)

### Gnome Operation
**Input:**
- Effort per activity (from Phase 1)
- Precedence graph from `precedencia.json` (dependencies + lag times)
- Praticabilidade by period (seasonal weather effects)
- Project duration constraint (estimated weeks)

**Processing:**
1. **Topological Sort:** Respect precedence constraints, detect cycles
2. **Critical Path:** Calculate minimum project duration
3. **Activity Scheduling:** Assign each activity to weeks, respecting:
   - Precedence dependencies
   - Lag times (curing, testing, procurement)
   - Praticability constraints (compressed duration in wet season)
4. **Resource Load:** Calculate hours-per-week for each activity

**Output:**
```json
{
  "cronograma_semanal": [
    {
      "semana": 1,
      "atividades": [
        {"cpu_id": "MO-001", "horas": 40, "status": "programada"}
      ]
    },
    {
      "semana": 2,
      "atividades": [
        {"cpu_id": "PREP-015", "horas": 40, "status": "programada"}
      ]
    }
  ],
  "caminho_critico": ["MO-001", "PREP-015", "ATI-003", ...],
  "duracao_projeto_semanas": 52
}
```

### Skill Implementation: `02-cronograma` (Stage 2)

**Location:** `src/concilium/application/skills/cronograma.py` (main scheduling engine)

**Entry Point in LifecycleCoordinator:**
```python
# lifecycle_coordinator.py
def avancar_plano(self, plano_id, habilidade_proxima='02-cronograma', ...):
    # Phase 1 runs first (effort calc)
    run_skill_on_plano('02-cronograma', {'fase': 1, ...})
    
    # Phase 2 runs second (scheduling)
    run_skill_on_plano('02-cronograma', {'fase': 2, 'precedencia': 'LOAD_FROM_CATALOG'})
```

**Phase 2 Code Flow (Pseudo-code):**
```python
def _schedule_by_precedence(effort_map, precedence_graph, praticabilidade_rules):
    """Build week-by-week schedule respecting precedence."""
    
    # 1. Validate precedence graph (no cycles)
    topo_order = topological_sort(precedence_graph)
    
    # 2. Calculate critical path
    critical_path = calculate_critical_path(topo_order, effort_map, lag_times)
    
    # 3. Assign activities to weeks
    schedule = {}
    for semana in range(1, max_project_weeks):
        atividades_semana = []
        for (cpu_id, atividade) in feasible_activities(semana):
            # Check predecessors completed
            if all_predecessors_done(cpu_id, schedule):
                horas = effort_map[cpu_id] / weeks_allocated[cpu_id]
                atividades_semana.append({
                    'cpu_id': cpu_id,
                    'horas': horas * praticabilidade[semana]
                })
        schedule[semana] = atividades_semana
    
    return schedule
```

**Data Sources:**
- Effort output from Phase 1
- Precedence graph from `precedencia.json` (loaded from scope context)
- Praticability by period from `produtividade.json`

**Outputs Stored:**
- `plano_store.skills_log/02-cronograma/cronograma_semanal.json` (immutable)
- Critical path for downstream skills (Phase 3)
- Total project duration (52 weeks for MendesLobo reference)

**Error Handling:**
| Error | Root Cause | Gnome Response |
|-------|-----------|---|
| `CyclicDependency` | Precedence graph has cycle | Fail immediately, report cycle |
| `InfeasibleSchedule` | Cannot fit activities in duration | Warn, extend duration, or suggest parallel execution |
| `InvalidLagTime` | Lag days exceed activity duration | Fail with precedence validation error |

---

## Phase 3: Team Adjustment → Skill 03-equipes

### Gnome Operation
**Input:**
- Weekly schedule from Phase 2 (hours per activity per week)
- Standard team composition from `produtividade.json` (people per activity type)
- Team capacity model (min/max team members, shift arrangements)
- Duration constraints (can team work overtime? split shifts?)

**Processing:**
1. **FTE Calculation:** For each week, sum hours per activity type
2. **Team Sizing:** Convert FTE to headcount per team type
3. **Roster Assignment:** Create week-by-week team roster
4. **Constraint Checking:** Validate min/max team sizes, flag bottlenecks

**Output:**
```json
{
  "equipes_por_semana": [
    {
      "semana": 1,
      "equipes": [
        {
          "tipo_atividade": "Mobilização",
          "composicao": "1 mestre + 2 ajudantes",
          "quantidade_pessoas": 3,
          "fte": 0.75,
          "custo_dia_homem": "R$ 250"
        }
      ],
      "total_pessoas": 3,
      "total_fte": 0.75
    }
  ],
  "utilizacao_media": 0.82,
  "picos_utilizacao": [{"semana": 15, "pessoas": 12, "pico_pct": 1.15}]
}
```

### Skill Implementation: `03-equipes`

**Location:** `src/concilium/application/skills/equipes.py`

**Entry Point in LifecycleCoordinator:**
```python
# After Phase 2 completes
run_skill_on_plano('03-equipes', {
    'cronograma_input': 'FROM_SKILL_02',
    'team_model': 'LOAD_FROM_CATALOG'
})
```

**Phase 3 Code Flow (Pseudo-code):**
```python
def _adjust_team_quantities(cronograma_semanal, team_model_rules):
    """Convert weekly effort into team rosters."""
    
    equipes_por_semana = {}
    for semana, atividades in cronograma_semanal.items():
        equipes_semana = []
        
        # Group activities by type
        por_tipo = group_by_activity_type(atividades)
        
        for tipo_atividade, activities_list in por_tipo.items():
            total_horas = sum(a['horas'] for a in activities_list)
            
            # Convert hours to FTE (40h work week = 1 FTE)
            fte_needed = total_horas / 40
            
            # Get team model for this activity
            team_spec = team_model_rules[tipo_atividade]
            
            # Convert FTE to headcount using team composition
            quantidade_pessoas = ceil(fte_needed / team_spec['pessoas_per_fte'])
            
            equipes_semana.append({
                'tipo_atividade': tipo_atividade,
                'quantidade_pessoas': quantidade_pessoas,
                'fte': fte_needed
            })
        
        equipes_por_semana[semana] = equipes_semana
    
    return equipes_por_semana
```

**Data Sources:**
- Weekly schedule from Phase 2 output
- Team model from `produtividade.json` (`equipe_padrao_por_atividade`)
- Team capacity constraints (if defined in project profile)

**Outputs Stored:**
- `plano_store.skills_log/03-equipes/equipes_por_semana.json` (immutable)
- Team roster for downstream skills (Phase 4, Phase 5)
- Utilization metrics for reporting

**Error Handling:**
| Error | Root Cause | Gnome Response |
|-------|-----------|---|
| `InvalidTeamModel` | Team spec not found for activity | Fail with governance error |
| `ExceededTeamCapacity` | Week requires more people than available | Warn, suggest extending duration |
| `MismatchedActivityType` | Activity type not in team model | Fail with validation error |

---

## Phase 4: Resource Merge + Indirect → Skill 05-indiretos

### Gnome Operation
**Input:**
- Team roster from Phase 3 (people per activity per week)
- CPU compositions (equipment, materials per activity)
- Indirect resource rules (supervision, safety, admin overhead percentages)
- Resource permanency model (which resources persist full project vs. temporary)

**Processing:**
1. **Direct Resource Consolidation:**
   - For each week, list all equipment and materials needed
   - Flag temporal conflicts (same equipment scheduled twice in same week)
   - Merge compatible resources (e.g., combine mason labor across non-conflicting activities)

2. **Indirect Resource Allocation:**
   - Calculate supervision needs (typically 1 supervisor per 8-10 workers)
   - Allocate safety officer (typically 1 per project or per 100K project value)
   - Calculate admin overhead (10-15% of direct labor typically)
   - Allocate resource management and logistics

3. **Permanency Split:**
   - **Permanent:** Site supervisor (present full project duration)
   - **Temporary:** Concrete pump (only weeks 5-10)
   - **Multiplicative:** Labor (scales with activity intensity)

**Output:**
```json
{
  "recursos_consolidados": [
    {
      "semana": 1,
      "tipo": "mao_obra",
      "recursos": [
        {"descricao": "Mobilização", "quantidade": 3, "unidade": "pessoa", "permanencia": "temporaria"}
      ]
    },
    {
      "semana": 2,
      "tipo": "equipamento",
      "recursos": [
        {"descricao": "Canteiro de obras", "quantidade": 1, "unidade": "lote", "permanencia": "permanente"}
      ]
    },
    {
      "semana": 1,
      "tipo": "indireto",
      "recursos": [
        {"descricao": "Supervisor de obra", "quantidade": 1, "unidade": "pessoa", "permanencia": "permanente"}
      ]
    }
  ],
  "resumo_permanencia": {
    "recursos_permanentes": 5,
    "recursos_temporarios": 25,
    "overhead_indireto_pct": 12.5
  }
}
```

### Skill Implementation: `05-indiretos`

**Location:** `src/concilium/application/skills/indiretos.py`

**Entry Point in LifecycleCoordinator:**
```python
# After Phase 3 completes
run_skill_on_plano('05-indiretos', {
    'equipes_input': 'FROM_SKILL_03',
    'atividades_input': 'FROM_SKILL_02',
    'catalogo_recursos': 'LOAD_FROM_MASTER'
})
```

**Phase 4 Code Flow (Pseudo-code):**
```python
def _allocate_resources_and_indirect(equipes_por_semana, cronograma_semanal, catalog, rules):
    """Consolidate direct resources and allocate indirect overhead."""
    
    recursos_consolidados = {}
    
    for semana, equipes in equipes_por_semana.items():
        recursos_semana = {'mao_obra': [], 'equipamento': [], 'indireto': []}
        
        # Direct resources per activity
        for equipe in equipes:
            tipo_atividade = equipe['tipo_atividade']
            quantidade_pessoas = equipe['quantidade_pessoas']
            
            # Load CPU composition (equipment, materials)
            cpu_specs = catalog.get_cpu_equipment(tipo_atividade)
            
            # Add labor
            recursos_semana['mao_obra'].append({
                'descricao': tipo_atividade,
                'quantidade': quantidade_pessoas,
                'permanencia': 'multiplicativa'  # Scales with activity
            })
            
            # Add equipment (check for conflicts)
            for eq in cpu_specs['equipamento']:
                if not has_conflict(eq, recursos_semana['equipamento'], semana):
                    recursos_semana['equipamento'].append(eq)
        
        # Indirect resources (one-time per project)
        if semana == 1:  # Or pro-rata across all weeks
            total_pessoas_semana = sum(e['quantidade_pessoas'] for e in equipes)
            
            # Supervisor: 1 per 8-10 workers
            supervisores = ceil(total_pessoas_semana / 8)
            recursos_semana['indireto'].append({
                'descricao': 'Supervisor de obra',
                'quantidade': supervisores,
                'permanencia': 'permanente'
            })
            
            # Safety officer
            recursos_semana['indireto'].append({
                'descricao': 'Engenheiro de segurança',
                'quantidade': 1,
                'permanencia': 'permanente'
            })
        
        recursos_consolidados[semana] = recursos_semana
    
    return recursos_consolidados
```

**Data Sources:**
- Team roster from Phase 3 output
- Activity schedule from Phase 2 output
- CPU equipment compositions from master catalog
- Indirect resource rules from project profile (`perfil`)

**Outputs Stored:**
- `plano_store.skills_log/05-indiretos/recursos_consolidados.json` (immutable)
- Permanency classification for Phase 5 (cost calculation)
- Equipment conflict resolution for schedule adjustments

**Error Handling:**
| Error | Root Cause | Gnome Response |
|-------|-----------|---|
| `EquipmentConflict` | Same equipment scheduled twice in one week | Flag and escalate to Phase 3 for rescheduling |
| `MissingEquipmentSpec` | CPU composition incomplete | Fail with CatalogGovernanceError |
| `InvalidPermanencyModel` | Permanency type not recognized | Default to 'multiplicative' |

---

## Phase 5: Cost Calculation → Skill 06-consolidacao (Stage 1)

### Gnome Operation
**Input:**
- Consolidated resources from Phase 4 (quantities, types, permanency)
- Pricing cascade:
  - Project-level overrides (config/projetos/<projeto>/overrides.json)
  - Regional pricing (config/jurisdicoes/<jurisdicao>/precos.json)
  - Master catalog pricing (config/referencias/*/precos.json)
- BDI parameters (overhead %, markup %)
- Cost models (cost per person-day, equipment per hour, etc.)

**Processing:**
1. **Resolve Pricing:** For each resource, apply cascata (project → regional → master)
2. **Weekly Costing:** For each week, cost = Σ(resource_qty × unit_price)
3. **Permanency Adjustment:**
   - **Permanent resources:** Amortized over full project duration
   - **Temporary resources:** Charged only to active weeks
   - **Multiplicative:** Charged per activity intensity
4. **Aggregation:**
   - Total Direct Costs = Σ(weekly direct costs)
   - Total Indirect Costs = Σ(weekly indirect costs)
5. **BDI Application:**
   - Total with BDI = (Direct + Indirect) × (1 + BDI_%/100)
6. **Margin & Sale Price:**
   - Profit = Sale Price - (Direct + Indirect)
   - Margin % = Profit / Sale Price

**Output:**
```json
{
  "custos_por_semana": [
    {
      "semana": 1,
      "custo_direto": 8500,
      "custo_indireto": 1200,
      "custo_com_bdi": 10670
    }
  ],
  "resumo_financeiro": {
    "custo_direto_total": 450000,
    "custo_indireto_total": 65000,
    "custo_operacional_total": 515000,
    "custo_com_bdi": 644750,
    "bdi_aplicado_pct": 25,
    "margem_lucro_pct": 15,
    "preco_venda_total": 742262,
    "lucro_bruto": 227262,
    "ponto_equilbrio_por_equipe": 43500
  }
}
```

### Skill Implementation: `06-consolidacao` (Stage 1)

**Location:** `src/concilium/application/skills/consolidacao.py`

**Entry Point in LifecycleCoordinator:**
```python
# After Phase 4 completes
run_skill_on_plano('06-consolidacao', {
    'recursos_input': 'FROM_SKILL_05',
    'pricing_cascata': 'LOAD_FROM_GOVERNANCE',
    'bdi_config': 'LOAD_FROM_PERFIL'
})
```

**Phase 5 Code Flow (Pseudo-code):**
```python
def _calculate_costs(recursos_consolidados, pricing_cascata, bdi_config):
    """Calculate weekly and total costs with BDI."""
    
    custos_por_semana = {}
    total_direto = 0
    total_indireto = 0
    
    for semana, recursos in recursos_consolidados.items():
        custo_direto_sem = 0
        custo_indireto_sem = 0
        
        # Direct costs
        for recurso in recursos['mao_obra'] + recursos['equipamento']:
            preco_unitario = resolve_price(recurso['id'], pricing_cascata)
            custo = recurso['quantidade'] * preco_unitario
            
            if recurso['permanencia'] == 'permanente':
                # Amortize over full project
                custo = custo / total_project_weeks
            
            custo_direto_sem += custo
        
        # Indirect costs
        for recurso in recursos['indireto']:
            preco_unitario = resolve_price(recurso['id'], pricing_cascata)
            custo = recurso['quantidade'] * preco_unitario
            
            if recurso['permanencia'] == 'permanente':
                custo = custo / total_project_weeks
            
            custo_indireto_sem += custo
        
        custo_com_bdi = (custo_direto_sem + custo_indireto_sem) * (1 + bdi_config['bdi_pct']/100)
        
        custos_por_semana[semana] = {
            'custo_direto': custo_direto_sem,
            'custo_indireto': custo_indireto_sem,
            'custo_com_bdi': custo_com_bdi
        }
        
        total_direto += custo_direto_sem
        total_indireto += custo_indireto_sem
    
    # Aggregated financials
    custo_total = total_direto + total_indireto
    custo_com_bdi = custo_total * (1 + bdi_config['bdi_pct']/100)
    margem_pct = bdi_config['margem_lucro_pct']
    preco_venda = custo_com_bdi * (1 + margem_pct/100)
    lucro = preco_venda - custo_total
    
    return {
        'custos_por_semana': custos_por_semana,
        'custo_direto_total': total_direto,
        'custo_indireto_total': total_indireto,
        'custo_com_bdi': custo_com_bdi,
        'preco_venda': preco_venda,
        'lucro_bruto': lucro
    }
```

**Data Sources:**
- Consolidated resources from Phase 4 output
- Pricing cascade via `catalog_governance.validate_and_resolve_*_file()` functions
- BDI configuration from project profile (perfil)
- Project duration from Phase 2 (for permanency amortization)

**Outputs Stored:**
- `plano_store.skills_log/06-consolidacao/custos_por_semana.json` (immutable)
- Aggregated financials (readonly reference for Phase 6)
- Break-even analysis per team

**Error Handling:**
| Error | Root Cause | Gnome Response |
|-------|-----------|---|
| `PriceNotFound` | Resource ID not in pricing cascata | Fail with CatalogGovernanceError |
| `InvalidBDI` | BDI % not in valid range [15, 50] | Fail with validation error |
| `NegativeCost` | Unit price ≤ 0 | Fail with governance error (caught at Phase 4 write) |

---

## Phase 6: Consolidation (Final) → Skill 06-consolidacao (Stage 2)

### Gnome Operation
**Input:**
- Weekly costs from Phase 5
- Effort per activity from Phase 1
- Team composition from Phase 3
- Schedule from Phase 2

**Processing:**
1. **Financial Consolidation:**
   - Summarize direct, indirect, BDI, and margin
   - Calculate profitability metrics (profit %, ROI, break-even)
   - Generate sensitivity analysis (±10% on labor, equipment)

2. **Schedule Consolidation:**
   - Critical path summary (longest dependency chain)
   - Resource utilization histogram (average team size per week)
   - Activity slackness (activities with float vs. critical activities)

3. **Executive Summary:**
   - Total project cost and revenue
   - Key risks (critical path, resource peaks)
   - Phasing and milestones (if applicable)

4. **Deliverables:**
   - Consolidated financial summary (for proposal/contract)
   - Gantt chart (for project control)
   - Resource histogram (for recruitment/planning)
   - Cash flow curve (for financial planning)

**Output:**
```json
{
  "consolidacao_executiva": {
    "projeto_nome": "MendesLobo Trecho 5A",
    "duracao_semanas": 52,
    "data_inicio_prevista": "2026-06-01",
    "data_fim_prevista": "2027-05-31",
    "valor_venda": 742262,
    "lucro_bruto": 227262,
    "margem_lucro_pct": 30.6,
    "roi_pct": 45.2
  },
  "analise_sensibilidade": [
    {"cenario": "+10% labor", "impacto_lucro_pct": -8.5},
    {"cenario": "-10% productivity", "impacto_duracao_semanas": +5}
  ],
  "caminho_critico": ["WBS-1.1", "WBS-1.2", "WBS-2.1", "WBS-2.2", "WBS-3.1", "WBS-4.2", "WBS-5.2", "WBS-6.2"],
  "riscos_identificados": [
    {"risco": "Compactação em período de chuva", "impacto": "Estender WBS-2.2 em +2 semanas", "mitigacao": "Programar para período seco"}
  ],
  "marcos": [
    {"semana": 1, "evento": "Mobilização completa"},
    {"semana": 16, "evento": "Terraplenagem finalizada"},
    {"semana": 52, "evento": "Projeto entregue"}
  ]
}
```

### Skill Implementation: `06-consolidacao` (Stage 2)

**Location:** `src/concilium/application/skills/consolidacao.py` (continuation from Phase 5)

**Entry Point in LifecycleCoordinator:**
```python
# After Phase 5 completes
run_skill_on_plano('06-consolidacao', {
    'phase': 2,
    'custos_input': 'FROM_PHASE_5',
    'esforco_input': 'FROM_SKILL_02',
    'equipes_input': 'FROM_SKILL_03',
    'cronograma_input': 'FROM_SKILL_02'
})
```

**Phase 6 Code Flow (Pseudo-code):**
```python
def _consolidate_final(custos_dict, esforco_dict, equipes_dict, cronograma_dict):
    """Aggregate all phases into executive summary."""
    
    # Financial summary
    total_revenue = sum(c['custo_com_bdi'] for c in custos_dict.values())
    total_cost = sum(c['custo_direto'] + c['custo_indireto'] for c in custos_dict.values())
    lucro = total_revenue - total_cost
    margem_pct = (lucro / total_revenue) * 100 if total_revenue > 0 else 0
    
    # Schedule summary
    duracao_semanas = len(cronograma_dict)
    data_inicio = '2026-06-01'  # From project metadata
    data_fim = add_weeks(data_inicio, duracao_semanas)
    
    # Resource utilization
    max_pessoas = max(sum(e['quantidade_pessoas'] for e in equipes_dict[s]) 
                      for s in equipes_dict)
    avg_pessoas = mean(...)
    
    # Risk analysis
    riscos = [
        {'risco': 'Compactação em período de chuva', 'mitigacao': 'Programar para período seco'},
        {'risco': 'Pico de 12 pessoas na semana 15', 'mitigacao': 'Recrutamento antecipado'}
    ]
    
    return {
        'consolidacao_executiva': {
            'valor_venda': total_revenue,
            'lucro_bruto': lucro,
            'margem_lucro_pct': margem_pct,
            'duracao_semanas': duracao_semanas
        },
        'riscos_identificados': riscos,
        'marcos': extract_milestones(cronograma_dict)
    }
```

**Data Sources:**
- All previous phase outputs (immutable snapshots)
- Project metadata (dates, location, type)
- Historical risk library (if available)

**Outputs Stored:**
- `plano_store.skills_log/06-consolidacao/consolidacao_executiva.json` (immutable, final deliverable)
- Executive dashboard (auto-generated from this summary)
- Artifacts ready for proposal/contract

**Error Handling:**
| Error | Root Cause | Gnome Response |
|-------|-----------|---|
| `InconsistentPhaseData` | Phase outputs don't align (e.g., different week counts) | Validate + raise RuntimeDomainError |
| `MissingPhaseOutput` | Phase 5 or earlier phase output missing | Fail with explicit error message |

---

## Full Integration: From Input to Output

```
USER PROVIDES:
├── config/catalogos/mendeslobo/projeto.json
├── config/catalogos/mendeslobo/escopo_eap.json
├── config/catalogos/mendeslobo/precedencia.json
├── config/catalogos/mendeslobo/produtividade.json
└── (master catalog + pricing, loaded automatically)

CLI ENTRY:
$ concilium avancar escopo --projeto mendeslobo

LifecycleCoordinator ORCHESTRATES:
├─ Data Gate: assert_catalog_healthy() [validate all CPUs exist]
├─ Pre-Flight: Load canonic inputs ✓
├─ Execute:
│  ├─ Phase 1 (02-cronograma): Calculate effort
│  │  Output: esforco_por_atividade.json
│  ├─ Phase 2 (02-cronograma): Schedule weekly
│  │  Input: esforço + precedência + praticabilidade
│  │  Output: cronograma_semanal.json
│  ├─ Phase 3 (03-equipes): Build teams
│  │  Input: cronograma
│  │  Output: equipes_por_semana.json
│  ├─ Phase 4 (05-indiretos): Merge resources
│  │  Input: equipes + catalogo composição
│  │  Output: recursos_consolidados.json
│  ├─ Phase 5 (06-consolidacao stage 1): Calculate costs
│  │  Input: recursos + pricing cascata
│  │  Output: custos_por_semana.json
│  └─ Phase 6 (06-consolidacao stage 2): Final consolidation
│     Input: all phase outputs
│     Output: consolidacao_executiva.json [FINAL]
└─ Check-Out: Validate + Persist

OUTPUTS:
├── plano_store.skills_log/
│   ├── 02-cronograma/
│   │   ├── esforco_por_atividade.json
│   │   └── cronograma_semanal.json
│   ├── 03-equipes/
│   │   └── equipes_por_semana.json
│   ├── 05-indiretos/
│   │   └── recursos_consolidados.json
│   └── 06-consolidacao/
│       ├── custos_por_semana.json
│       └── consolidacao_executiva.json
└── Executive Dashboard [READY FOR REVIEW/APPROVAL]
```

---

## Error Cascade & Failure Points

If any phase **fails**, execution **stops**. User must fix the input data and **restart from Phase 1**:

```
Phase 1 Error (missing CPU)
  → Fix: Add CPU to catalog or update escopo_eap.json
  → Restart: concilium avancar escopo --projeto mendeslobo

Phase 2 Error (circular precedence)
  → Fix: Update precedencia.json to resolve cycle
  → Restart: concilium avancar escopo --projeto mendeslobo

Phase 3 Error (exceeded team capacity)
  → Fix: Extend project duration or rebalance workload
  → Restart: concilium avancar escopo --projeto mendeslobo

(etc.)
```

**No partial recovery.** All phases must complete successfully for the gnome pipeline to produce a valid consolidation.

---

## Key Differences: What Gnomes Do ≠ What Users Do

| What | Gnomes (Automatic) | Users (Manual) |
|-----|---|---|
| Precedence | Enforce strictly (no inference) | Provide explicitly |
| Productivity | Apply mechanically (no learning) | Adjust based on experience |
| Team sizing | Convert effort to headcount | Define standard team models |
| Resource conflicts | Flag and escalate | Decide resolution strategy |
| Costing | Calculate deterministically | Set prices and BDI % |
| Risk mitigation | Identify (list risks) | Plan (execute mitigations) |

---

## Next Steps: Validate & Execute

1. **Validate MendesLobo Reference:**
   ```bash
   concilium validate catalog config/catalogos/mendeslobo/
   ```

2. **Run Phase 1 (dry-run):**
   ```bash
   concilium avancar escopo --projeto mendeslobo --dry-run --fase 1
   ```

3. **Run Full Pipeline (dry-run):**
   ```bash
   concilium avancar escopo --projeto mendeslobo --dry-run
   ```

4. **Execute (creates immutable snapshots):**
   ```bash
   concilium avancar escopo --projeto mendeslobo
   ```

5. **Review Executive Summary:**
   ```bash
   cat plano_store.skills_log/06-consolidacao/consolidacao_executiva.json
   ```

---

**Document Generated:** 2026-05-12  
**Framework Version:** Concilium v1.2  
**Skills Status:** All 6 gnome phases are fully implemented and integrated with LifecycleCoordinator
