# CPU × Insumo × Jurisdição: Documentation Index

**Overview**: Complete specification for architecting versioned CPU-Insumo-Jurisdição models with validation and auditoria.

**Quick Start**: Read in this order:
1. [01-CPU-INSUMO-JURISDICAO.md](01-CPU-INSUMO-JURISDICAO.md) — Executive summary + roadmap (20 min read)
2. [02-INSUMO-MODEL.md](02-INSUMO-MODEL.md) — Insumo types and CPU composition (15 min read)
3. [03-VALIDATIONS.md](03-VALIDATIONS.md) — 7 validation rules with code examples (15 min read)
4. [diagrams/](diagrams/) — Visual specifications

---

## Files Overview

### Core Architecture

#### [01-CPU-INSUMO-JURISDICAO.md](01-CPU-INSUMO-JURISDICAO.md) ⭐ START HERE
**The main document** covering:
- AS-IS problems (9 critical issues identified)
- TO-BE architecture (versionamento + auditoria)
- Sprint roadmap (3 sprints, 54h)
- Impact on existing skills
- Risk mitigation
- Success criteria

**Time**: ~20 min | **Audience**: PM, Architects, Tech Leads

---

#### [02-INSUMO-MODEL.md](02-INSUMO-MODEL.md)
**Deep dive into insumo types and CPU composition**:
- 4 insumo types: MAO_OBRA, EQUIPAMENTO, MATERIAL, TERCEIRIZADO
- M:N relationship CPU ↔ Insumo
- Compatibility rules (type, unit, coefficient)
- Practical example: 80.000 m³ terraplenagem
- 7 required validations

**Time**: ~15 min | **Audience**: Domain Experts, Architects

---

#### [03-VALIDATIONS.md](03-VALIDATIONS.md)
**Implementation guide for 7 validation rules**:
- VAL-CPU-INS-01: Insumo exists?
- VAL-CPU-INS-02: Type compatible?
- VAL-CPU-INS-03: Coefficient > 0?
- VAL-CPU-INS-04: Coefficient in range?
- VAL-CPU-INS-05: Unit compatible?
- VAL-CPU-INS-06: Functions exist?
- VAL-CPU-INS-07: Equipment exist?

Each with code implementation + tests.

**Time**: ~15 min | **Audience**: Developers, QA

---

### Diagrams

#### [diagrams/01-RELATIONSHIPS.md](diagrams/01-RELATIONSHIPS.md)
Mermaid diagrams:
- AS-IS vs TO-BE comparison
- Versioning timeline
- Validation flow

---

#### [diagrams/02-COMPOSITION.md](diagrams/02-COMPOSITION.md)
Mermaid diagrams:
- M:N relationship (ER diagram)
- CPU composition example
- Cost calculation flow
- Type/unit compatibility matrices
- Validation sequence

---

## Related Documentation

### Implementation Roadmap
📍 [../roadmap/IMPLEMENTATION-3SPRINTS.md](../roadmap/IMPLEMENTATION-3SPRINTS.md)

3-sprint plan with:
- Sprint 1: Models (2 weeks)
- Sprint 2: Validations + Auditoria (2 weeks)
- Sprint 3: Skill integration (2 weeks)

---

### Data Integration
📍 [../integration/INSUMO-LOADER.md](../integration/INSUMO-LOADER.md)

Guide for integrating separated insumo data with backwards-compatible loader.

---

## Reading Paths

### For PMs / Project Managers
1. [01-CPU-INSUMO-JURISDICAO.md](01-CPU-INSUMO-JURISDICAO.md) — Executive summary
2. [../roadmap/IMPLEMENTATION-3SPRINTS.md](../roadmap/IMPLEMENTATION-3SPRINTS.md) — Timeline & effort
3. [diagrams/01-RELATIONSHIPS.md](diagrams/01-RELATIONSHIPS.md) — Visual overview

**Time**: 30 min

---

### For Architects
1. [01-CPU-INSUMO-JURISDICAO.md](01-CPU-INSUMO-JURISDICAO.md) — Full architecture
2. [02-INSUMO-MODEL.md](02-INSUMO-MODEL.md) — Domain model deep-dive
3. [03-VALIDATIONS.md](03-VALIDATIONS.md) — Validation layer design
4. [diagrams/](diagrams/) — All diagrams

**Time**: 1 hour

---

### For Developers (Sprint 1)
1. [01-CPU-INSUMO-JURISDICAO.md](01-CPU-INSUMO-JURISDICAO.md) **section 2** — TO-BE models
2. [02-INSUMO-MODEL.md](02-INSUMO-MODEL.md) — Understand insumo structure
3. [diagrams/02-COMPOSITION.md](diagrams/02-COMPOSITION.md) — Visualize relationships

**Time**: 45 min

---

### For Developers (Sprint 2)
1. [03-VALIDATIONS.md](03-VALIDATIONS.md) — Validation implementation guide
2. [02-INSUMO-MODEL.md](02-INSUMO-MODEL.md) **section 5** — Validation matrix

**Time**: 30 min

---

### For Developers (Sprint 3)
1. [01-CPU-INSUMO-JURISDICAO.md](01-CPU-INSUMO-JURISDICAO.md) **section 3** — Skills impact
2. [diagrams/01-RELATIONSHIPS.md](diagrams/01-RELATIONSHIPS.md) — Integration flow

**Time**: 20 min

---

### For QA / Test Engineers
1. [03-VALIDATIONS.md](03-VALIDATIONS.md) — Test cases for each validation
2. [../roadmap/IMPLEMENTATION-3SPRINTS.md](../roadmap/IMPLEMENTATION-3SPRINTS.md) — Acceptance criteria
3. [01-CPU-INSUMO-JURISDICAO.md](01-CPU-INSUMO-JURISDICAO.md) **section 8** — Success metrics

**Time**: 45 min

---

## Key Metrics

| Metric | Value |
|--------|-------|
| **Total Effort** | 54h (3 sprints × 2 weeks) |
| **Team Size** | 2 devs + 1 QA |
| **New Tests** | 50+ (models + validations + E2E) |
| **Target Coverage** | ≥ 85% |
| **Problems Solved** | 9 critical + 4 moderate |
| **Validations Implemented** | 7 (VAL-CPU-INS-*) |

---

## Quick Reference: Problem ↔ Solution

| Problem | Solution | Doc | Status |
|---------|----------|-----|--------|
| P1: Função/Equipamento sem modelo | Create `class Funcao`, `class Equipamento` | [01 § 2](01-CPU-INSUMO-JURISDICAO.md#2-estado-desejado-to-be---arquitetura-proposta) | ⏳ Sprint 1 |
| P2: Encargos implícitos | Explicit encargos + audit trail | [01 § 3](01-CPU-INSUMO-JURISDICAO.md#3-impacto-nas-skills-existentes) | ⏳ Sprint 2 |
| P3: CPU sem versionamento | `CPUVersionada` with history | [01 § 2](01-CPU-INSUMO-JURISDICAO.md#2-estado-desejado-to-be---arquitetura-proposta) | ⏳ Sprint 1 |
| P4: Validação incompleta | Implement VAL-CPU-INS-01 to 07 | [03](03-VALIDATIONS.md) | ⏳ Sprint 2 |
| P5: Circular dependencies | DFS graph validation | [01 § 6](01-CPU-INSUMO-JURISDICAO.md#6-matriz-de-estimativas) | ⏳ Sprint 2 |
| P6: Sem histórico CPU | Versionamento com histórico | [01 § 2](01-CPU-INSUMO-JURISDICAO.md#2-estado-desejado-to-be---arquitetura-proposta) | ⏳ Sprint 1 |
| P7: Jurisdição sem snapshot | Jurisdição versionada | [01 § 2](01-CPU-INSUMO-JURISDICAO.md#2-estado-desejado-to-be---arquitetura-proposta) | ⏳ Sprint 1 |
| P8: Sem auditoria | LayerAuditoria + trail | [01 § 2](01-CPU-INSUMO-JURISDICAO.md#2-estado-desejado-to-be---arquitetura-proposta) | ⏳ Sprint 2 |
| P9: Atributos heterogêneos | Strict validation + schema | [03](03-VALIDATIONS.md) | ⏳ Sprint 2 |

---

## Version History

| Version | Date | Status | Notes |
|---------|------|--------|-------|
| 1.0 | 2026-04-28 | ✅ Published | Consolidated from 7 docs; ready for review |

---

## How to Update This Documentation

When you make changes to the architecture:

1. **Update the relevant section** (01, 02, or 03)
2. **Update diagrams** if architecture changes
3. **Update roadmap** if estimates/scope change
4. **Update this INDEX** if structure changes
5. **Increment version** above

Keep all 4 documents in sync!

---

## Questions?

- **Technical questions**: Ask in the PR for the feature branch
- **Clarifications**: Add a comment to this INDEX
- **Feedback**: Open an issue in the project tracker

