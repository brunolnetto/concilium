# ADR-026 — Fase Saída Multi-Canal: Relatórios Analíticos como Artefatos de Primeira Classe

**Status:** Implementado  
**Data:** 2026-05-04  
**Data Implementado:** 2026-05-04  
**Implementadores:** models/artifact.py (ArtifactKind + 3 relatórios), models/reports.py (RelatorioCriticidade, RelatorioSensibilidade, RelatorioIntervencao), skills/base.py (SkillResult.artifacts), skills/15-relatorio-criticidade, 16-relatorio-sensibilidade, 17-relatorio-intervencao, adapters/excel_legacy_sheets.py (coluna Criticidade — §D5), skills/07-adapter-saida/skill.py (enriquecimento criticidade — §D5)  
**Contexto:** MendesLobo Construtora — Concilium

---

## Contexto

### Problema

A Fase Saída do pipeline possui hoje uma única skill: `07-adapter-saida`, que produz a planilha de planejamento (`RELATORIO`). As fases de Análise (08, 09) e Decisão (10, 13, 14, 11) produzem dados ricos — classificação de criticidade, caminhos de repair, espaço de intervenção, log de decisões — mas esses dados **não materializam em artefatos entregáveis independentes**.

Consequências:
1. O engenheiro consome dados analíticos apenas através do canônico em memória — sem persistência rastreável como `ArtifactEnvelope`.
2. `07-adapter-saida` executa em **Wave 6**, antes de `09-cost-criticality` (Wave 7) e `10-intervention-roi` (Wave 7). A planilha de planejamento **não embute criticidade** mesmo quando o dado existe.
3. Não há artefatos de relatório para os outputs de `13-replan-advisor` (sensibilidade) e `14-plan-space-explorer` (intervenção), impossibilitando trilha de auditoria ou comparação entre versões de planejamento.

### Dependências atuais incorretas

```
# Hoje (ADR-022 Wave 6):
Wave 6:  03C, 06A-reconciliar-custos-recurso, 07-adapter-saida, 08-criticality
Wave 7:  09-cost-criticality, 10-intervention-roi

# 07 executa ANTES de 09 → planilha não tem criticidade
# 13 e 14 não têm skills de saída → análise é efêmera
```

---

## Decisões

### D1 — Duas Sub-camadas dentro de Saída

A Fase Saída passa a ter duas sub-camadas com dependências explícitas:

| Sub-camada | Upstream | Skills |
|---|---|---|
| **Saída-Base** | Consolidação + Análise (09) | `07-adapter-saida` (planilha) |
| **Saída-Analítica** | Análise (09) + Decisão (11, 13, 14) | `15-relatorio-criticidade`, `16-relatorio-sensibilidade`, `17-relatorio-intervencao` |

Regra de dependência:
- `07` passa a depender de `09-cost-criticality` (adiciona coluna de criticidade à planilha)
- `15` depende de `09-cost-criticality` + `11-decision-log`
- `16` depende de `13-replan-advisor`
- `17` depende de `14-plan-space-explorer`

### D2 — Wave Topology Atualizada (estende ADR-022)

```
Wave 0:   00-escopo
Wave 1:   00A, 00B, 01-praticabilidade
Wave 2:   01A, 02-cronograma
Wave 3:   03-equipes-diretas, 04-planejamento-bdi
Wave 4:   03A-derivar-requisitos, 05-indiretos
Wave 5:   03B-alocacao-recursos, 06-consolidar
Wave 6:   03C, 06A-reconciliar-custos-recurso, 08-criticality  ← 07 removido daqui
Wave 7:   09-cost-criticality, 10-intervention-roi
Wave 8:   07-adapter-saida [movido], 13-replan-advisor
Wave 9:   14-plan-space-explorer, 11-decision-log
Wave 10:  15-relatorio-criticidade, 16-relatorio-sensibilidade, 17-relatorio-intervencao
```

`07` permanece **ADVISORY** (não bloqueia 15–17). As três novas skills são **ADVISORY**.

### D3 — Três Novos `ArtifactKind`

```python
class ArtifactKind(str, Enum):
    # ... existentes ...
    RELATORIO_CRITICIDADE   = "relatorio_criticidade"   # Skill 15
    RELATORIO_SENSIBILIDADE = "relatorio_sensibilidade" # Skill 16
    RELATORIO_INTERVENCAO   = "relatorio_intervencao"   # Skill 17
```

Cada relatório é um `ArtifactEnvelope[T]` imutável, versionado, com `catalog_snapshot_id` e `bdi_perfil_id` herdados de `ArtifactMeta` (ADR-024, ADR-023 §D6).

### D4 — Payloads dos Novos Relatórios

#### `RelatorioCriticidade` (Skill 15)

Produz o ranking Pareto de atividades e as decisões de engenharia associadas.

```python
class ItemCriticidadeRelatorio(BaseModel):
    atividade_id:    str
    descricao:       str
    classificacao:   Literal["A+", "A", "B", "C"]   # de CriticidadeProfile (ADR-020)
    pareto_frontier: bool
    custo_share:     float
    duracao_share:   float
    sensibilidade:   float
    recurso_status:  Literal["CONSTRANGIDO", "LIVRE"]
    decisoes_vinculadas: list[str]  # IDs de DecisionLogEntry do 11

class RelatorioCriticidade(BaseModel):
    projeto_id:     str
    versao:         str
    gerado_em:      datetime
    skill_source:   Literal["09-cost-criticality", "11-decision-log"]
    itens:          list[ItemCriticidadeRelatorio]
    total_atividades:   int
    total_A_mais:       int   # count A+
    total_A:            int
    total_B:            int
    total_C:            int
    custo_A_mais_pct:   float  # soma de custo_share dos A+
    notas_engenheiro:   str | None  # do 11-decision-log geral
```

#### `RelatorioSensibilidade` (Skill 16)

Materializa os resultados de `13-replan-advisor`: quais levers movem a margem e quanto.

```python
class ItemSensibilidade(BaseModel):
    lever_tipo:            str   # EXPAND_POOL | REDUCE_DURATION | ADD_TEAMS | REVIEW_BDI
    lever_checkpoint:      str   # skill que implementa o lever
    delta_margem:          float
    custo_aplicacao:       float | None
    ratio_beneficio:       float  # delta_margem / custo_aplicacao_normalizado
    confianca:             Literal["ALTA", "MEDIA", "BAIXA"]
    atividades_afetadas:   list[str]

class RelatorioSensibilidade(BaseModel):
    projeto_id:      str
    versao:          str
    gerado_em:       datetime
    status_margem:   Literal["VERDE", "AMARELO", "VERMELHO"]
    margem_entrada:  float
    margem_alvo_min: float
    repair_viavel:   bool
    passos_repair:   list[ItemSensibilidade]   # RepairPath.steps traduzidos
    oportunidades:   list[ItemSensibilidade]   # OportunidadeVerde para planos VERDE
    margem_pos_repair: float | None
```

#### `RelatorioIntervencao` (Skill 17)

Materializa os resultados de `14-plan-space-explorer`: caminhos combinados de intervenção.

```python
class EixoIntervencao(BaseModel):
    nome:            str  # ex: "Custo vs Prazo"
    margem_estimada: float
    prazo_delta_dias: int | None
    confianca:        Literal["ALTA", "MEDIA", "BAIXA"]
    risco:            Literal["BAIXO", "MEDIO", "ALTO"]
    levers_combinados: list[str]  # tipos aplicados em conjunto

class RelatorioIntervencao(BaseModel):
    projeto_id:           str
    versao:               str
    gerado_em:            datetime
    status_entrada:       Literal["VERDE", "AMARELO", "VERMELHO"]
    eixos_intervencao:    list[EixoIntervencao]
    fronteira_pareto:     list[EixoIntervencao]  # subconjunto não dominado
    recomendacao_primaria: EixoIntervencao | None  # melhor trade-off
```

### D5 — `07-adapter-saida`: Enriquecimento com Criticidade

Ao mover para Wave 8, `07-adapter-saida` passa a ter acesso ao resultado de `09-cost-criticality`. O adaptador deve:
1. Ler `canonical.criticidade` (lista de `CriticidadeProfile` por atividade)
2. Adicionar coluna **Criticidade** (`A+`/`A`/`B`/`C`) na aba `PLANEJAMENTO` da planilha `.xlsm`
3. Colorir linhas: `A+` → vermelho, `A` → laranja, `B` → amarelo, `C` → sem cor
4. Manter comportamento atual se `canonical.criticidade` estiver vazio (09 falhou) — coluna ausente, sem bloqueio

Este enriquecimento é **não-bloqueante**: se 09 estiver em `pipeline_blocked_from`, 07 executa sem a coluna de criticidade.

### D6 — `phase_classifier.py`: Atualização de `PHASE_MAP`

```python
PHASE_MAP = {
    ...
    # Camada 5 — Renderiza o plano final para stakeholders
    "Saída": [
        "07-adapter-saida",          # planilha de planejamento (Saída-Base)
        "15-relatorio-criticidade",  # relatório analítico (Saída-Analítica)
        "16-relatorio-sensibilidade",
        "17-relatorio-intervencao",
    ],
}
```

---

## Alternativas Consideradas

| Alternativa | Razão para Rejeição |
|---|---|
| Embutir todos os relatórios em 07-adapter-saida (aba extra) | Viola SRP; 07 dependeria de todas as fases, aumentando chance de bloqueio por falha em 13 ou 14 |
| Uma única skill `15-relatorios-analiticos` que produz os 3 relatórios | Impede execução independente; se 13 falha, 17 seria desnecessariamente bloqueado |
| Manter 07 na Wave 6 sem criticidade | Planilha entregável sem dado de criticidade já disponível — degradação silenciosa da qualidade |
| Relatórios apenas como campos no canônico (sem ArtifactEnvelope) | Sem versionamento, sem trilha de auditoria, sem comparação entre versões de planejamento |

---

## Consequências

### Positivas
- **Rastreabilidade completa**: cada relatório é um artefato com `artifact_id`, `version`, `catalog_snapshot_id` — comparável entre re-planejamentos
- **Planilha enriquecida**: engenheiro visualiza criticidade diretamente na planilha de licitação
- **Separação clara de responsabilidade**: 07 = consolidação financeira, 15 = criticidade, 16 = sensibilidade, 17 = intervenção
- **Falhas isoladas**: se `13-replan-advisor` falha, `17-relatorio-intervencao` é ADVISORY-DEGRADADO; `16-relatorio-sensibilidade` também — `07` e `15` não são afetados

### Negativas / Riscos
- **Latência de pipeline aumenta**: `07` agora executa após Wave 8 (era Wave 6) — o tempo até a planilha aumenta pelo tempo de 08, 09, 10, 13 precedentes
  - Mitigação: 08–10 são rápidos (sem I/O externo); 13 opera sobre canônico em memória
- **Dependência nova em 07**: se 09 falha por GATE bloqueado, 07 executa sem criticidade — comportamento degradado esperado e não-bloqueante
- **Três novos skills a implementar**: 15, 16, 17 precisam de scaffolding (skill.toml, skill.py, modelos)

---

## Definition of Done

- [ ] `models/artifact.py` — adicionar `RELATORIO_CRITICIDADE`, `RELATORIO_SENSIBILIDADE`, `RELATORIO_INTERVENCAO` a `ArtifactKind`
- [ ] `models/reports.py` — definir `RelatorioCriticidade`, `RelatorioSensibilidade`, `RelatorioIntervencao`, `ItemCriticidadeRelatorio`, `ItemSensibilidade`, `EixoIntervencao`
- [ ] `skills/phase_classifier.py` — adicionar 15, 16, 17 à fase `"Saída"`
- [ ] `mcp_server/_context.py` — atualizar `_GATE_PREDECESSORS`:
  - `07`: adicionar `"09-cost-criticality"` aos predecessores
  - `15`: `["09-cost-criticality", "11-decision-log"]`
  - `16`: `["13-replan-advisor"]`
  - `17`: `["14-plan-space-explorer"]`
- [ ] `skills/07-adapter-saida/skill.py` — ler `canonical.criticidade`; adicionar coluna à aba PLANEJAMENTO com coloração condicional; degradação silenciosa se ausente
- [ ] `skills/15-relatorio-criticidade/skill.py` + `skill.toml` — `gate = false`; lê de `canonical.criticidade` + `canonical.decision_log`; emite `ArtifactEnvelope[RelatorioCriticidade]`
- [ ] `skills/16-relatorio-sensibilidade/skill.py` + `skill.toml` — `gate = false`; lê de `canonical.replan_result`; emite `ArtifactEnvelope[RelatorioSensibilidade]`
- [ ] `skills/17-relatorio-intervencao/skill.py` + `skill.toml` — `gate = false`; lê de `canonical.plan_space_result`; emite `ArtifactEnvelope[RelatorioIntervencao]`
- [ ] `concilium/diagram.md` — atualizar diagrama Mermaid com waves 8–10 e novas skills
- [ ] Testes: `test_07_embeds_criticidade`, `test_07_degrades_without_criticidade`, `test_15_criticidade_artifact_schema`, `test_16_sensibilidade_artifact_schema`, `test_17_intervencao_artifact_schema`, `test_15_degrades_without_decision_log`

---

## Referências

- **ADR-018:** Typed Artifact System — `ArtifactKind`, `ArtifactEnvelope`, `ArtifactMeta`
- **ADR-020:** Criticidade Multi-Dimensional — `CriticidadeProfile`, `DimensaoCriticidade`
- **ADR-021:** Plan Space Explorer — `RepairPath`, `Lever`, `OportunidadeVerde`
- **ADR-022:** Wave Execution e Gate Blocking — `_GATE_PREDECESSORS`, wave topology
- **ADR-023 §D6:** `bdi_perfil_id` em `ArtifactMeta`
- **ADR-024 §D3:** `catalog_snapshot_id` em `ArtifactMeta`
- **`skills/phase_classifier.py`:** `PHASE_MAP` — fonte de verdade das fases
- **`skills/07-adapter-saida/`:** adaptador Excel atual
- **`skills/11-decision-log/`:** captura HiL de decisões de engenharia
