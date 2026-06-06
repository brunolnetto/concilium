# ADR-019 — Re-planejamento de Orçamentação e Gaps Estruturais do Pipeline

**Status:** Implementado  
**Data:** 2026-05-03  
**Data Implementado:** 2026-05-04  
**Implementadores:** skills/06A-reconciliar-custos-recurso, skills/13-replan-advisor, models/canonical.py (ResultadoReconciliado, ReplanSugestao, Alocacao.criticidade_recurso), cli/commands_replan.py  
**Contexto:** MendesLobo Construtora — Concilium

---

## Contexto

Uma revisão estrutural do pipeline de orçamentação identificou quatro gaps que comprometem a viabilidade do framework como ferramenta de planejamento pré-licitação:

**Gap 1 — Pipeline linear sem feedback de margem**
Quando `06-consolidar` retorna `AMARELO` ou `VERMELHO`, o framework não oferece nenhum mecanismo para revisar parâmetros e re-executar a pipeline. O engenheiro recebe o diagnóstico mas precisa criar um projeto novo do zero para simular alternativas. Em obras de terraplenagem, 3 a 5 iterações sobre cronograma e equipes são normais antes de fechar o orçamento.

**Gap 2 — Decisões de recurso (03C) não alcançam o orçamento**
`03C-validar-compartilhamento` pode recomendar `BUY` (aquisição de equipamento) ou `HIRE` (contratação de mão-de-obra). Esses custos não entram em `04-planejamento-bdi` nem em `05-indiretos` porque ambos já executaram quando 03C conclui. O `resultado` de `06-consolidar` está estruturalmente incompleto quando há recomendações de aquisição pendentes.

```
03-equipes-diretas → 04-planejamento-bdi ─┐
03-equipes-diretas → 05-indiretos ─────────┼→ 06-consolidar  ← custo de BUY ausente
03-equipes-diretas → 03A → 03B → 03C       │
                              ↑            │
                          BUY/HIRE ────────┘ (não chega)
```

**Gap 3 — 08-criticality produz criticidade teórica, não operacional**
`08-criticality` executa em paralelo com `03-equipes-diretas` (ambos em L4, após `02-cronograma`). Isso significa que a análise de criticidade desconhece as restrições de alocação de recursos calculadas em `03B`. Um caminho pode ser crítico no papel mas viável operacionalmente se os recursos estiverem livres — ou vice-versa. O relatório atual é criticidade por duração e DAG, não por disponibilidade de recurso.

**Gap 4 — Ausência de skills para contingência, MOB no cronograma e change orders**
Contratos DNIT e ANTT exigem provisão de riscos; o BDI absorve isso de forma opaca sem modelo formal. O cronograma de mobilização afeta o caminho crítico em obras de grande porte mas hoje é apenas custo em `05-indiretos`. Variações de escopo (change orders) forçam re-run completo a partir de `00-escopo`.

Este ADR é **complementar ao ADR-005**, que cobre replanning *durante execução* (Tiers 1/2/3 por atraso, produtividade e overrun). O presente ADR cobre replanning *durante orçamentação*, antes da submissão da proposta.

---

## Decisões

### D1 — Mecanismo de Re-planejamento durante Orçamentação

**Alternativas consideradas:**

| Alternativa | Descrição | Problema |
|-------------|-----------|---------|
| A — Arcos de feedback no DAG | Edges de retorno de 06 para 02 ou 03 | Introduz ciclos; quebra acyclicidade e determinismo |
| B — Re-run por checkpoint como nova revisão | CLI `concilium replan` que cria nova revisão a partir de um skill específico | Preserva histórico, não quebra DAG |
| C — Branching de cenários | Projetos paralelos com parâmetros diferentes | Multiplicação de storage; sem orientação ao engenheiro sobre o que mudar |
| D — Skill advisor de re-planejamento | Nova skill que analisa AMARELO/VERMELHO e propõe ajustes específicos | Complementar a B; orienta o engenheiro |

**Decisão: B + D (checkpoint com nova revisão, orientado por advisor)**

**D1.1 — Comando `concilium replan`**

Cria nova revisão do projeto a partir de um skill de checkpoint, aplicando overrides de parâmetros. O histórico de versões é preservado integralmente.

```bash
# Exemplo: margem VERMELHO → tentar com 3 equipes a partir do cronograma
concilium replan <projeto_id> \
  --from 02-cronograma \
  --set "num_equipes_mes_3=3" \
  --set "num_equipes_mes_4=3" \
  --justificativa "Aumento de equipes para recuperar margem (ADR-019 D1)"

# Exemplo: redimensionar pool de recursos
concilium replan <projeto_id> \
  --from 01A-declarar-recursos \
  --set "pool.escavadeira_cat320.quantidade_total=4" \
  --justificativa "Expansão de frota para reduzir pico 03C"
```

**Regras do mecanismo:**
- Apenas skills que possuem `[replan_checkpoint] enabled = true` no `skill.toml` são pontos de partida válidos
- O re-run recalcula todos os skills downstream do ponto de partida
- A revisão anterior é preservada com status `SUPERSEDED`; a nova inicia em `RASCUNHO`
- Overrides são registrados em `canonical.meta.replan_overrides[]` com `decided_by` e `justificativa`
- Limite de 5 revisões ativas por projeto (anti-thrashing de orçamentação; alinhado ao espírito de ADR-005 §D6)

**D1.2 — Skill `13-replan-advisor`**

Nova skill que executa após `06-consolidar` quando `resultado.status_margem` for `AMARELO` ou `VERMELHO`. Analisa o modelo canônico e produz sugestões concretas de parâmetros para `concilium replan`.

```toml
# skill.toml
[skill]
id = "13-replan-advisor"
version = "1.0.0"
descricao = "Analisa resultado AMARELO/VERMELHO e gera sugestões de replanejamento com impacto estimado de margem."

[depends_on]
skills = ["06-consolidar", "09-cost-criticality", "03C-validar-compartilhamento"]
canonical_sections = ["resultado", "cost_criticality_report", "conflitos_picos", "cronograma", "equipes_diretas"]

[produces]
canonical_section = "replan_suggestions"
validations = ["VAL-REPLAN-01", "VAL-REPLAN-02"]

[inputs]
required = []
optional = ["meta_margem_alvo"]

[trigger]
auto_run_when = "resultado.status_margem in ['AMARELO', 'VERMELHO']"
```

**Modelo de saída:**

```python
class ReplanSuggestion(BaseModel):
    id: str                          # "REPLAN-001"
    tipo: Literal["CRONOGRAMA", "EQUIPES", "RECURSOS", "ESCOPO", "BDI"]
    checkpoint_skill: str            # ponto de re-run recomendado
    parametros_sugeridos: dict       # overrides para concilium replan --set
    delta_margem_estimado: float     # variação percentual estimada
    confianca: Literal["ALTA", "MEDIA", "BAIXA"]
    justificativa: str
    restricoes: list[str]            # o que pode impedir a sugestão

class ReplanSuggestionsSection(BaseModel):
    status_gatilho: str              # "AMARELO" ou "VERMELHO"
    delta_margem_necessario: float   # quanto precisa recuperar
    suggestions: list[ReplanSuggestion]
    suggestion_prioritaria: str      # id da sugestão com maior delta/confiança
```

**Fonte das sugestões (lógica do advisor):**

| Condição detectada | Sugestão gerada |
|-------------------|-----------------|
| Itens `A+` em `cost_criticality` com equipes subdimensionadas | Aumentar `num_equipes` nos meses de pico |
| `conflitos_picos` com `SHIFT` viável | Re-run de `02-cronograma` redistribuindo atividades |
| `conflitos_picos` com `BUY` recomendado | Re-run de `01A-declarar-recursos` expandindo pool |
| Indiretos > 30% do custo total | Revisão de permanências (re-run de `05-indiretos`) |
| Praticabilidade < 70% em meses críticos | Revisão de cronograma evitando meses de baixa produtividade |

---

### D2 — Propagação de Custos de Aquisição de Recurso (03C → Orçamento)

**Alternativas consideradas:**

| Alternativa | Descrição | Problema |
|-------------|-----------|---------|
| A — Mover 03C antes de 04/05 | Reordena pipeline | 03C depende de 03B que depende de 03A; custo de BUY não é conhecido sem o orçamento (circular) |
| B — Nova skill 03D antes de 04/05 | 03D converte recomendações em custos; 04/05 consomem | Quebra paralelismo 04/05 com a cadeia 03A-03B-03C; alonga caminho crítico em ~3 níveis |
| C — 03B absorve custo de BUY | 03B calcula custo de aquisição quando recurso é insuficiente | Mistura lógica de alocação com lógica de custo em uma skill |
| D — Nova skill 06A-reconciliar | Após 06, aplica delta de BUY/HIRE sobre resultado | Preserva paralelismo; orçamento de 04/05 permanece inalterado; delta é explícito e auditável |

**Decisão: D — Skill `06A-reconciliar-custos-recurso`**

Introduz `06A` entre `06-consolidar` e `07-adapter-saida`. Não re-executa `04` nem `05`; aplica ajustes delta sobre o `resultado` de `06` com base nas recomendações de `03C`.

```
04-planejamento-bdi ─┐
05-indiretos ─────────┼→ 06-consolidar → 06A-reconciliar → 07-adapter-saida
03C-validar-compart. ─┘                       ↑
                                    (delta BUY/HIRE aplicado aqui)
```

```toml
# skill.toml
[skill]
id = "06A-reconciliar-custos-recurso"
version = "1.0.0"
descricao = "Aplica delta de custo de aquisição/contratação recomendados por 03C sobre o resultado de 06. Produz resultado_reconciliado."

[depends_on]
skills = ["06-consolidar", "03C-validar-compartilhamento"]
canonical_sections = ["resultado", "conflitos_picos"]

[produces]
canonical_section = "resultado_reconciliado"
validations = ["VAL-RECON-01", "VAL-RECON-02", "VAL-RECON-03"]

[inputs]
required = []
optional = []
```

**Modelo de saída:**

```python
class ItemCustoAquisicao(BaseModel):
    conflito_id: str
    tipo_recurso_id: str
    acao: Literal["BUY", "HIRE"]
    quantidade: float
    custo_unitario: float
    custo_total: float
    categoria_bdi: Literal["EQUIPAMENTO", "MAO_OBRA"]

class ResultadoReconciliado(BaseModel):
    resultado_base_id: str           # ref para canonical.resultado
    itens_aquisicao: list[ItemCustoAquisicao]
    delta_custo_total: float
    venda_total_com_bdi: float       # herdado de resultado, inalterado
    custo_total_reconciliado: float  # custo_base + delta_aquisicao
    margem_reconciliada_pct: float
    status_margem_reconciliado: Literal["VERDE", "AMARELO", "VERMELHO"]
    delta_status: str                # ex: "VERDE → AMARELO após BUY escavadeira"
```

**Validações:**

- `VAL-RECON-01`: Toda recomendação `BUY` ou `HIRE` de `03C` deve ter um `ItemCustoAquisicao` correspondente
- `VAL-RECON-02`: `custo_total_reconciliado >= custo_base` (delta sempre positivo ou zero)
- `VAL-RECON-03`: Se `status_margem_reconciliado != status_margem_base`, registrar `delta_status` com rastreio de causa

**Impacto no grafo:** `07-adapter-saida` e `11-decision-log` passam a depender de `06A` em vez de `06`. `06` continua existindo como resultado de planejamento puro; `06A` é o resultado definitivo incluindo custos de aquisição.

---

### D3 — Criticidade Operacional vs. Teórica

**Contexto:** `08-criticality` executa em L4 (paralelo a `03`), produzindo criticidade baseada em duração e DAG. As restrições de alocação de recurso (saída de `03B`) só ficam disponíveis em L6 — dois níveis depois.

**Alternativas consideradas:**

| Alternativa | Descrição | Custo |
|-------------|-----------|-------|
| A — Mover 08 após 03B | 08 sobe para L7; 09 para L8; 10 para L9 | Alonga análise financeira em 3 níveis |
| B — Split: 08 teórico + 08B operacional | 08 fica onde está; 08B executa após 03B | Nova skill; dois relatórios de criticidade |
| C — Anotar 03B com flag de criticidade de recurso; 09 combina ambos | 03B produz `criticidade_recurso` por atividade; 09 usa 08 + 03B | Sem nova skill; 09 já depende de resultado de 03 |

**Decisão: C — Anotação de criticidade de recurso em 03B, combinação em 09**

`03B-alocacao-recursos` passará a incluir, para cada atividade alocada, uma flag `criticidade_recurso`:

```python
class Alocacao(BaseModel):
    # campos existentes...
    criticidade_recurso: Literal["LIVRE", "CONSTRANGIDO", "CRITICO_RECURSO"]
    # LIVRE: recursos disponíveis com folga
    # CONSTRANGIDO: alocado sem margem; atraso = delay direto
    # CRITICO_RECURSO: insuficiente; requer BUY/HIRE ou SHIFT
```

`09-cost-criticality` já depende de `03-equipes-diretas` (e agora de `05-indiretos` pela correção deste sprint). Acrescenta dependência em `03B-alocacao-recursos` e combina as duas dimensões de criticidade:

```
score_final = α × criticidade_temporal  (de 08)
            + β × criticidade_recurso   (de 03B)
            + γ × cost_share            (de 04 + 05)
```

Os pesos α, β, γ são parametrizados via `perfil.pesos_analiticos` (já existente).

**Impacto no grafo:** `09-cost-criticality` adiciona `03B-alocacao-recursos` em `depends_on.skills` e `alocacoes` em `canonical_sections`. Nenhuma skill nova; nenhum nível adicionado ao caminho crítico.

---

### D4 — Gaps Identificados mas Fora do Escopo deste ADR

Os gaps abaixo foram registrados para rastreabilidade. Os ADRs efetivamente numerados 020–022 abordaram outras prioridades; os gaps abaixo permanecem abertos:

| Gap | Impacto | Estado |
|-----|---------|--------|
| Sem skill de contingência/risco | BDI absorve risco de forma opaca; incompatível com contratos DNIT/ANTT que exigem proviso explicity | **Aberto** — ADR-023 endereça parcialmente via campo `cr` (Contingência de Risco) em `ComponentesBdi` |
| MOB apenas como custo em `05` | Cronograma de mobilização afeta caminho crítico em obras de grande porte | **Aberto** |
| Sem modelagem de variações de escopo | Change orders forçam re-run completo a partir de `00-escopo` | **Aberto** |

---

## Impacto no Grafo de Dependências

**Antes (com as correções do sprint anterior):**
```
... → 06-consolidar → 07-adapter-saida
      06-consolidar → 11-decision-log → 12-decision-review
```

**Depois (com este ADR):**
```
... → 06-consolidar ─┐
03C-validar-compart. ─┴→ 06A-reconciliar → 07-adapter-saida
                                         → 11-decision-log → 12-decision-review
                                         → 13-replan-advisor  (se AMARELO/VERMELHO)
```

**Novos níveis:**

| Skill | Nível anterior | Nível novo |
|-------|---------------|------------|
| 06A-reconciliar-custos-recurso | — (nova) | L7 |
| 07-adapter-saida | L7 | L8 |
| 11-decision-log | L8 | L8 |
| 13-replan-advisor | — (nova) | L8 |
| 12-decision-review | L9 | L9 |

O caminho crítico (`00→00A→00B→02→03→04→06→06A→11→12`) aumenta em 1 aresta (06A). O custo é mínimo — 06A é uma operação de ajuste delta, não um recálculo completo.

---

## Validações

| Código | Regra |
|--------|-------|
| VAL-REPLAN-01 | `replan_suggestions` deve conter ao menos 1 sugestão quando `status_margem` for `VERMELHO` |
| VAL-REPLAN-02 | Toda sugestão deve referenciar um `checkpoint_skill` com `replan_checkpoint.enabled = true` |
| VAL-RECON-01 | Toda recomendação `BUY`/`HIRE` de `03C` deve gerar `ItemCustoAquisicao` em `06A` |
| VAL-RECON-02 | `custo_total_reconciliado >= resultado.custo.total` |
| VAL-RECON-03 | Se `status_margem_reconciliado != resultado.status_margem`, `delta_status` deve estar preenchido |

---

## ADRs Relacionados

- **ADR-005** — Replanning Strategy: cobre replanning durante *execução* (Tiers 1/2/3). Este ADR cobre replanning durante *orçamentação*.
- **ADR-006** — Team Composition: base do dimensionamento de equipes que `13-replan-advisor` analisa.
- **ADR-009** — Indirect Costs as First Class: `06A` não altera a lógica de `05`; respeita a separação de indiretos.
- **ADR-010** — Activity Cost Breakdown and Resource Allocation: origem de `03B`; `06A` consome sua saída indiretamente via `03C`.
- **ADR-016** — Resource Sharing Taxonomy: define os tipos de recomendação (BUY/SHIFT/HIRE) que `06A` e `13` consomem.
- **ADR-018** — Typed Artifact System: `resultado_reconciliado` e `replan_suggestions` devem ser envelopados como `ArtifactKind.RESULTADO` e `ArtifactKind.PROPOSTA` respectivamente.

---

## Definition of Done

- [x] `06A-reconciliar-custos-recurso`: `skill.toml`, `skill.py`, `SKILL.md`, `__init__.py`
- [x] `13-replan-advisor`: `skill.toml`, `skill.py`, `SKILL.md`, `__init__.py`
- [x] `03B-alocacao-recursos`: campo `criticidade_recurso` adicionado ao modelo `Alocacao`
- [x] `09-cost-criticality`: `depends_on` atualizado com `03B-alocacao-recursos`; lógica de score combinado implementada
- [x] `07-adapter-saida`, `11-decision-log`: `depends_on` migrado de `06` para `06A`
- [x] CLI `concilium replan` implementado com `--from`, `--set`, `--justificativa`
- [x] `skill.toml` de skills válidos como checkpoint marcados com `[replan_checkpoint] enabled = true` (01A, 02, 03, 06A, 13)
- [ ] Testes: `test_06A_buy_delta_applied`, `test_06A_no_conflicts_passthrough`, `test_13_suggests_replan_on_vermelho`, `test_13_no_suggestion_on_verde`, `test_replan_cli_creates_new_revision`, `test_replan_preserves_prior_revision`
- [ ] Amostra `data/samples/04-terraplenagem-replan-vermelho.json` validando o fluxo completo com `13-replan-advisor` ativo
