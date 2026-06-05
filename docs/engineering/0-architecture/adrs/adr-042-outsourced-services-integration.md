# ADR-042: Integration of Outsourced Services into Financial Model

**Status:** Proposto 
**Implementation Priority:** Medium (Not required for MARA_ROSA baseline; activated for mixed in-house/outsourced projects)
**Date:** 2026-05-09  
**Author(s):** Engineering Team  
**Supersedes:** None  
**Related:** ADR-009 (Indirect Costs), ADR-023 (BDI Profile Snapshots)

---

## 1. Context

### 1.1 Historical Motivation: CTC Project Case Study

The CTC project (Barra do Ribeiro, RS) analysis revealed a critical gap in financial modelling when outsourced services dominate:

- **Total Scope:** 8 EAP items representing 1,890,919 m³/m² of earthmoving work
- **In-House Direct Work:** 3 items with local team allocation (R$ 3.4M direct cost)
- **Outsourced Work:** 5 items with zero local allocation (~R$ 71.7M reference cost)
- **Financial Impact:** 96% cost delta (reference 75.1M vs. engine 3.4M) due to outsourcing partition

This revealed that the framework lacked mechanisms to model subcontracted work at the same rigor as in-house activities.

### 1.2 Example Project: MARA_ROSA (GO) - Supressão e Sump

To illustrate the proposed ADR design **without outsourcing complications**, this document uses **MARA_ROSA** as the reference implementation example:

- **Project:** Mara Rosa Suppression & Sump (Goiás, Brazil)
- **Scope:** 2 EAP items, all in-house (100% direct team execution)
- **Equipes:** 2 teams with full cost breakdowns (mão_obra, equipamentos, combustível)
- **Planejamento:** Complete in-house activity schedule
- **Use Case:** Demonstrates how future outsourced extensions will integrate with existing in-house model

### 1.3 Motivation for Outsourced Services Support

**Current Model Deficiency:** When outsourced services DO exist (as in CTC), they are modeled as zero-cost items in the canonical project structure:
- No vendor tracking
- No contract references
- No cost allocation mechanism
- No budget vs. actual comparison capability
- Reference data exists in benchmarks but is disconnected from financial tracking

**Future Readiness Requirement:**
- This ADR proposes a design extensible to OUTSOURCED scenarios (not required for MARA_ROSA baseline)
- Implementation will first support MARA_ROSA (pure in-house) validation
- Outsourced model will be activated when projects like CTC or future subcontracting scenarios arise
- Ensures framework can scale to complex mixed in-house/outsourced portfolios

---

## 2. Decision

### 2.1 Proposed Approach

**Integrate outsourced services as first-class financial entities** by extending the project financial model to include:

1. **Outsourced Services Manifest** - Track all subcontracted work
2. **Vendor Registry** - Manage subcontractor information
3. **Contract References** - Link to actual procurement documents
4. **Cost Allocation** - Model outsourced costs with same rigor as in-house work
5. **Variance Analysis** - Compare budgeted vs. actual outsourced costs

### 2.2 Solution Architecture

```
Project Financial Model (Current)
├── In-House Direct Costs (modeled) ✓
│   ├── Equipes → Funcoes, Equipamentos
│   ├── Planejamento → Insumos, Produção
│   ├── Cronograma → Sequenciamento (W1-W27)
│   └── Indiretos → ADM, TOP, LAB, QSMS, MOB
└── Outsourced Costs (NOT modeled) ✗
    └── Cronograma has artificial num_equipes (incorrect)

Project Financial Model (Proposed)
├── In-House Direct Costs (modeled) ✓
│   └── [existing structure]
├── Outsourced Services (modeled) ✓ [NEW]
│   ├── Outsourced Items Manifest
│   │   └── item_id, description, escopo (scope)
│   ├── Vendor Registry
│   │   ├── vendor_id, razao_social, cnpj
│   │   ├── contact, endereco
│   │   └── ramo (specialization: terraplenagem, desmonte, etc)
│   ├── Contracts
│   │   ├── contract_id, vendor_id, reference
│   │   ├── valor_contrato, data_inicio, data_termino
│   │   └── documento_path (procurement attachment)
│   ├── Cronograma Extensions (separated by tipo)
│   │   ├── In-house: num_equipes + qtd_executada model
│   │   └── Outsourced: capacidade_mensal + payment_schedule model
│   └── Cost Allocation
│       ├── custo_budgetado (from contract or benchmark)
│       ├── custo_realizado (actual invoicing)
│       └── variancia_pct
└── Indiretos (may be applied to outsourced services)
```

---

## 3. Detailed Design

### 3.1 Data Structure: Outsourced Services Layer

#### 3.1.1 Outsourced Items Manifest

```json
{
  "outsourced_items": [
    {
      "item_id": "eap-1_5",
      "descricao": "Aterro Compactado a 100% PN",
      "escopo": "outsourced",
      "quantitativo": 738881.15,
      "unidade": "m3",
      "motivo_outsourcing": "Capacidade produtiva — equipamentos especializados",
      "vendor_id": "VEND-ATERRO-001",
      "contract_id": "CONTR-2025-001",
      "data_prevista_inicio": "2025-01-15",
      "data_prevista_fim": "2025-06-20"
    },
    {
      "item_id": "eap-1_2",
      "descricao": "Escavação, carga e transporte — 1ª categoria DMT 1km",
      "escopo": "outsourced",
      "quantitativo": 602697.47,
      "unidade": "m3",
      "motivo_outsourcing": "Longa distância — terceirizar logística reduz overhead",
      "vendor_id": "VEND-ESCAV-001",
      "contract_id": "CONTR-2025-002",
      "data_prevista_inicio": "2025-01-01",
      "data_prevista_fim": "2025-06-11"
    }
  ]
}
```

#### 3.1.2 Vendor Registry

```json
{
  "vendors": [
    {
      "vendor_id": "VEND-ATERRO-001",
      "razao_social": "Companhia de Terraplenagem & Aterros Ltda",
      "cnpj": "12.345.678/0001-90",
      "ramo": ["terraplenagem", "compactacao"],
      "contact": {
        "email": "contratos@terraworks.com.br",
        "telefone": "+55 51 99999-9999",
        "responsavel": "João Silva"
      },
      "endereco": "Barra do Ribeiro, RS",
      "historico_projetos": ["CTC-2025", "USINA-2024"],
      "avaliacao_desempenho": {
        "qualidade": 4.5,
        "cumprimento_prazo": 4.0,
        "comunicacao": 4.8
      }
    }
  ]
}
```

#### 3.1.3 Contracts

```json
{
  "contracts": [
    {
      "contract_id": "CONTR-2025-001",
      "vendor_id": "VEND-ATERRO-001",
      "item_id": "eap-1_5",
      "descricao_servico": "Aterro Compactado a 100% PN — 738,881 m³",
      "valor_contrato": 103467092.23,
      "valor_contrato_unitario": 140.0,
      "data_assinatura": "2024-12-01",
      "data_inicio_vigencia": "2025-01-15",
      "data_termino_vigencia": "2025-06-20",
      "condicoes_pagamento": "30/60/30 — 3 parcelas",
      "documento_path": "projetos/{project_id}/contratos/CONTR-2025-001.pdf",
      "status": "ativo",
      "bdi_aplicado": 0.223736,
      "custo_com_bdi": 128467092.23
    }
  ]
}
```

### 3.2 Schedule Integration (Cronograma)

#### 3.2.1 Current Inconsistency

In CTC, outsourced items are currently tracked in cronograma with artificial `num_equipes` allocations:

| Item | Type | Cronograma Structure | Problem |
|------|------|----------------------|---------|
| eap-1_5 | Outsourced | `num_equipes: 5` per week | Vendor manages own capacity, not our teams |
| eap-1_4 | In-house | `num_equipes: 3` per week | Correct — our team allocation |

**Issue:** Cronograma conflates two different resource models:
- **In-house:** We control team count, productivity, efficiency
- **Outsourced:** Vendor controls everything; we only track progress & payments

#### 3.2.2 Proposed Cronograma Structure

**In-House Activities** (unchanged):
```json
{
  "activity_id": "eap-1_4",
  "tipo": "interno",
  "start_week": 0,
  "end_week": 17,
  "duration_weeks": 18,
  "num_equipes_medio": 2.8889,
  "semanas": {
    "2025-W01": {
      "num_equipes": 3,
      "qtd_executada": 27152.93,
      "eficiencia": 0.8571
    }
  }
}
```

**Outsourced Activities** (new model):
```json
{
  "activity_id": "eap-1_5",
  "tipo": "outsourced",
  "vendor_id": "VEND-ATERRO-001",
  "contract_id": "CONTR-2025-001",
  "start_week": 0,
  "end_week": 21,
  "duration_weeks": 22,
  "data_inicio": "2025-01-01",
  "data_fim": "2025-06-04",
  "semanas": {
    "2025-W01": {
      "capacidade_mensal": 1200000.0,
      "progresso_esperado_pct": 0.04,
      "status": "em_execucao"
    },
    "2025-W05": {
      "capacidade_mensal": 1200000.0,
      "progresso_esperado_pct": 0.22,
      "status": "em_execucao",
      "pagamento": 1200000.0
    }
  },
  "resumo_vendor": {
    "custo_total": 103467092.23,
    "custo_com_bdi": 128467092.23,
    "duracao_meses": 5.98,
    "payment_schedule": [
      { "semana": "2025-W05", "valor": 1200000.0, "parcela": 1 },
      { "semana": "2025-W10", "valor": 1200000.0, "parcela": 2 },
      { "semana": "2025-W15", "valor": 1200000.0, "parcela": 3 },
      { "semana": "2025-W20", "valor": 103467092.23, "parcela": "final" }
    ]
  }
}
```

#### 3.2.3 Cronograma Changes Summary

| Aspect | In-House | Outsourced |
|--------|----------|-----------|
| **Resource Unit** | `num_equipes` (team count) | `capacidade_mensal` (vendor budget) |
| **Progress Measure** | `qtd_executada` (work done) | `progresso_esperado_pct` (% complete) |
| **Efficiency** | `eficiencia` (productivity ratio) | `status` (em_execucao, atraso, concluido) |
| **Cost Tracking** | Via equipes → indiretos chain | Via `payment_schedule` array |
| **Contingency** | Team adjustment | Vendor negotiation / contract clause |

#### 3.2.4 Benefits

✅ **Semantic Clarity:** Cronograma distinguishes what we control (in-house) vs. what vendor manages (outsourced)
✅ **Payment Scheduling:** Explicit cash flow forecast for outsourced services
✅ **Variance Detection:** Can track promised capacity vs. actual progress independently
✅ **No Artificial Teams:** Eliminates fictional `num_equipes` for vendor work

---

### 3.3 Financial Integration Points

#### 3.3.1 Extension to `resultado` (Consolidated Result)

Current structure:
```json
{
  "resultado": {
    "canonical": {
      "venda": { "direto": 1603280.69, ... },
      "custo": {
        "direto_equipes": 3475911.69,
        "direto_catalogo": 1603280.69,
        "indireto_*": ...,
        "total": 31827369.37
      }
    }
  }
}
```

**Proposed extension:**
```json
{
  "resultado": {
    "canonical": {
      "venda": { "direto": 1603280.69, ... },
      "custo": {
        "direto_equipes": 3475911.69,
        "direto_catalogo": 1603280.69,
        "outsourced_services": 103467092.23,  // NEW
        "indireto_*": ...,
        "total": 135294461.60  // Updated
      },
      "custo_breakdown": {
        "in_house_pct": 2.35,     // 3.2M / 135.3M
        "outsourced_pct": 76.46,  // 103.5M / 135.3M
        "indirect_pct": 21.19     // 28.3M / 135.3M
      }
    }
  }
}
```

#### 3.3.2 BDI Application to Outsourced Services

Outsourced services require BDI adjustments for:
- **Administrative overhead** on third-party invoicing
- **Contingency** for delivery risk
- **Profit margin** negotiation

```json
{
  "bdi_applied_to_outsourced": {
    "administrative_markup": 0.08,     // 8% invoice handling overhead
    "contingency": 0.05,               // 5% delivery risk buffer
    "profit_margin": 0.10,             // 10% negotiated margin
    "total_bdi": 0.2385,               // Comparable to in-house (23.87%)
    "custo_com_bdi": 128467092.23
  }
}
```

---

## 4. Implementation

### 4.1 Phase 1: Data Model Extension (Week 1-2)

**Deliverables:**
- [ ] Extend `canonical.json` schema to include `outsourced_services` section
- [ ] Extend `cronograma` section to support `tipo: "interno"` vs `tipo: "outsourced"` differentiation
- [ ] Create `vendors.json` master data file
- [ ] Create `contracts.json` storage structure
- [ ] Add Pydantic validators for contract integrity (vendor_id must exist, dates valid, etc.)

**Files to modify:**
- `src/concilium/domain/models/canonical.py` → Add `OutsourcedServices`, `Vendor`, `Contract` classes; extend `CronogramaAtividade` with `tipo` field
- `src/concilium/domain/models/cronograma.py` → Split weekly data into `InHouseWeek` (num_equipes, qtd_executada, eficiencia) vs `OutsourcedWeek` (capacidade_mensal, progresso_esperado_pct, status, pagamento)
- `src/concilium/infrastructure/repositories/` → Create `vendors_repo.py`, `contracts_repo.py`
- `config/schemas/` → Add JSON schema definitions

**Cronograma Schema Changes:**
```python
# Before
class CronogramaWeek(BaseModel):
    num_equipes: int
    qtd_executada: float
    eficiencia: float

# After
class InHouseWeek(BaseModel):
    num_equipes: int
    qtd_executada: float
    eficiencia: float

class OutsourcedWeek(BaseModel):
    capacidade_mensal: float
    progresso_esperado_pct: float
    status: Literal["em_execucao", "atraso", "concluido", "parado"]
    pagamento: Optional[float] = None  # If payment due this week

class CronogramaWeek(BaseModel):
    __root__: Union[InHouseWeek, OutsourcedWeek]
```

### 4.2 Phase 2: Financial & Schedule Integration (Week 2-3)

**Deliverables:**
- [ ] Update skill-02 (Cronograma) validator to handle `tipo: "outsourced"` separately
  - In-house: validate `num_equipes > 0`, `qtd_executada` aligned with productivity
  - Outsourced: validate `capacidade_mensal` sums to contract total, payment_schedule integrity
- [ ] Update skill-06 (Consolidação) to aggregate outsourced costs from payment_schedule
- [ ] Extend variance analysis to compare:
  - In-house: expected_duration vs. actual_duration
  - Outsourced: budgeted_payment vs. actual_invoice (when received)
- [ ] Implement BDI calculation for outsourced items (administrative markup + contingency + profit)

**Files to modify:**
- `src/concilium/application/skills/skill_02_cronograma.py` → Add outsourced schedule validator
- `src/concilium/application/skills/skill_06_consolidacao.py` → Aggregate outsourced payment schedule into resultado
- `src/concilium/application/benchmarks/analysis/etapa_diffs.py` → Add outsourced variance comparators
- `src/concilium/domain/services/bdi_calculator.py` → Support outsourced item BDI rules

### 4.3 Phase 3: Benchmarking & Reporting (Week 3-4)

**Deliverables:**
- [ ] Extend benchmark reports to show outsourced cost reconciliation
- [ ] Add vendor performance metrics to audit reports
- [ ] Create dashboard widget for in-house vs. outsourced cost visualization

**Files to modify:**
- `src/concilium/application/benchmarks/report_builder.py`
- `src/concilium/presentation/cli/reports/` → Add outsourced variance report

### 4.4 Phase 4: MCP Integration (Week 4-5)

**Deliverables:**
- [ ] Add tools to MCP server for vendor/contract management
- [ ] CRUD operations for outsourced items, vendors, contracts

**Files to create:**
- `src/concilium/presentation/mcp_server/resources/outsourced_services.py`
- `src/concilium/presentation/mcp_server/tools/vendor_management.py`

---

## 5. Consequences

### 5.1 Benefits

✅ **Complete Financial Transparency**
- Single source of truth for all project costs (in-house + outsourced)
- Variance tracking between budget and actual across all services

✅ **Improved Decision Making**
- Quantified in-house vs. outsource trade-off analysis
- Vendor performance metrics for future sourcing decisions
- Better bid evaluation with normalized cost structure

✅ **Contract Traceability**
- Audit trail from EAP item → vendor → contract → invoice
- Regulatory compliance for procurement documentation

✅ **BDI Model Accuracy**
- Consistent markup methodology across all cost categories
- More realistic cost-plus pricing for client proposals

### 5.2 Drawbacks

⚠️ **Additional Data Entry**
- Vendor registry must be maintained separately
- Contract data must be curated from procurement documents

⚠️ **Schema Complexity**
- `canonical.json` and related models become larger
- New validation rules and constraints to enforce

⚠️ **Integration Dependencies**
- Requires coordination with procurement/contracts team
- Vendor IDs and contract references must align with external systems

---

## 6. Risks & Mitigation

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|-----------|
| Vendor registry becomes stale | High | Medium | Implement automated CNPJ validation; quarterly audit schedule |
| Contract data entry errors | Medium | High | Schema validation; required fields; audit trails |
| BDI mismatch between in/out | Medium | Medium | Document BDI methodology; peer review; sensitivity analysis |
| Performance degradation (large vendor DB) | Low | Medium | Index vendor_id; lazy-load contracts; caching |
| Cronograma payment_schedule desync from actual invoices | High | High | Implement invoice matching logic; monthly reconciliation; variance alerts |
| Outsourced activity delays not detected early | Medium | High | Automated status checks in skill-02; weekly progress threshold alerts |
| Conflicting vendor capacity allocations across projects | Medium | Medium | Central vendor capacity registry (future: real-time visibility) |

---

## 7. Alternatives Considered

### 7.1 Alternative 1: Segregated Outsourced Module
**Approach:** Keep outsourced services completely separate from canonical model  
**Pros:** Minimal disruption to current schema  
**Cons:** Manual reconciliation required; duplication of cost logic  
**Decision:** Rejected — violates single source of truth principle

### 7.2 Alternative 2: Benchmark-Only Tracking
**Approach:** Only track outsourced costs in benchmark reports, not in canonical  
**Pros:** Zero impact on core financial model  
**Cons:** Cannot enforce budget constraints; no preventive variance detection  
**Decision:** Rejected — too late for course correction once invoice arrives

### 7.3 Alternative 3: Proposed Integrated Model
**Approach:** Outsourced services as first-class citizens in canonical + contracts metadata  
**Pros:** Unified model; early detection; audit trail; BDI consistency  
**Cons:** Schema expansion; data entry overhead  
**Decision:** Selected ✓

---

## 8. Related Decisions

- **ADR-009 (Indirect Costs & Permanence):** BDI methodology extends to outsourced services
- **ADR-023 (BDI Profile Snapshots):** Contract terms become part of immutable BDI profile
- **ADR-038 (Local Overrides):** Outsourced items can be project-specific (reference via contract)

---

## 9. References

**Primary Reference Implementation:**
- MARA_ROSA Project: `benchmarks/data/MARA_ROSA/referencia.json`
- Full in-house model (no outsourced services) — baseline for ADR validation
- 2 EAP items, 2 teams, complete equipes/cronograma/planejamento structure

**Historical Case Study (Outsourcing Motivation):**
- CTC Benchmark Analysis (2026-05-09): 5 of 8 activities outsourced; R$ 71.7M unmodeled cost
- Benchmark Report: `benchmark_ctc.json` — reference cost 75.1M direto vs. engine 3.4M direto
- Iteration Reference: `benchmarks/data/CTC/iteracao_referencias_ctc.json` — canonical baseline with outsourced zero-cost items

**Cross-Validation Case (No Outsource, BDI/PE Semantics):**
- VALE Benchmark Analysis (2026-05-09): project has no outsourced execution, but uses BDI by category in planning.
- BDI worksheet includes `SERVICOS` category and must remain modeled in `TabelaBdi` even when direct outsourced items are absent.
- Break-even comparison source is the worksheet `C_FIXO`; extraction/audit must accept `ponto_equilibrio` from `C_FIXO`-derived structures when canonical PE is absent.

---

## 10. Timeline & Ownership

| Phase | Owner | Start | End | Dependency |
|-------|-------|-------|-----|------------|
| 1. Data Model | Backend Team | W1 | W2 | None |
| 2. Financial Integration | Skills Team | W2 | W3 | Phase 1 |
| 3. Benchmarking & Reports | Analytics Team | W3 | W4 | Phase 2 |
| 4. MCP Integration | Platform Team | W4 | W5 | Phase 3 |

---

## Appendix A: Example — Outsourced Item Modeling (Future Scenario)

**Note:** This example shows how outsourced services WOULD be modeled when CTC or similar mixed in-house/outsourced projects are processed. MARA_ROSA (current baseline) has no outsourced items.

### Current State (Without Outsourced Support)
```json
{
  "item_id": "eap-1_5",
  "cpu_id": "CPU-TERRA-ATI-017",
  "funcoes": [],
  "equipamentos": [],
  "custo_total": 0.0,
  "modo_estimativa": "inicial",
  "cronograma_nota": "Has num_equipes in schedule (incorrect for vendor work)"
}
```

### Proposed State (Complete)
```json
{
  "item_id": "eap-1_5",
  "descricao": "Aterro Compactado a 100% PN",
  "modo_estimativa": "outsourced",
  "outsourced": {
    "status": "outsourced",
    "vendor_id": "VEND-ATERRO-001",
    "contract_id": "CONTR-2025-001",
    "quantitativo": 738881.15,
    "unidade": "m3",
    "custo_unitario": 140.0,
    "custo_subtotal": 103467092.23,
    "bdi_aplicado": 0.223736,
    "custo_com_bdi": 128467092.23,
    "motivo": "Capacidade produtiva — equipamentos especializados",
    "data_inicio": "2025-01-15",
    "data_termino": "2025-06-20"
  },
  "cronograma_reference": {
    "activity_id": "eap-1_5",
    "tipo": "outsourced",
    "vendor_id": "VEND-ATERRO-001",
    "duration_weeks": 22,
    "payment_schedule_weeks": [5, 10, 15, 20]
  }
}
```

This enables proper budget tracking, variance analysis, and schedule management at execution time.

---

## Appendix B: Example — Cronograma with Outsourced Services (Future Scenario)

**Note:** This example illustrates how cronograma WILL be extended when processing mixed in-house/outsourced projects (e.g., CTC). Current MARA_ROSA cronograma contains only `tipo: "interno"` activities.

### Current State (With Artificial num_equipes for Outsourced)
```json
{
  "cronograma": {
    "atividades": [
      {
        "activity_id": "eap-1_5",
        "tipo_implícito": "???",
        "start_week": 0,
        "end_week": 21,
        "num_equipes_medio": 4.8148,
        "semanas": {
          "2025-W01": {
            "num_equipes": 5,
            "qtd_executada": 33348.73,
            "eficiencia": 0.8571
          }
        }
      }
    ]
  }
}
```
**Problem:** No indication that eap-1_5 is outsourced; num_equipes (5) is meaningless for vendor work.

### Proposed State (Complete)
```json
{
  "cronograma": {
    "atividades": [
      {
        "activity_id": "eap-1_5",
        "tipo": "outsourced",
        "vendor_id": "VEND-ATERRO-001",
        "contract_id": "CONTR-2025-001",
        "start_week": 0,
        "end_week": 21,
        "duration_weeks": 22,
        "data_inicio": "2025-01-01",
        "data_fim": "2025-06-04",
        "semanas": {
          "2025-W01": {
            "capacidade_mensal": 1200000.0,
            "progresso_esperado_pct": 0.04,
            "status": "em_execucao"
          },
          "2025-W05": {
            "capacidade_mensal": 1200000.0,
            "progresso_esperado_pct": 0.22,
            "status": "em_execucao",
            "pagamento": 1200000.0
          },
          "2025-W10": {
            "capacidade_mensal": 1200000.0,
            "progresso_esperado_pct": 0.44,
            "status": "em_execucao",
            "pagamento": 1200000.0
          },
          "2025-W15": {
            "capacidade_mensal": 1200000.0,
            "progresso_esperado_pct": 0.66,
            "status": "em_execucao",
            "pagamento": 1200000.0
          },
          "2025-W20": {
            "capacidade_mensal": 1200000.0,
            "progresso_esperado_pct": 0.95,
            "status": "em_execucao",
            "pagamento": 103467092.23
          },
          "2025-W22": {
            "capacidade_mensal": 0.0,
            "progresso_esperado_pct": 1.0,
            "status": "concluido"
          }
        },
        "resumo_vendor": {
          "custo_total": 103467092.23,
          "custo_com_bdi": 128467092.23,
          "duracao_meses": 5.98,
          "payment_schedule": [
            {
              "semana": "2025-W05",
              "valor": 1200000.0,
              "parcela": 1,
              "descricao": "Adiantamento 1/4"
            },
            {
              "semana": "2025-W10",
              "valor": 1200000.0,
              "parcela": 2,
              "descricao": "Progressão 2/4"
            },
            {
              "semana": "2025-W15",
              "valor": 1200000.0,
              "parcela": 3,
              "descricao": "Progressão 3/4"
            },
            {
              "semana": "2025-W20",
              "valor": 103467092.23,
              "parcela": "final",
              "descricao": "Pagamento Final (inclusive BDI)"
            }
          ]
        }
      },
      {
        "activity_id": "eap-1_4",
        "tipo": "interno",
        "start_week": 0,
        "end_week": 17,
        "duration_weeks": 18,
        "num_equipes_medio": 2.8889,
        "semanas": {
          "2025-W01": {
            "num_equipes": 3,
            "qtd_executada": 27152.93,
            "eficiencia": 0.8571
          }
        }
      }
    ]
  }
}
```

**Benefits:**
- ✅ Clear distinction: `tipo: "outsourced"` vs `tipo: "interno"`
- ✅ Vendor-centric metrics: `capacidade_mensal` instead of fictional `num_equipes`
- ✅ Payment tracking: Explicit cash flow forecast aligned with contract terms
- ✅ Progress monitoring: `progresso_esperado_pct` vs. actual delivery
- ✅ Status management: Detect delays early via `status` field
