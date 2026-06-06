# Plano de Implementação — Camada Semântica e Resolução

> **Contexto:** ADR-001 (Semantic Layer) + ADR-002 (Resolution & Matching Strategy)  
> **Ancoragem no código atual:** O `EapItem` hoje já chega com `cpu_id` resolvido.  
> Esse plano adiciona a camada que existe *antes* disso — transforma texto de cliente em `EapItem` auditável.

---

## Estado atual (ancoragem)

```
Cliente entrega EAP com cpu_id já preenchido (manual)
        ↓
Skill 00-escopo valida VAL-EAP-01/02/03
        ↓
Pipeline de planejamento
```

**Problema:** o `cpu_id` é imputado manualmente ou inferido por fora do sistema.
Não há rastreabilidade de por que aquela CPU foi escolhida, nem validação estruturada da compatibilidade.

```
EapItem hoje:
  item_id, ordem, cpu_id, descricao, unidade, quantitativo, origem_template
  
CPU hoje:
  codigo, descricao, unidade, categoria, producao_horaria,
  composicao_itens, composicao_padrao_equipe,
  atributos_categoria { dmt_min_metros, dmt_max_metros }
```

**Estado alvo:**

```
Texto bruto do cliente
        ↓
[Camada Semântica]  ←── ADR-001
        ↓
SemanticIntent estruturado
        ↓
[Camada de Resolução]  ←── ADR-002
        ↓
ResolutionDecision (persistido, imutável)
        ↓
EapItem enriquecido com rastreabilidade
        ↓
Skill 00-escopo (inalterada)
```

---

## Princípios que guiam o plano

1. **Rejeição é resultado válido** — silêncio nunca é opção  
2. **Determinismo antes de flexibilidade** — embeddings assistem, nunca decidem  
3. **Imutabilidade de decisões** — append-only, nunca update  
4. **Explicitidade de atributos ausentes** — `None` explícito, não campo omitido  
5. **Versão como contrato** — toda execução referencia `ruleset_version` + `scoring_config_version`

---

## Estrutura de diretórios alvo

```
src/concilium/
├── semantic/
│   ├── __init__.py
│   ├── intent.py            ← SemanticIntent, Dimension, ExtractionConfidence
│   ├── extractor.py         ← Pipeline: rules → vocab → LLM fallback
│   ├── normalizer.py        ← ATTRIBUTE_REGISTRY, unit normalization
│   └── vocabularies/
│       ├── activities.yaml  ← Controlled vocab: activity_type
│       ├── materials.yaml   ← Controlled vocab: materiais
│       └── units.yaml       ← Unit aliases + canonical forms
│
├── resolution/
│   ├── __init__.py
│   ├── models.py            ← CPUCanonical, ResolutionDecision, ScoringConfig,
│   │                            Candidate, ResolutionContext, DecisionReview
│   ├── constraints.py       ← Hard constraint checks (unit, domain, attributes)
│   ├── scoring.py           ← Feature extraction + weighted scoring
│   ├── confidence.py        ← Confidence assignment (anti-bullshit mechanism)
│   ├── resolver.py          ← Main pipeline: retrieval → filter → score → decide
│   ├── registry.py          ← ATTRIBUTE_REGISTRY (canonical attribute definitions)
│   └── storage.py           ← ResolutionDecisionStore (append-only persistence)
│
├── models/
│   ├── catalogo.py          ← [EXTEND] CPUCanonical + atributos normalizados
│   └── canonical.py         ← [EXTEND] EapItem com resolution_decision_id
│
└── skills/manifests/
    └── 00-escopo/skill.py   ← [EXTEND] aceita scope_items brutos → chama resolver
```

---

## Fase S1 — Fundação: Modelos e Vocabulários (Semana 1)

### Sprint S1.1 — `SemanticIntent` e tipos relacionados

**Arquivo:** `src/concilium/semantic/intent.py`

```python
from typing import Optional, Literal
from pydantic import BaseModel, ConfigDict, Field

DomainType = Literal["earthwork", "pavement", "drainage", "structure", "other"]

class Dimension(BaseModel):
    """Atributo quantitativo explícito de um item de escopo."""
    model_config = ConfigDict(extra="forbid")
    
    name: str       # canonical name: "thickness", "depth", "dmt", "width"
    value: float
    unit: str       # canonical unit after normalization: "cm", "m", "m3"

class ExtractionConfidence(BaseModel):
    """Confiança por campo. Explícito — nunca implícito."""
    model_config = ConfigDict(extra="ignore")
    
    domain: float = Field(ge=0.0, le=1.0)
    activity_type: float = Field(ge=0.0, le=1.0)
    unit: float = Field(ge=0.0, le=1.0)
    dimensions: float = Field(ge=0.0, le=1.0)
    materials: float = Field(ge=0.0, le=1.0, default=0.0)

class SemanticIntent(BaseModel):
    """
    Representação canônica de um item de escopo do cliente.
    
    É uma *hipótese estruturada de intenção* — não é verdade absoluta.
    Gaps explícitos (None) são preferíveis a inferências silenciosas.
    
    Invariantes:
    - unit é sempre presente e normalizado
    - dimensions são sempre estruturadas (nunca em free text)
    - raw_text sempre rastreável
    - atributo ausente → None explícito, não campo omitido
    """
    model_config = ConfigDict(extra="forbid")
    
    # Origem
    raw_text: str
    scope_item_id: str  # ID gerado pelo chamador para rastreabilidade
    
    # Classificação
    domain: DomainType
    activity_type: str  # controlled vocab: "cut_fill", "subgrade_compaction", etc.
    
    # Atributos físicos
    unit: str           # normalizado: "m2", "m3", "m", "un"
    dimensions: list[Dimension] = Field(default_factory=list)
    qualifiers: list[str] = Field(default_factory=list)
    
    # Composição material
    materials: list[str] = Field(default_factory=list)  # ["brita_graduada", "cimento"]
    method: Optional[str] = None  # "mecanized", "manual", "mixed"
    
    # Contexto de execução
    context: dict[str, str | float | bool] = Field(default_factory=dict)
    # ex: {"location_type": "urban", "access": "restricted", "soil_class": "C"}
    
    # Qualidade da extração
    extraction_confidence: ExtractionConfidence
    
    # Atributos ausentes explícitos (campo obrigatório faltou → listado aqui)
    missing_attributes: list[str] = Field(default_factory=list)
    
    # Sinaliza se passou por LLM fallback (deve ser auditado)
    used_llm_fallback: bool = False

class SemanticParseError(Exception):
    """Falha ao construir SemanticIntent válido. Propagada, nunca silenciada."""
    
    def __init__(self, raw_text: str, reason: str, missing: list[str] = None):
        self.raw_text = raw_text
        self.reason = reason
        self.missing = missing or []
        super().__init__(f"SemanticParseError: {reason} | input='{raw_text[:80]}'")
```

**Checks:**
- `unit` nunca vazio (raise `SemanticParseError`)  
- `domain` nunca `"other"` sem `missing_attributes` populado  
- `dimensions` nunca codificadas como texto em `qualifiers`

**Escrever 5+ testes:**
- Construção válida completa
- Falha: unit ausente → `SemanticParseError`
- Falha: dimensão embutida em qualifiers (deve estar em `dimensions`)
- Extração com campos missing → listados em `missing_attributes`
- Rastreabilidade: `raw_text` preservado intacto

---

### Sprint S1.2 — Vocabulários controlados

**Arquivos:** `src/concilium/semantic/vocabularies/`

```yaml
# activities.yaml — vocabulário canônico de activity_type
# Formato: canonical_id: {label_pt, domain, aliases_pt, aliases_en}

earthwork:
  cut_fill:
    label_pt: "Corte e aterro"
    domain: earthwork
    aliases_pt: ["escavação e aterro", "corte/aterro", "terraplanagem"]
    aliases_en: ["cut and fill", "earthwork", "grading"]
    required_dimensions: []
    optional_dimensions: ["dmt", "soil_class"]

  subgrade_compaction:
    label_pt: "Compactação de subleito"
    domain: earthwork
    aliases_pt: ["compactação do subleito", "regularização do subleito"]
    required_dimensions: []
    optional_dimensions: ["compaction_rate", "thickness"]

pavement:
  base_course:
    label_pt: "Base granular"
    domain: pavement
    aliases_pt: ["base de brita", "BGS", "base granulométrica"]
    required_dimensions: ["thickness"]
    optional_dimensions: ["strength_cbr"]

  wearing_course:
    label_pt: "Revestimento asfáltico"
    domain: pavement  
    aliases_pt: ["CBUQ", "revestimento", "camada de rolamento", "asfalto"]
    required_dimensions: ["thickness"]
    optional_dimensions: ["binder_content"]

# ... demais atividades
```

```yaml
# units.yaml — unidades canônicas e aliases
m3:
  aliases: ["m³", "metros cubicos", "metros cúbicos", "M3"]
  dimension_type: volume

m2:
  aliases: ["m²", "metros quadrados", "metros quadrado", "M2"]
  dimension_type: area

m:
  aliases: ["ml", "metros lineares", "metro linear", "ML"]
  dimension_type: length

un:
  aliases: ["unid", "unidade", "und", "pç", "peca"]
  dimension_type: count
```

```yaml
# materials.yaml — materiais e aliases
brita_graduada:
  aliases: ["BGS", "brita graduada simples", "material granular"]
  domain: pavement

cbuq:
  aliases: ["concreto asfáltico", "asfalto usinado", "CA"]
  domain: pavement

solo_natural:
  aliases: ["material de 1a categoria", "material 1a", "solo argilo"]
  domain: earthwork
```

**Regras de vocabulário:**
- Aliases são case-insensitive
- Correspondência exata precede fuzzy
- Vocabulário não cobre → `missing_attributes` + confiança < 0.5

---

### Sprint S1.3 — `CPUCanonical` e `ATTRIBUTE_REGISTRY`

**Arquivo:** `src/concilium/resolution/registry.py`

```python
from dataclasses import dataclass
from typing import Any, Callable

@dataclass
class AttributeDefinition:
    canonical_name: str
    type_: type
    unit: str                          # canonical unit for comparison
    aliases: list[str]                 # outros nomes no catálogo
    normalizer: Callable[[Any], float] # converte para canonical unit
    tolerance_pct: float = 0.0         # margem para match parcial (0.0 = exact)

ATTRIBUTE_REGISTRY: dict[str, AttributeDefinition] = {
    "thickness": AttributeDefinition(
        canonical_name="thickness",
        type_=float,
        unit="cm",
        aliases=["espessura", "thickness_mm", "espessura_cm", "thick"],
        normalizer=lambda x, src_unit: x / 10 if src_unit == "mm" else x,
        tolerance_pct=0.15,  # 15% tolerance for thickness match
    ),
    "dmt": AttributeDefinition(
        canonical_name="dmt",
        type_=float,
        unit="m",
        aliases=["dmt_min_metros", "dmt_max_metros", "distancia_media_transporte"],
        normalizer=lambda x, _: x,
        tolerance_pct=0.20,
    ),
    "compaction_rate": AttributeDefinition(
        canonical_name="compaction_rate",
        type_=float,
        unit="pct",
        aliases=["grau_compactacao", "gc_pct"],
        normalizer=lambda x, _: x,
        tolerance_pct=0.05,
    ),
    "soil_class": AttributeDefinition(
        canonical_name="soil_class",
        type_=str,
        unit="class",
        aliases=["categoria_material", "classe_solo"],
        normalizer=lambda x, _: x.upper(),
        tolerance_pct=0.0,  # exact match for categorical
    ),
}
```

**Arquivo:** `src/concilium/resolution/models.py` — `CPUCanonical`

```python
class CPUCanonical(BaseModel):
    """
    Representação normalizada de uma CPU para comparação estruturada.
    
    Gerada a partir de CPU do catálogo via normalização.
    Normalizada na ingestão — nunca em runtime.
    Atributos ausentes são None explícito.
    """
    model_config = ConfigDict(extra="forbid")
    
    cpu_id: str                  # referência para CPU original no catálogo
    domain: DomainType
    activity_type: str           # vocabulary-mapped
    unit: str                    # normalizado
    base_productivity: float     # m2/day, m3/day, etc.
    
    # Atributos canônicos (chaves = ATTRIBUTE_REGISTRY keys)
    attributes: dict[str, float | str | None]
    # None = ausente explícito. Ausente no dict = não aplicável à categoria.
    
    required_attributes: set[str]  # se ausente → candidato inelegível
    optional_attributes: set[str]  # ausente → penalidade parcial
```

**Regra crítica:** `CPUCanonical` é produzido pelo `CatalogNormalizer` uma vez,
armazenado junto ao snapshot do catálogo. **Nunca normalizado em tempo de resolução.**

---

## Fase S2 — Extrator Semântico (Semana 2)

### Sprint S2.1 — Pipeline de extração

**Arquivo:** `src/concilium/semantic/extractor.py`

```python
class SemanticExtractor:
    """
    Pipeline deterministico-first para construção de SemanticIntent.
    
    Ordem:
    1. Extração por regras (regex, números, unidades)
    2. Mapeamento por vocabulário controlado
    3. LLM fallback (opcional, deve ser logado e sinalizado)
    
    Se o resultado não satisfaz invariantes → SemanticParseError.
    """
    
    def __init__(
        self,
        vocab_path: Path,
        allow_llm_fallback: bool = False,
        llm_client: Optional[Any] = None,
    ):
        self.vocab = VocabularyLoader(vocab_path)
        self.normalizer = AttributeNormalizer(ATTRIBUTE_REGISTRY)
        self.allow_llm = allow_llm_fallback
        self.llm = llm_client
    
    def extract(self, raw_text: str, scope_item_id: str) -> SemanticIntent:
        """
        Transforma texto bruto em SemanticIntent estruturado.
        
        Raises:
            SemanticParseError: se invariantes não podem ser satisfeitos.
        """
        # Passo 1: extração de números e unidades por regras
        raw_fields = self._rule_based_extraction(raw_text)
        
        # Passo 2: mapeamento de vocabulário
        vocab_fields = self._vocabulary_mapping(raw_text, raw_fields)
        
        # Passo 3: LLM fallback apenas se permitido e necessário
        if self._needs_fallback(vocab_fields) and self.allow_llm:
            vocab_fields = self._llm_fallback(raw_text, vocab_fields)
            vocab_fields["used_llm_fallback"] = True
        
        # Passo 4: validar invariantes
        return self._build_and_validate(raw_text, scope_item_id, vocab_fields)
    
    def _rule_based_extraction(self, text: str) -> dict:
        """
        Extrai números, unidades, dimensões por regex.
        
        Padrões:
          - "(\\d+(?:[.,]\\d+)?)\\s*(cm|mm|m[23]?|%)" → dimensão
          - unidades ao final do texto após quantidade
          - qualificadores em maiúsculas ou entre parênteses
        """
    
    def _vocabulary_mapping(self, text: str, raw_fields: dict) -> dict:
        """
        Mapeia texto para activity_type, domain, materials do vocab controlado.
        Case-insensitive. Exact match precede fuzzy.
        Sem match → campo como None com confiança baixa.
        """
    
    def _needs_fallback(self, fields: dict) -> bool:
        """Verdadeiro se unit ou domain ausentes após extração deterministica."""
        return fields.get("unit") is None or fields.get("domain") is None
    
    def _build_and_validate(
        self, raw: str, sid: str, fields: dict
    ) -> SemanticIntent:
        """
        Constrói SemanticIntent e valida invariantes.
        
        Raises SemanticParseError para:
        - unit ausente
        - domain == "other" sem missing_attributes
        - dimensão embutida em text (detectada por regex)
        """
```

**Regras de falha explícita (não silenciosa):**

| Condição | Comportamento |
|----------|--------------|
| `unit` não encontrado | `SemanticParseError("missing_unit")` |
| `activity_type` ambíguo (2+ matches com score similar) | `SemanticParseError("ambiguous_activity")` |
| Dimensão em texto livre | `SemanticParseError("dimension_in_freetext")` |
| Categoria não suportada | `SemanticParseError("unsupported_category")` |
| Dimensões conflitantes | `SemanticParseError("conflicting_dimensions")` |

---

### Sprint S2.2 — Normalizador de atributos

**Arquivo:** `src/concilium/semantic/normalizer.py`

```python
class AttributeNormalizer:
    """Normaliza atributos usando ATTRIBUTE_REGISTRY."""
    
    def normalize(
        self,
        raw_name: str,
        raw_value: Any,
        raw_unit: str | None = None,
    ) -> tuple[str, float | str | None]:
        """
        Retorna (canonical_name, normalized_value).
        
        Se raw_name não está no registry (por alias ou canonical):
            retorna (raw_name, raw_value)  ← passthrough, não erro
        
        Se raw_unit incompatível com canonical_unit:
            aplica normalizer
        """
    
    def normalize_unit(self, raw_unit: str) -> str | None:
        """Mapeia alias de unidade para forma canônica. None se desconhecida."""

class CatalogNormalizer:
    """
    Normaliza CPUs do catálogo para CPUCanonical.
    
    Deve ser rodado uma vez na ingestão do catálogo,
    não em runtime de resolução.
    """
    
    def normalize_cpu(self, cpu: CPU) -> CPUCanonical:
        """
        Converte CPU do catálogo para forma canônica.
        
        - Mapeia categoria para DomainType
        - Normaliza atributos via ATTRIBUTE_REGISTRY
        - Determina required_attributes e optional_attributes
          a partir do vocabulário de atividades
        - Atributos ausentes → None explícito no dict
        """
    
    def normalize_catalog(self, cpus: list[CPU]) -> list[CPUCanonical]:
        """Normaliza catálogo inteiro. Armazenar resultado no snapshot."""
```

**Escrever 6+ testes:**
- Normalização de espessura mm → cm
- Alias resolution via registry
- Unidade desconhecida → passthrough
- CPU com dmt_min/dmt_max → atributos canônicos
- CPUCanonical gerado de CPU real do catálogo AGIS
- Catalog normalization rodando sobre os 11 CPUs existentes

---

## Fase S3 — Camada de Resolução (Semanas 3–4)

### Sprint S3.1 — Hard Constraints (filtro determinístico)

**Arquivo:** `src/concilium/resolution/constraints.py`

```python
class ConstraintFilter:
    """
    Gate determinístico. CPU é elegível SOMENTE se todos os hard constraints passam.
    
    Falha em qualquer constraint → CPU descartada do candidate set.
    Constraint failure é logada com motivo explícito.
    """
    
    def check_unit_compatibility(
        self, intent: SemanticIntent, cpu: CPUCanonical
    ) -> ConstraintResult:
        """
        Unit mismatch é hard failure. m2 ≠ m3, ponto final.
        
        Normaliza ambos antes de comparar.
        """
    
    def check_domain_compatibility(
        self, intent: SemanticIntent, cpu: CPUCanonical
    ) -> ConstraintResult:
        """
        Domain/categoria incompatível → descartado.
        TERRAPLENAGEM ≠ PAVIMENTACAO.
        """
    
    def check_required_attributes(
        self, intent: SemanticIntent, cpu: CPUCanonical
    ) -> ConstraintResult:
        """
        Se cpu.required_attributes contém X e intent.dimensions não tem X:
        → cpu é inelegível (falta atributo obrigatório para resolver corretamente)
        
        Não é penalidade. É eliminação.
        """
    
    def check_structural_compatibility(
        self, intent: SemanticIntent, cpu: CPUCanonical
    ) -> ConstraintResult:
        """
        Compatibilidade estrutural específica por categoria:
        - earthwork com DMT: requer faixa DMT compatível
        - pavement: requer espessura dentro da faixa do CPU
        """
    
    def is_eligible(
        self, intent: SemanticIntent, cpu: CPUCanonical
    ) -> tuple[bool, list[ConstraintResult]]:
        """
        Roda todos os checks. Retorna (elegível, detalhes_por_constraint).
        CPU elegível somente se TODOS passam.
        """

@dataclass
class ConstraintResult:
    constraint_name: str
    passed: bool
    reason: str | None = None  # obrigatório se passed=False
```

---

### Sprint S3.2 — Scoring (soft ranking)

**Arquivo:** `src/concilium/resolution/scoring.py`

```python
class FeatureExtractor:
    """
    Extrai features estruturadas para scoring.
    Embeddings = ferramenta de recall, nunca de decisão.
    """
    
    def semantic_similarity(
        self, intent: SemanticIntent, cpu: CPUCanonical
    ) -> float:
        """
        Similarity entre activity_type normalizado de intent e cpu.
        Máximo de peso: 0.4 (ADR hard cap).
        
        Implementação inicial: jaccard sobre tokens normalizados.
        Embedding opcional: apenas se jaccard < 0.3 (edge case handling).
        """
    
    def attribute_match(
        self, intent: SemanticIntent, cpu: CPUCanonical
    ) -> float:
        """
        Score de compatibilidade de atributos.
        
        Para cada atributo em cpu.optional_attributes:
          - presente e dentro da tolerância → contribuição positiva
          - ausente em intent → penalidade proporcional
          - presente mas fora da tolerância → penalidade maior
        
        Atributo ausente em intent.dimensions tem score 0 (não penalidade máxima).
        Atributo conflitante tem score negativo.
        """
    
    def context_fit(
        self, intent: SemanticIntent, cpu: CPUCanonical
    ) -> float:
        """
        Compatibilidade de contexto de execução.
        Ex: intent.context["location_type"] == "urban" 
            → preferir CPUs de execução manual/menor equipamento
        """
    
    def historical_prior(
        self, intent: SemanticIntent, cpu: CPUCanonical,
        history: list[ResolutionDecision]
    ) -> float:
        """
        Frequência histórica de seleção deste cpu_id para activity_types similares.
        
        ⚠️ Cap: não pode dominar score final.
        ⚠️ Detectar loops de bias: se uma CPU domina histórico, 
           limitar boost para evitar self-reinforcement.
        """

class WeightedScorer:
    """
    Aplica pesos configuráveis às features.
    
    Pesos vêm de ScoringConfig (versionado).
    Embedding nunca ultrapassa weight <= 0.4.
    """
    
    def score(
        self,
        intent: SemanticIntent,
        cpu: CPUCanonical,
        config: ScoringConfig,
        history: list[ResolutionDecision] | None = None,
    ) -> ScoredCandidate:
        """
        Retorna ScoredCandidate com score total e breakdown por feature.
        
        Breakdown é obrigatório — sem "black box scoring":
        
        explanations = [
            {
                "feature": "semantic_similarity",
                "value": 0.91,
                "weight": 0.40,
                "contribution": 0.364
            },
            ...
        ]
        """

@dataclass
class ScoredCandidate:
    cpu_id: str
    score: float
    explanations: list[dict]  # structured, not text blobs
```

---

### Sprint S3.3 — Confidence Model (anti-bullshit mechanism)

**Arquivo:** `src/concilium/resolution/confidence.py`

```python
ConfidenceLevel = Literal["HIGH", "MEDIUM", "LOW"]

class ConfidenceAssigner:
    """
    Confiança NÃO é o score.
    
    Alta confiança requer DOIS critérios:
    1. Score acima do threshold_high
    2. Margem para o segundo candidato acima de delta_min
    
    Sem margem → MEDIUM, independente do score absoluto.
    Este é o "anti-bullshit mechanism": 0.83 com segundo em 0.82 = MEDIUM.
    """
    
    def assign(
        self,
        candidates: list[ScoredCandidate],
        config: ScoringConfig,
    ) -> list[CandidateWithConfidence]:
        """
        candidates deve estar ordenado por score desc.
        
        HIGH: score[0] > threshold_high AND (score[0] - score[1]) > delta_min
        MEDIUM: score[0] > threshold_medium (mas não HIGH)
        LOW: abaixo do threshold_medium ou sem candidatos válidos
        
        EDGE CASES explícitos:
        - Apenas 1 candidato → MEDIUM (não há margem calculável)
        - Top-2 empatados → MEDIUM
        - Score alto com atributos ausentes → rebaixar para MEDIUM
        """
    
    def _detect_embedding_failure_modes(
        self, candidates: list[ScoredCandidate]
    ) -> list[str]:
        """
        Detecta:
        1. Alta similarity, baixo attribute_match → likely false positive
        2. Alta similarity em muitos candidatos → baixo poder discriminativo
        3. Ambiguidade semântica → forçar MEDIUM
        """
```

---

### Sprint S3.4 — Pipeline de Resolução

**Arquivo:** `src/concilium/resolution/resolver.py`

```python
class Resolver:
    """
    Pipeline completo: retrieval → constraint → score → confidence → output.
    
    Output é sempre ResolutionOutput — nunca "a resposta direta".
    """
    
    def __init__(
        self,
        catalog: list[CPUCanonical],
        scorer: WeightedScorer,
        confidence_assigner: ConfidenceAssigner,
        decision_store: ResolutionDecisionStore,
        config: ScoringConfig,
        context: ResolutionContext,
    ):
        ...
    
    def resolve(
        self,
        intent: SemanticIntent,
        history: list[ResolutionDecision] | None = None,
    ) -> ResolutionOutput:
        """
        1. Candidate Retrieval (broad, recall-oriented)
        2. Constraint Filtering (deterministic gate)
        3. Feature Extraction
        4. Scoring
        5. Confidence Assignment
        → ResolutionOutput
        
        ResolutionOutput.resolution_status:
        - AUTO_SELECTED: confiança HIGH → pode avançar automaticamente
        - NEEDS_REVIEW: MEDIUM ou LOW → requer validação humana
        - NO_VALID_CANDIDATES: todos eliminados por hard constraints → falha explícita
        """
    
    def _retrieve_candidates(
        self, intent: SemanticIntent
    ) -> list[CPUCanonical]:
        """
        Broad retrieval: filtra por domain inicialmente.
        Top-N por similaridade bruta de activity_type.
        
        Retorna conjunto amplo (recall > precision aqui).
        Precisão fica para constraint filtering.
        """
    
    def _filter_by_constraints(
        self,
        candidates: list[CPUCanonical],
        intent: SemanticIntent,
    ) -> tuple[list[CPUCanonical], list[EliminationLog]]:
        """
        Roda ConstraintFilter em cada candidato.
        Retorna (elegíveis, log de eliminações com motivos).
        
        Log de eliminações é persistido — rastreabilidade de por que CPUs foram excluídas.
        """

class ResolutionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    scope_item_id: str
    intent: SemanticIntent
    
    candidates: list[CandidateWithConfidence]  # ordenados por score desc
    eliminated: list[EliminationLog]           # CPUs eliminadas por hard constraints
    
    resolution_status: Literal["AUTO_SELECTED", "NEEDS_REVIEW", "NO_VALID_CANDIDATES"]
    selected_cpu_id: Optional[str]             # None se NEEDS_REVIEW ou NO_VALID_CANDIDATES
    
    ruleset_version: str
    scoring_config_version: str
```

---

## Fase S4 — Persistência e Governança de Decisões (Semana 5)

### Sprint S4.1 — ResolutionDecision (imutável, append-only)

**Arquivo:** `src/concilium/resolution/models.py`

```python
class ResolutionDecision(BaseModel):
    """
    Decisão de resolução. IMUTÁVEL após criação.
    
    Regra: nunca atualizar. Somente append de novas decisões.
    Uma override gera nova ResolutionDecision com decision_source="USER_OVERRIDE".
    """
    model_config = ConfigDict(extra="forbid", frozen=True)
    
    decision_id: str            # UUID
    scope_item_id: str
    
    # O que foi decidido
    selected_cpu_id: str
    candidate_set: list[CandidateWithConfidence]
    eliminated_set: list[EliminationLog]
    
    # Rastreabilidade de configuração
    scoring_config_version: str
    ruleset_version: str
    
    # Confiança e explicabilidade
    confidence: ConfidenceLevel
    explanations: list[dict]    # structured breakdown obrigatório
    
    # Fonte da decisão
    decision_source: Literal["AUTO", "USER_OVERRIDE", "REVIEWED"]
    
    # Contexto imutável no momento da decisão
    intent_snapshot: SemanticIntent  # snapshot, não referência
    
    created_at: datetime
    
    # Referência a decisão anterior (se USER_OVERRIDE)
    supersedes_decision_id: Optional[str] = None
```

```python
class ScoringConfig(BaseModel):
    """Configuração de scoring. Tratada como modelo — versão explícita."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    
    version: str  # semver: "1.3.2"
    
    weights: dict[str, float]   # feature_name → weight (sum deve = 1.0)
    thresholds: dict[str, float]  # "threshold_high", "threshold_medium", "delta_min"
    
    feature_flags: dict[str, bool]  # "use_embeddings", "use_historical_priors"
    
    # Embedding cap (ADR hard rule: weight <= 0.4)
    max_embedding_weight: float = Field(default=0.4, le=0.4)
    
    created_at: datetime
    lineage: Optional[str] = None  # e.g. "v1.2 → v1.3: fixed attribute bias"

class ResolutionContext(BaseModel):
    """Contexto de resolução por camada (global → domain → project)."""
    
    config_version: str
    override_layer: Literal["GLOBAL", "DOMAIN", "PROJECT"]
    
    overrides: dict[str, Any]
    justification: str          # obrigatório para qualquer override
    
    expiration: Optional[date]  # overrides sem expiração são bugs futuros
    
    # Regra: overrides não podem modificar unit_compatibility
    # nem structural_constraints (checado em ResolutionContext.validate)
```

**Arquivo:** `src/concilium/resolution/storage.py`

```python
class ResolutionDecisionStore:
    """
    Persistência append-only de ResolutionDecision.
    
    Armazena como JSONL (consistente com invocations.log existente).
    Nunca sobrescreve. Nunca deleta.
    
    Regra de falha: API resolve() deve FALHAR se persist() falhar.
    Não existe "best effort logging".
    """
    
    def persist(self, decision: ResolutionDecision) -> None:
        """Falha explicitamente se não conseguir persistir."""
    
    def load_for_scope_item(
        self, scope_item_id: str
    ) -> list[ResolutionDecision]:
        """Retorna todas as decisões para um scope_item, em ordem cronológica."""
    
    def load_recent_for_activity_type(
        self, activity_type: str, limit: int = 50
    ) -> list[ResolutionDecision]:
        """Para cálculo de historical_prior."""
    
    def load_for_project(
        self, project_id: str
    ) -> list[ResolutionDecision]:
        """Todas as decisões de um projeto para auditoria."""
```

---

### Sprint S4.2 — Feedback Loop (DecisionReview)

**Arquivo:** `src/concilium/resolution/models.py`

```python
class DecisionReview(BaseModel):
    """
    Revisão humana de uma ResolutionDecision.
    
    Fecha o loop de calibração:
    ResolutionDecision → Review → Signals → New ScoringConfig version.
    """
    model_config = ConfigDict(extra="forbid")
    
    review_id: str
    decision_id: str
    
    was_correct: bool
    corrected_cpu_id: Optional[str] = None  # se was_correct=False
    
    reviewer_confidence: float = Field(ge=0.0, le=1.0)
    notes: str
    
    # Sinais para calibração
    confidence_mismatch: bool = False  # sistema disse HIGH mas estava errado
    attribute_gap: Optional[str] = None  # qual atributo causou erro de matching
    
    created_at: datetime
```

**Uso do feedback:**
```python
class CalibrationAnalyzer:
    """
    Detecta padrões sistemáticos nas reviews para guiar ajuste de ScoringConfig.
    
    Não ajusta pesos automaticamente — produz relatório para decisão humana.
    """
    
    def detect_systematic_bias(
        self, reviews: list[DecisionReview]
    ) -> BiasReport:
        """
        Exemplos de bias detectável:
        - Taxa de erro > 30% para activity_type específico
        - confidence_mismatch frequente → threshold_high muito baixo
        - Mesmo attribute_gap em múltiplas reviews → feature engineering issue
        """
    
    def suggest_config_changes(
        self, bias_report: BiasReport, current_config: ScoringConfig
    ) -> list[ConfigSuggestion]:
        """Sugestões estruturadas. Humano decide se aplica."""
```

---

## Fase S5 — Integração com Pipeline Existente (Semana 6)

### Sprint S5.1 — Integrar Resolver na Skill 00-escopo

**Objetivo:** Skill 00 passa a aceitar `scope_items` brutos (texto) além do EAP estruturado atual.

**Extensão de `EapItem`:**

```python
class EapItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    item_id: str
    ordem: int = Field(ge=1)
    cpu_id: str
    descricao: str
    unidade: str
    quantitativo: float = Field(gt=0)
    origem_template: bool = False
    
    # NOVO — rastreabilidade semântica
    resolution_decision_id: Optional[str] = None  # None se imputado manualmente
    semantic_confidence: Optional[ConfidenceLevel] = None
```

**Extensão da Skill 00:**

```python
# Skill 00 aceita dois modos de entrada:
# Modo A (atual): eap com cpu_id já resolvido
# Modo B (novo): scope_items com texto bruto → resolve → gera eap

def run_escopo(canonical_in, inputs, catalogo=None) -> SkillResult:
    
    if "scope_items" in inputs:
        # Modo B: resolve semanticamente
        resolved_eap = _resolve_scope_items(
            inputs["scope_items"], catalogo, inputs.get("resolver_config")
        )
        inputs = {**inputs, "eap": resolved_eap}
    
    # Modo A continua inalterado
    ...

def _resolve_scope_items(
    scope_items: list[dict],
    catalogo: dict,
    config: dict | None,
) -> list[dict]:
    """
    Transforma scope_items em eap resolvido.
    Items com status NEEDS_REVIEW → VAL-SCOPE-REVIEW AVISO (não bloqueante).
    Items com NO_VALID_CANDIDATES → VAL-SCOPE-NOCANDIDATE ERRO (bloqueante).
    """
```

**Novos códigos de validação:**

| Código | Status | Condição |
|--------|--------|----------|
| `VAL-SCOPE-PARSE-01` | ERRO | SemanticParseError em item de escopo |
| `VAL-SCOPE-NOCANDIDATE` | ERRO | Nenhum candidato CPU elegível |
| `VAL-SCOPE-REVIEW` | AVISO | Item com confiança MEDIUM/LOW (requer validação humana) |
| `VAL-SCOPE-LLM` | AVISO | Item resolvido com LLM fallback (deve ser revisado) |

---

### Sprint S5.2 — Novo comando CLI

```bash
# Resolver escopo bruto sem criar projeto
concilium resolve scope \
  --context agis \
  --items scope_items.json \
  --config scoring_v1.json \
  --output resolution_report.json

# Output:
# ✅ 8/10 itens: AUTO_SELECTED
# ⚠️  2/10 itens: NEEDS_REVIEW (ver resolution_report.json)
# 
# Para cada item NEEDS_REVIEW: motivo + candidatos rankeados

# Visualizar decisões de um projeto
concilium resolution decisions --project lote09-ce --output decisions.json

# Submeter revisão de uma decisão
concilium resolution review \
  --decision dec-uuid \
  --correct false \
  --corrected-cpu CPU-TERR-04 \
  --note "CPU errada por DMT fora da faixa"

# Análise de calibração
concilium resolution calibrate --project lote09-ce --output bias_report.json
```

---

### Sprint S5.3 — Integração com MCP Server

**Novas ferramentas MCP expostas:**

| Ferramenta MCP | Operação interna |
|----------------|-----------------|
| `interpretar_escopo` | SemanticExtractor.extract() em batch |
| `resolver_cpus` | Resolver.resolve() para todos os itens interpretados |
| `revisar_resolucao` | ResolutionDecisionStore.persist(decision_source="REVIEWED") |
| `relatorio_calibracao` | CalibrationAnalyzer.detect_systematic_bias() |

---

## Fase S6 — Testes, Documentação e Release (Semana 7)

### Sprint S6.1 — Testes

**Cobertura mínima por componente:**

| Componente | Testes mínimos | Cenários-chave |
|-----------|---------------|----------------|
| `SemanticIntent` | 5 | unit ausente, dimensão em freetext, LLM fallback flag |
| `SemanticExtractor` | 8 | regex por categoria, alias vocab, falha explícita vs silenciosa |
| `AttributeNormalizer` | 6 | mm→cm, alias resolution, passthrough, catálogo AGIS real |
| `CatalogNormalizer` | 4 | 11 CPUs AGIS → CPUCanonical sem perda |
| `ConstraintFilter` | 6 | unit mismatch, domain mismatch, required attr missing |
| `WeightedScorer` | 5 | breakdown por feature, embedding cap, histórico |
| `ConfidenceAssigner` | 5 | HIGH com margem, MEDIUM sem margem, 1 candidato |
| `Resolver` | 8 | pipeline end-to-end, NO_VALID_CANDIDATES, NEEDS_REVIEW |
| `ResolutionDecisionStore` | 4 | persist falha → erro; append-only; load_for_project |
| `DecisionReview + Calibration` | 4 | bias detection, mismatch pattern |
| **Integração Skill 00** | 6 | modo A inalterado, modo B com texto, AVISO review |
| **Total** | ~61 | |

**Teste de sanidade da camada semântica:**

```python
def test_semantic_layer_sanity():
    """
    A camada semântica está alinhada se:
    
    1. Texto com unit claro → unit normalizado correto
    2. Texto sem unit → SemanticParseError, não None
    3. Dimensão no texto → Dimension estruturado, não string em qualifiers
    4. CPU com m3 ≠ intent com m2 → eliminado por hard constraint
    5. Score alto mas margem < delta_min → MEDIUM, não HIGH
    6. Override sem justification → rejeitado
    7. Decisão persistida → imutável (frozen=True)
    """
```

---

### Sprint S6.2 — Documentação

- [ ] `ADR-001.md` e `ADR-002.md` como arquivos no repositório (`docs/adr/`)
- [ ] `docs/semantic-layer.md` — guia de uso com exemplos por tipo de obra
- [ ] Docstrings com examples em `SemanticExtractor.extract()`
- [ ] `CHANGELOG.md` atualizado com nova seção `[semantic-v1.0]`
- [ ] README: seção "Resolução de escopo" com fluxo diagram

---

## Resumo de timeline

| Fase | Semana | Sprints | Entregáveis |
|------|--------|---------|-------------|
| **S1** | 1 | S1.1–S1.3 | Modelos (`SemanticIntent`, `CPUCanonical`), vocabulários, `ATTRIBUTE_REGISTRY` |
| **S2** | 2 | S2.1–S2.2 | Extrator semântico, normalizador, pipeline de extração |
| **S3** | 3–4 | S3.1–S3.4 | Hard constraints, scoring, confidence, pipeline completo de resolução |
| **S4** | 5 | S4.1–S4.2 | Persistência imutável, `ScoringConfig` versionado, loop de calibração |
| **S5** | 6 | S5.1–S5.3 | Integração Skill 00, CLI, MCP Server |
| **S6** | 7 | S6.1–S6.2 | 61+ testes, docs, release |

**Total: ~7 semanas**

---

## Riscos e mitigações

| Risco | Mitigação |
|-------|-----------|
| Vocabulários insuficientes para cobrir escopo AGIS real | Rodar extrator nos 11 CPUs + histórico de obras primeiro; expandir vocabulários antes de codar pipeline |
| Embeddings começam a dominar scoring com tempo | Hard cap 0.4 no `ScoringConfig`. `ConfidenceAssigner` penaliza baixa margem |
| Override de projeto viola unit constraint | `ResolutionContext.validate()` rejeita qualquer override em unit/structural |
| Feedback loop cria bias self-reinforcing | `CalibrationAnalyzer` detecta dominância; `historical_prior` tem cap próprio |
| LLM fallback vira caminho primário (LLM creep) | `used_llm_fallback=True` gera `VAL-SCOPE-LLM AVISO` — visível e auditável |

---

## Definition of Done — Camada Semântica v1.0

- [ ] `SemanticIntent` com invariantes testados
- [ ] `SemanticParseError` propagada em todos os casos de falha
- [ ] Vocabulários: activities, materials, units — cobrindo todos os 11 CPUs AGIS
- [ ] `CPUCanonical` gerado para todo o catálogo AGIS sem perda de atributos
- [ ] `ATTRIBUTE_REGISTRY` normaliza: thickness, dmt, compaction_rate, soil_class
- [ ] Hard constraints rejeitam unit mismatch e domain mismatch corretamente
- [ ] `WeightedScorer` com breakdown estruturado por feature (não texto)
- [ ] `ConfidenceAssigner` implementa regra de margem (HIGH = score + margem)
- [ ] Embedding weight nunca ultrapassa 0.4 (enforced em `ScoringConfig`)
- [ ] `ResolutionDecision` é frozen=True (imutável)
- [ ] `ResolutionDecisionStore` falha explicitamente se persistence falha
- [ ] Skill 00 aceita `scope_items` brutos (Modo B)
- [ ] CLI `concilium resolve scope` funcional
- [ ] 61+ testes passando
- [ ] ADR-001 e ADR-002 commitados em `docs/adr/`
- [ ] Sanity check da camada semântica (7 critérios) passando
