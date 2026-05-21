# ADR-012: Catalog Completeness via Authoritative Sources per Jurisdiction

**Status:** Implementado  
**Date Decided:** 2026-05-02  
**Date Implemented:** 2026-05-02  
**Implementers:** catalog/catalog_health.py, catalog/completeness.py, models/catalog_gap.py  
**Context:** The Concilium catalog today consists of:
- **11 CPUs** calibrated against AGIS real projects (Lote 09/10 CE)
- **~140 insumos** (labor, equipment, materials)
- **Productivity artifacts** (ADR-007) with confidence levels and calibration history

This catalog is **deep but narrow**: highly accurate for what it covers, but incomplete relative to the full scope of Brazilian infrastructure construction.

### The Problem: Incomplete Catalog = Incomplete Planning

When Skill 00 (scope) or Skill 02-resolver-cpus (ADR-002) tries to resolve an EAP item against the catalog:

```
Input: "Instalação de tubulação PEAD DN400 - saneamento"
Catalog lookup: ❌ NOT FOUND

Options today:
  1. Fail (VAL-SCOPE-NOCANDIDATE)
  2. Use closest CPU by similarity (risky approximation)
  3. Manual override by engineer (breaks automation)
```

**Root cause:** Catalog was grown organically from project needs, not systematically against a reference scope.

### What "Consistent Completeness" Means

Not "every CPU that exists" — that's impossible and unnecessary.

Instead:
```
For a given work domain (e.g., rodovias federais, CE jurisdiction):
  Every service type that COULD appear in an EAP
  MUST have at least one resolvable CPU in the catalog,
  calibrated against an authoritative source for that jurisdiction.
```

**Consistent** = no gaps within declared scope  
**Complete** = covers all expected service types for declared domain  
**Authoritative** = traceable to recognized entities (not guesswork)

---

## Decision

We formalize a **catalog completeness policy** with three components:

### D1 — Authoritative Source Registry per Jurisdiction

Each jurisdiction has a **ranked list of authoritative sources** for CPU/insumo/productivity data:

```python
class FonteAutoritativa(BaseModel):
    """An authoritative source for catalog data in a jurisdiction."""
    
    id: str               # "SICRO_2024_CE"
    nome: str             # "SICRO - Sistema de Custos Referenciais de Obras"
    entidade: str         # "DNIT - Departamento Nacional de Infraestrutura de Transportes"
    url: str              # https://www.gov.br/dnit/sicro
    jurisdicao: str       # "BR" (national) or "BR-CE" (state-level)
    dominio: list[str]    # ["rodovias", "ferrovias", "obras_arte"]
    
    granularidade: Literal["cpu_completa", "insumo_unitario", "produtividade"]
    
    # How to use this source
    cobertura: str        # "Full CPU with composition" | "Unit prices only" | "Productivity only"
    ciclo_atualizacao: str  # "mensal", "trimestral", "anual"
    ultima_consulta: date
    
    # Priority in resolution chain
    prioridade: int       # 1 = highest (use first), 2 = fallback, 3 = last resort
```

#### Brazil: Authoritative Sources by Domain

```yaml
# config/jurisdicoes/BR.json — authoritative sources registry

fontes_autoritativas:
  
  # Tier 1: Government reference tables (highest authority)
  
  SICRO:
    nome: "Sistema de Custos Referenciais de Obras"
    entidade: "DNIT"
    url: "https://www.gov.br/dnit/sicro"
    jurisdicao: "BR"
    dominio: ["rodovias_federais", "ferrovias", "obras_arte_corrente", "obras_arte_especiais"]
    granularidade: "cpu_completa"
    cobertura: "Full CPU: equipment + labor + fuel + unit productivity"
    ciclo_atualizacao: "mensal"
    prioridade: 1
    notas: "Primary reference for DNIT/federal contracts"
  
  SINAPI:
    nome: "Sistema Nacional de Pesquisa de Custos e Índices da Construção Civil"
    entidade: "Caixa Econômica Federal + IBGE"
    url: "https://www.caixa.gov.br/sinapi"
    jurisdicao: "BR"
    dominio: ["edificacoes", "saneamento_basico", "obras_urbanas", "habitacao"]
    granularidade: "insumo_unitario"
    cobertura: "Unit prices for labor and materials; limited productivity"
    ciclo_atualizacao: "mensal"
    prioridade: 1
    notas: "Primary reference for CEF/housing/sanitation contracts"
  
  ORSE:
    nome: "Orçamento de Referência de Sergipe"
    entidade: "SEINFRA-SE"
    url: "https://orse.seinfra.se.gov.br"
    jurisdicao: "BR-SE"
    dominio: ["obras_estaduais", "saneamento", "edificacoes"]
    granularidade: "cpu_completa"
    prioridade: 2
    notas: "State-level reference; use when SICRO doesn't cover service type"
  
  # Tier 2: Industry references
  
  TCPO:
    nome: "Tabelas de Composições de Preços para Orçamentos"
    entidade: "Editora PINI"
    url: "https://pini.com.br/tcpo"
    jurisdicao: "BR"
    dominio: ["edificacoes", "obras_civis_gerais"]
    granularidade: "cpu_completa"
    cobertura: "Full CPU composition; productivity norms"
    ciclo_atualizacao: "anual"
    prioridade: 2
    notas: "Industry standard for general civil works; not government-binding"
  
  # Tier 3: Direct calibration (highest confidence, narrower scope)
  
  AGIS_OBRAS_REAIS:
    nome: "AGIS — Obras reais calibradas"
    entidade: "AGIS / MendesLobo Construtora"
    jurisdicao: "BR-CE"
    dominio: ["rodovias", "ferrovias", "saneamento", "terraplanagem"]
    granularidade: "produtividade"
    cobertura: "Productivity calibrated from real job data (ADR-007)"
    ciclo_atualizacao: "por_obra"
    prioridade: 1  # Highest for productivity (empirical > tabular)
    notas: "Preferred for productivity; may lag for new service types"
```

---

### D2 — Coverage Matrix: Domain × Service Type

For each declared domain, define the **expected service types** (completeness target):

```yaml
# config/cobertura/rodovias_federais.yaml

dominio: "rodovias_federais"
jurisdicao: "BR"
fonte_referencia: "SICRO"

grupos_servico:
  
  DESMATAMENTO:
    servicos_esperados:
      - "Supressão vegetal DAP >= 0.30"
      - "Limpeza de camada vegetal"
      - "Desmatamento, destocamento, limpeza"
    status_catalogo: "COMPLETO"  # All CPUs present
  
  TERRAPLANAGEM:
    servicos_esperados:
      - "Escavação 1ª categoria DMT até 2000m"
      - "Escavação 1ª categoria DMT 2000–3000m"
      - "Escavação 2ª categoria DMT até 2000m"
      - "Escavação 2ª categoria DMT 2000–3000m"
      - "Escavação 3ª categoria DMT até 2000m"
      - "Escavação 3ª categoria DMT 2000–3000m"
      - "Aterro compactado 100% PN"
      - "Aterro compactado 100% PI"
      - "Construção de corpo de aterro 3ª categoria"
      - "Compactação camada final rocha"
    status_catalogo: "COMPLETO"
  
  DRENAGEM:
    servicos_esperados:
      - "Corpo BSTC D=0.60m"
      - "Corpo BSTC D=0.80m"
      - "Corpo BSTC D=1.00m PA1"
      - "Corpo BSTC D=1.00m PA2"
      - "Corpo BSTC D=1.20m PA2"
      - "Corpo BDTC D=1.00m"
      - "Corpo BSCC 1.50×2.00m"
      - "Corpo BSCC 2.00×2.00m"
      - "Boca tubular"
      - "Boca celular"
      - "Sarjeta de corte"
      - "Descida d'água"
    status_catalogo: "PARCIAL"  # Some CPUs missing
    lacunas:
      - "BSTC D=0.60m"  # Not in catalog yet
      - "BSTC D=0.80m"  # Not in catalog yet
      - "Sarjeta de corte"  # Not in catalog yet
    fonte_preenchimento: "SICRO_2024_CE"
  
  PAVIMENTACAO:
    servicos_esperados:
      - "Sub-base de solo melhorado"
      - "Base de brita graduada tratada com cimento (BGTC)"
      - "Imprimação betuminosa"
      - "Pintura de ligação"
      - "Concreto betuminoso usinado a quente (CBUQ)"
      - "CBUQ camada de rolamento"
      - "CBUQ camada de ligação (binder)"
    status_catalogo: "PARCIAL"
    lacunas:
      - "Sub-base de solo melhorado"
      - "Imprimação betuminosa"
    fonte_preenchimento: "SICRO_2024_CE"
  
  SANEAMENTO:
    servicos_esperados:
      - "Tubo PVC PBA D=50mm"
      - "Tubo PVC PBA D=75mm"
      - "Tubo PVC PBA D=100mm"
      - "Tubo PVC PBA D=150mm"
      - "Tubo PEAD D=200mm"
      - "Tubo PEAD D=400mm"
      - "Poço de visita padrão"
      - "Poço de visita profundo"
      - "Estação elevatória de esgoto"
    status_catalogo: "PARCIAL"
    lacunas:
      - "Tubo PEAD D=200mm"
      - "Tubo PEAD D=400mm"
      - "Estação elevatória"
    fonte_preenchimento: "SINAPI_2024"
```

---

### D3 — Gap Detection and Resolution Workflow

```python
class CatalogGapDetector:
    """
    Detect gaps between expected coverage and actual catalog.
    Triggered: on catalog load, on new project initialization.
    """
    
    def detect_gaps(
        self,
        dominio: str,
        catalogo: CatalogoAgis,
        cobertura_config: CoberturaConfig,
    ) -> list[CatalogGap]:
        """
        Compare expected service types vs catalog CPUs.
        Return list of gaps with resolution suggestions.
        """
        gaps = []
        
        for grupo, config in cobertura_config.grupos_servico.items():
            for servico_esperado in config.servicos_esperados:
                
                # Check if CPU exists
                cpu_match = catalogo.find_cpu_by_description(servico_esperado)
                
                if not cpu_match:
                    gaps.append(CatalogGap(
                        grupo=grupo,
                        servico_esperado=servico_esperado,
                        status="AUSENTE",
                        fonte_sugerida=config.fonte_preenchimento,
                        prioridade=self._estimate_priority(servico_esperado, dominio),
                    ))
                
                elif cpu_match.producao_id is None:
                    gaps.append(CatalogGap(
                        grupo=grupo,
                        servico_esperado=servico_esperado,
                        cpu_existente=cpu_match.codigo,
                        status="SEM_PRODUTIVIDADE",
                        fonte_sugerida="AGIS_OBRAS_REAIS ou SICRO",
                        prioridade="MEDIA",
                    ))
                
                elif cpu_match.producao.qualidade.confianca_pct < 60:
                    gaps.append(CatalogGap(
                        grupo=grupo,
                        servico_esperado=servico_esperado,
                        cpu_existente=cpu_match.codigo,
                        status="BAIXA_CONFIANCA",
                        confianca_atual=cpu_match.producao.qualidade.confianca_pct,
                        fonte_sugerida="Calibrar contra obra real",
                        prioridade="BAIXA",
                    ))
        
        return gaps


class CatalogGapResolver:
    """
    Resolve gaps by fetching data from authoritative sources.
    """
    
    def resolve(
        self,
        gap: CatalogGap,
        fontes: dict[str, FonteAutoritativa],
    ) -> ResolutionProposal:
        """
        For a given gap, propose CPU + productivity from authoritative source.
        
        Sources checked in priority order per jurisdiction.
        """
        
        fonte = fontes[gap.fonte_sugerida]
        
        # Fetch from authoritative source (manual or automated)
        dados_fonte = self._fetch_from_source(fonte, gap.servico_esperado)
        
        if not dados_fonte:
            return ResolutionProposal(
                gap=gap,
                status="NAO_ENCONTRADO",
                acao_requerida="Manual research required",
            )
        
        # Build CPU proposal from source data
        cpu_proposal = CPU(
            codigo=self._generate_cpu_code(gap.servico_esperado),
            descricao=gap.servico_esperado,
            unidade=dados_fonte.unidade,
            origem=f"Proposto a partir de {fonte.id}",
            composicao_itens=dados_fonte.composicao,
        )
        
        # Build productivity artifact
        producao_proposal = Producao(
            id=self._generate_producao_id(cpu_proposal.codigo),
            valor_horario=dados_fonte.produtividade_horaria,
            origem=OrigemProducao(
                tipo="tabela_referencia",
                fonte_id=fonte.id,
                data_calibracao=date.today(),
                referencia=f"Fonte: {fonte.nome}; {fonte.url}",
            ),
            qualidade=QualidadeProducao(
                confianca_pct=70,  # Tabular reference: lower than real data
                intervalo_confianca=None,  # Unknown from table
                quantidade_amostras=0,
                desvio_padrao=None,
            ),
        )
        
        return ResolutionProposal(
            gap=gap,
            status="PROPOSTO",
            cpu_proposta=cpu_proposal,
            producao_proposta=producao_proposal,
            requer_aprovacao=True,  # Engineer must approve before catalog update
            aprovador="engenheiro_senior",
        )
```

---

### D4 — Approval Workflow for New Catalog Entries

New CPUs/productivities from authoritative sources require approval:

```
Gap detected
  ↓
CatalogGapResolver proposes CPU + Producao
  ↓
Senior Engineer reviews:
  ├─ Does CPU composition match AGIS's equipment fleet?
  ├─ Is productivity realistic for local conditions?
  ├─ Any adjustments needed (soil type, DMT, etc.)?
  └─ Approve / Reject / Request calibration
  ↓
If APPROVED:
  ├─ CPU written to config/catalogos/agis/cpus.json
  ├─ Producao written to config/producoes/<id>.json
  ├─ Cobertura config updated (gap → COMPLETO)
  └─ Changelog entry logged
  ↓
If CALIBRATE:
  └─ Flag for calibration on next project that uses this service type
```

---

### D5 — Catalog Health Metrics

```python
class CatalogHealthReport(BaseModel):
    """Snapshot of catalog completeness for a domain."""
    
    dominio: str
    jurisdicao: str
    data_avaliacao: date
    
    # Coverage
    total_servicos_esperados: int
    total_cpus_presentes: int
    total_gaps: int
    cobertura_pct: float = total_cpus_presentes / total_servicos_esperados × 100
    
    # Quality
    producoes_com_dados_reais: int   # origem = "calibrado_contra_obra_real"
    producoes_apenas_tabulares: int  # origem = "tabela_referencia"
    producoes_confianca_baixa: int   # confianca_pct < 60
    confianca_media: float           # average across all producoes
    
    # Gaps by type
    gaps_ausente: int                # No CPU at all
    gaps_sem_produtividade: int      # CPU exists, no productivity
    gaps_baixa_confianca: int        # Productivity low confidence
    
    # Status
    status: Literal["COMPLETO", "ADEQUADO", "PARCIAL", "INSUFICIENTE"]
    # COMPLETO: cobertura ≥ 95%, confianca_media ≥ 80%
    # ADEQUADO: cobertura ≥ 80%, confianca_media ≥ 70%
    # PARCIAL: cobertura ≥ 60%
    # INSUFICIENTE: cobertura < 60%
```

---

### D6 — Jurisdiction Expansion Protocol

When Concilium is used in a **new jurisdiction** (e.g., Bahia, Pará, or abroad):

```
1. Identify jurisdiction (state, country)
2. Add jurisdiction config (config/jurisdicoes/BR-BA.json):
   - Authoritative sources for this jurisdiction
   - Labor law specifics (encargos)
   - Regional price indices
3. Clone nearest existing coverage config as starting point
4. Run gap detection against new jurisdiction's authoritative source
5. Resolve gaps (tabular first, then calibrate on first real project)
6. Set health metric target (ADEQUADO before first project)
```

---

## CLI

```bash
# Check catalog health for a domain
concilium catalog health --domain rodovias_federais --jurisdiction BR-CE

# Output:
# Catalog Health: rodovias_federais / BR-CE
# Coverage: 78% (47/60 services)
# Confidence: 82% avg
# Status: ADEQUADO
#
# Gaps (13):
#   AUSENTE (8):
#     - DRENAGEM: Sarjeta de corte
#     - PAVIMENTACAO: Sub-base solo melhorado
#     - SANEAMENTO: Tubo PEAD D=400mm
#     (... + 5 more)
#   SEM_PRODUTIVIDADE (3):
#     - CPU-BSTC-0060: Body BSTC D=0.60m
#     (... + 2 more)
#   BAIXA_CONFIANCA (2):
#     - COMPACT-ATERRO-100PN (confianca: 55%)
#     (... + 1 more)

# Resolve gaps from authoritative source
concilium catalog resolve-gaps \
  --domain rodovias_federais \
  --jurisdiction BR-CE \
  --source SICRO_2024_CE

# Output:
# Proposed 8 new CPUs from SICRO_2024_CE
# Proposed 3 productivity artifacts from SICRO_2024_CE
# Pending approval by senior engineer
# Run: concilium catalog approve-proposals --list

# List pending proposals
concilium catalog approve-proposals --list

# Approve specific proposal
concilium catalog approve-proposals --id SARJ-CORTE-001 \
  --approved-by eng_silva \
  --note "Composition verified against AGIS fleet"
```

---

## Validation Rules

| Code | Condition | Severity |
|------|-----------|----------|
| **VAL-CAT-01** | CPU without `producao_id` | AVISO |
| **VAL-CAT-02** | CPU references non-existent `producao_id` | ERRO |
| **VAL-CAT-03** | Producao without documented origin | ERRO |
| **VAL-CAT-04** | Producao confidence < 60% | AVISO |
| **VAL-CAT-05** | Catalog coverage < 80% for declared domain | AVISO |
| **VAL-CAT-06** | Authoritative source not consulted in > 6 months | AVISO |
| **VAL-CAT-07** | New CPU approved without senior engineer sign-off | ERRO |

---

## Related ADRs

- **ADR-007** (Productivity Artifact): Source structure for `Producao` model
- **ADR-002** (CPU Resolution): Consumer of catalog completeness (gaps → VAL-SCOPE-NOCANDIDATE)
- **Skill 05-indiretos** (existing): Unaffected (indiretos don't depend on catalog CPUs)

---

## Definition of Done

- [ ] `FonteAutoritativa` model + registry per jurisdiction
- [ ] Coverage matrix config (rodovias_federais at minimum)
- [ ] `CatalogGapDetector` implemented + tested
- [ ] `CatalogGapResolver` (proposal generation from source)
- [ ] `CatalogHealthReport` model + metrics calculation
- [ ] Approval workflow (proposal → review → approve → write)
- [ ] Jurisdiction expansion protocol documented
- [ ] CLI: `catalog health`, `catalog resolve-gaps`, `catalog approve-proposals`
- [ ] Validation rules VAL-CAT-01 to 07
- [ ] Initial gap analysis run for rodovias_federais / BR-CE
- [ ] 6+ test cases:
  - [ ] Gap detected correctly (CPU absent)
  - [ ] Gap detected for missing productivity
  - [ ] Gap detected for low confidence
  - [ ] Proposal generated from SICRO
  - [ ] Approval workflow persists entry
  - [ ] Health report metrics calculated correctly

---

## Summary

**Decision:** The catalog is not "correct" unless it is also **consistently complete** for its declared domain and jurisdiction.

```
Completeness = f(domain, jurisdiction)

For each (domain, jurisdiction) pair:
  1. Authoritative sources registered (SICRO, SINAPI, TCPO, etc.)
  2. Expected service types declared (coverage matrix)
  3. Gaps detected automatically (present vs. expected)
  4. Gaps resolved from authoritative sources (with approval)
  5. Health metrics tracked (cobertura%, confianca_media)
```

**Consequence:**
- Before first project in new domain/jurisdiction: run gap analysis
- Gaps filled from authoritative sources (not invented)
- Productivity from real projects (ADR-007) beats tabular when available
- Catalog health is **observable and improvable**, not assumed