# ADR-070: Exploração Determinística do Espaço de Configuração Operacional para Viabilidade de GO

**Status:** ⚠️ Parcialmente Implementado — núcleo entregue via ADR-108/109 _(reclassificado 2026-06-19)_  
**Data original:** 2026-05-23  
**Reavaliação:** 2026-06-11 — correção de status + mapeamento ao estado atual + path revisado  
**Relacionado:** ADR-004, ADR-005, ADR-006, ADR-020, ADR-021, ADR-022, ADR-051, ADR-060, ADR-061, ADR-108, ADR-109, ADR-113, NEP-042, NEP-043

---

## Reclassificação 2026-06-19 (backlog cleanup)

Não é "bug abandonado" — é feature cujo **núcleo foi entregue depois** por outros ADRs:

| Componente ADR-070 | Entregue por | Estado |
|---|---|---|
| `GoResearchCampaignBundle` (contrato tipado) | ADR-108/109 | ✅ `domain/models/campaign/campaign.py` |
| Sweep paramétrico (produto cartesiano) | ADR-109 | ✅ cardinalidade + discretizações |
| Modo de execução leve para exploração | ADR-113 | ✅ `PipelineMode.OLTP` (campanha não gera artefatos) |
| Curadoria Pareto formal (F3) | — | 🔴 deferido — ranking heurístico atual é suficiente para uso real |
| Separação formal espaços O × EF/F (D8) | — | 🔴 deferido |

**Decisão:** O valor central do ADR-070 (exploração paramétrica de campanha) está
operacional. As partes não entregues (Pareto bi-espaço) são refinamento sem demanda
concreta. Mantido como ⚠️ Parcial; **sem trabalho ativo planejado** até surgir caso de uso.

---

## Reavaliação 2026-06-11

### Por que o status "Implementado" estava incorreto

A auditoria de 2026-06-09 identificou `plan_space` e `replan_suggestions` no código e inferiu implementação. Na prática:

| Conceito ADR-070 | O que o audit encontrou | O que realmente é |
|---|---|---|
| `GoResearchCampaignBundle` | `plan_space` CLI de benchmark | CLI para comparar alternativas manuais de benchmark — não é busca paramétrica sistemática |
| Motor de exploração (F2) | `simular_cenario_replan` | Estimativa linear sem re-execução do pipeline |
| Curadoria Pareto (F3) | `replan_suggestions` | Ranking heurístico por `delta_margem_estimado` — sem fronteira de Pareto nos dois espaços |
| Avaliação O + EF/F (D8) | — | Não existe separação formal dos dois espaços |

**Status correto: ⚠️ Parcialmente Implementado** — os esboços de F2 e F3 existem, mas sem o contrato tipado do bundle, sem sweep paramétrico e sem curadoria Pareto.

### O que mudou desde 2026-05-23 que torna o ADR mais factível

**Mudanças que habilitam a implementação:**

| Mudança | Relevância para ADR-070 |
|---|---|
| **NEP-043 — C_r reconciliado** | Comparações entre cenários agora são significativas: pool cost / PU_cat ≈ 0.90 (era 0.45, não representativo) |
| **ADR-091 — makespan fix (n_max)** | O-space tem `prazo` correto: 42 semanas em vez de 67 infladas |
| **NEP-042 — três camadas de custo** | EF/F-space tem `{PU_cat, PU_op_pool, C_permanência}` separados e auditáveis |
| **ProjetoSpec completo (v2.0)** | Os "parâmetros de baixo risco" de D2 são exatamente campos do spec: `n_max`, `leadtime_mob_semanas`, `lag_demob_semanas`, `restricoes_mercado` |
| **`plan_space` CLI paralelo** | Infra de avaliação paralela de alternativas já existe — pode ser reutilizada |
| **ADR-106 F5 — mob_window** | Custo de mobilização por janela agora é computável — entra no O-space como `custo_mob_window` |

**Consequência:** antes dessas mudanças, uma exploração produziria cenários com métricas sistematicamente erradas. Agora a infra subjacente é confiável.

---

## 1. Contexto (original — preservado)

A operação precisa encontrar configurações viáveis de GO a partir de um baseline técnico consistente. O sistema hoje executa planejamento e classificação com qualidade de benchmark, mas não possui um mecanismo canônico para explorar sistematicamente variações controladas.

---

## 2. Problema (original — preservado)

P1–P6 permanecem válidos. Adições pós-reavaliação:

**P7 — Estimativa linear é insuficiente para senários de composição**  
O `simular_cenario_replan` retorna `fe_nec_novo = fe_nec / prod_factor` — válido para lever_adjust simples, mas não captura efeitos não-lineares de mudança de `n_max` (interação com RCPSP, gaps de idle, custo de mob_window).

**P8 — Plan_space CLI é centrado em benchmark, não em projeto**  
O comando `concilium benchmark plan-space` opera sobre alternativas de `referencia.json` de benchmark — sem bundle de campanha versionado, sem sweep paramétrico, sem Pareto.

---

## 3. Decisão (atualizada)

### D1–D8 originais: mantidos

### D2b — Inventário de Levers de Exploração (elaboração de D2)

Os levers são os parâmetros variados em cada cenário da campanha. Estão todos disponíveis no `ProjetoSpec` (schema v2.0) e classificados por risco semântico e espaço de impacto.

#### Classe 1 — Levers de Frota (risco baixo, impacto O-space)

| Lever | Campo no spec | Range sugerido | Impacto |
|---|---|---|---|
| **Tamanho máximo de equipe** | `cronograma[i].n_equipes.n_max` | `[1, n_max_cat]` (inteiros) | Prazo, custo_mob_window, pool |
| **Frentes na mobilização** | `cronograma[i].n_equipes.n_inicial` | `[1, n_max]` (inteiros) | Custo de ramp, prazo |
| **Janela de mobilização** | `cronograma[i].leadtime_mob_semanas` | `[1, 4]` semanas | custo_mob_window, prazo |
| **Lag de desmobilização** | `cronograma[i].lag_demob_semanas` | `[0, 2]` semanas | custo_mob_window |

Constraint automático: `n_inicial ≤ n_max`. Variação de `n_max` → re-execução do RCPSP (ADR-091 garante uso como pool irrestrito).

#### Classe 2 — Levers de Produtividade (risco médio, impacto O + EF)

| Lever | Campo no spec | Range sugerido | Impacto |
|---|---|---|---|
| **Override de produtividade** | `cronograma[i].producao_diaria` | `[0.8×P_cat, 1.2×P_cat]` | Prazo, custo_direto |
| **Horas por dia** | `meta.regime_trabalho.horas_dia` | `{6, 8, 9, 10}` | Prazo, `C_r^{sem}`, custo |
| **Dias por semana** | `meta.regime_trabalho.dias_semana` | `{5, 6, 7}` | Prazo, `C_r^{sem}`, custo |

Nota: `horas_dia × dias_semana` afeta `C_r^{sem}` (custo semanal de todos os recursos) e `horas_semana` (produção por semana). Um cenário com 6d×10h tem o mesmo custo por semana que 6d×8h escalado por 10/8 — mas o prazo cai mais rápido que o custo sobe.

#### Classe 3 — Levers de Estratégia de Pool (risco baixo, impacto O + EF)

| Lever | Campo no spec | Valores | Impacto |
|---|---|---|---|
| **Objetivo do pool** | `meta.objetivo_pool` | `{balanceado, minimizar_prazo, minimizar_custo}` | Prazo vs custo direto |
| **Restrições de mercado** | `restricoes_mercado` | `{tipo: [1,2,3]}` | Prazo se vinculante |

`objetivo_pool = minimizar_prazo` aumenta o pool ao pico de demanda concorrente; `minimizar_custo` usa o mínimo serial. Diferença de makespan pode ser significativa em obras com atividades concorrentes.

#### Classe 4 — Levers de Composição de CPU (risco médio, requer catálogo — D3/F4)

| Lever | Mecanismo | Valores | Impacto |
|---|---|---|---|
| **CPU alternativo por item** | `eap[i].cpu_id` substituto | CPUs do mesmo tipo de serviço | PU_cat, produtividade, custo de equipe |

Exemplo: escavação 2ª cat. → `CPU-TERRA-ESCO-CARGA-2CAT-DMT2000` vs `CPU-TERRA-ESCO-CARGA-2CAT-DMT3000`. O CPU com DMT menor tem custo menor mas demanda mais equipamento de transporte. Impacto em O e EF/F simultaneamente.

Requer catálogo de CPUs substitutos por tipo de serviço (F4 — não implementado).

#### Classe 5 — Levers Financeiros (risco alto, decisão humana — não sweepear automaticamente)

| Lever | Campo | Por que não sweepear |
|---|---|---|
| `bdi_lucro.*` | `meta.bdi_lucro` | É objetivo de negócio, não variável operacional |
| `regime_tributario.iss` | `meta.regime_tributario.iss` | Determinado pela jurisdição, não pela obra |
| `regime_tributario.regime` | `meta.regime_tributario.regime` | Decisão jurídico-contábil |

Estes parâmetros podem compor um `perfil_expectativas` da campanha (quanto lucro é esperado), mas não devem ser variados no sweep — eles definem o contexto dentro do qual o sweep opera.

#### Resumo: prioridade de implementação

```
Campanha v1 (F1–F3):
  Classe 1 (frota): n_max, n_inicial, leadtime, lag
  Classe 3 (pool):  objetivo_pool, restricoes_mercado

Campanha v2 (F4):
  Classe 2 (produtividade): horas_dia, dias_semana, producao_diaria
  Classe 4 (CPU alternativo): cpu_id por item — requer catálogo enriquecido
```

### D9 — Ancorar a campanha no ProjetoSpec (novo)

`GoResearchCampaignBundle` não inventa contratos próprios. Uma campanha é:

```
GoResearchCampaignBundle = {
    base_spec: ProjetoSpec,          ← spec canônico da obra
    sweep: [ParametroSweep],         ← quais campos variam e em que range
    constraints: [Constraint],       ← restrições duras
    espaco_O: MetricaODef,           ← quais campos do canonical medem O-space
    espaco_EF: MetricaEFDef,         ← quais campos medem EF/F-space
    perfil_expectativas: dict,       ← faixas alvo por métrica EF/F
    politica_curadoria: CuradoriaConfig,
    top_k: int,
    campaign_version: str
}
```

Os "parâmetros controláveis de baixo risco" (D2) já estão no `ProjetoSpec`:

| D2 original | Campo no ProjetoSpec |
|---|---|
| `ramp_up_rate` | `escopos[].cronograma[].n_equipes.n_inicial / n_max` |
| `ramp_down_rate` | `escopos[].cronograma[].lag_demob_semanas` |
| `team_max_count` | `escopos[].cronograma[].n_equipes.n_max` |
| `productivity_boost_pct` | `escopos[].cronograma[].producao_diaria` (override) |
| Restrição de mercado | `restricoes_mercado: {tipo: N_max}` |

### D10 — Definir os vetores de espaço O e EF/F com campos canônicos (novo)

**Espaço O** — métricas operacionais do canonical após pipeline completo:

```
I_O(x) = {
    prazo_semanas:        cronograma.makespan_semanas,
    fe_nec_medio:         mean(ponto_equilibrio[].frentes_equivalentes_necessarias),
    gap_pool_total:       sum(ponto_equilibrio[].gap_pool_overhead),
    custo_mob_window_total: sum(equipes_diretas[].custo_inst_mob_demob),
    itens_criticos_pct:   count(pe.status_frentes=='CRITICO') / N_itens
}
```

**Espaço EF/F** — métricas econômico-financeiras:

```
I_EF(x) = {
    margem_pct:            resultado.margem_pct,
    custo_execucao_pool:   resultado.custo.direto_equipes,
    custo_indireto:        sum(resultado.custo.indireto_*),
    preco_venda:           resultado.venda.total_com_bdi,
    delta_custo_direto_pct: (custo_execucao_pool - PU_cat_Q) / PU_cat_Q,
    fidelidade_gates:      quality_gates.decision in {APROVADO, APROVADO_COM_RESSALVAS}
}
```

---

## 4. Mapeamento ao Estado Atual

### O que já existe como fundação

| Componente ADR-070 | Implementado onde | Maturidade |
|---|---|---|
| Estimativa linear de lever | `_simular_lever_adjust()` em `replan.py` | ✅ Funcional (F2 simplificado) |
| Ranking heurístico de sugestões | `replan_suggestions` via skill-13 assessor | ✅ Funcional (F3 simplificado) |
| Oportunidades identificadas | `plan_space_result.oportunidades` via skill-13 explorador | ✅ Funcional |
| Avaliação paralela de alternativas | CLI `benchmark plan-space` | ✅ Funcional (mas não paramétrico) |
| Vetor O-space | `ponto_equilibrio[]` + `cronograma.makespan_semanas` | ✅ Dados disponíveis |
| Vetor EF/F-space | `resultado.custo/venda` + `quality_gates` | ✅ Dados corretos pós-NEP-043 |
| Semáforo de viabilidade | `quality_gates.decision` | ✅ Reutilizável conforme D4 |
| Visualização de espaço | `_chart_plan_space` | ✅ Existe |

### O que não existe

| Componente ADR-070 | Status |
|---|---|
| `GoResearchCampaignBundle` tipado | ❌ Não existe |
| Sweep paramétrico de `ProjetoSpec` | ❌ Não existe — apenas alternativas manuais no CLI |
| Pareto O-space × EF/F-space | ❌ Não existe — apenas ranking heurístico por `delta_margem` |
| Templates de equipe (D3/F4) | ❌ Não existe — composições do catálogo usam `composicao_padrao_equipe` como template único |
| Persistência de campanha versionada | ❌ Não existe |
| API de exploração (F5) | ❌ Não existe — apenas CLI |

---

## 4b. CampaignOutputBundle — Contrato de Saída e Critérios de Classificação

### 4b.1 Estrutura geral

```
CampaignOutputBundle
├── campaign_id: str
├── campaign_version: str
├── base_spec_hash: str               ← hash do ProjetoSpec base
├── gerado_em: datetime
├── n_cenarios_avaliados: int
├── n_cenarios_viaveis: int
├── n_falhas: int
├── status: CampaignStatus            ← classificação do bundle inteiro
├── cenarios: list[CenarioAvaliado]   ← todos os cenários com vetores e classificações
├── shortlist: list[CenarioRankeado]  ← top_k curados com justificativa
├── summary_O: SummaryEspacoO         ← fronteira Pareto O + estatísticas
├── summary_EF: SummaryEspacoEF       ← fronteira Pareto EF/F + estatísticas
└── trilha_auditoria: AuditTrail
```

### 4b.2 CenarioAvaliado — estrutura por cenário

```
CenarioAvaliado
├── cenario_id: str                   ← hash determinístico dos parâmetros variados
├── parametros_variados: dict         ← apenas os campos que divergem do base_spec
├── viabilidade: ViabilidadeStatus    ← APROVADO / APROVADO_COM_RESSALVAS /
│                                        BLOQUEADO_COM_INVESTIGACAO / BLOQUEADO
│
├── vetor_O: VetorEspacoO
│   ├── prazo_semanas: int            ← cronograma.makespan_semanas
│   ├── folga_semanas: float          ← prazo_contratual - prazo_semanas (+ = no prazo)
│   ├── fe_nec_medio: float           ← mean(ponto_equilibrio[].frentes_equivalentes_necessarias)
│   ├── itens_criticos_pct: float     ← count(fe_nec > 1.25) / N_itens
│   ├── gap_pool_total: float         ← sum(ponto_equilibrio[].gap_pool_overhead)
│   └── custo_mob_window_total: float ← sum(equipes_diretas[].custo_inst_mob_demob)
│
├── vetor_EF: VetorEspacoEF
│   ├── margem_pct: float             ← resultado.margem_pct
│   ├── custo_execucao_pool: float    ← resultado.custo.direto_equipes
│   ├── custo_indireto: float         ← Σ resultado.custo.indireto_*
│   ├── preco_venda: float            ← resultado.venda.total_com_bdi
│   ├── ratio_pool_vs_cat: float      ← custo_execucao_pool / PU_cat_Q  (< 1.0 = bom)
│   └── fidelidade_gates: bool        ← quality_gates.decision ∈ {APROVADO, APROVADO_COM_RESSALVAS}
│
├── classificacao_O: ClassificacaoO   ← por dimensão: IDEAL / ATENCAO / CRITICO
├── classificacao_EF: ClassificacaoEF ← por métrica: DENTRO / ATENCAO / FORA
│
├── pareto_O: bool                    ← está na fronteira de Pareto do espaço O?
├── pareto_EF: bool                   ← está na fronteira de Pareto do espaço EF/F?
├── pareto_intersecao: bool           ← está em AMBAS as fronteiras?
└── rank_final: int | None            ← posição no shortlist (None se não curado)
```

### 4b.3 Critérios de Classificação no Espaço O

Cada dimensão recebe `IDEAL | ATENCAO | CRITICO`:

| Dimensão | IDEAL | ATENCAO | CRITICO |
|---|---|---|---|
| `folga_semanas` | ≥ 0 (no prazo ou adiantado) | −2 ≤ folga < 0 | < −2 semanas |
| `fe_nec_medio` | ≤ 1.0 (pool cobre sem esforço) | 1.0 < fe_nec ≤ 1.25 | > 1.25 |
| `itens_criticos_pct` | 0% | 0% < pct ≤ 20% | > 20% |
| `gap_pool_total` | ≤ 0 (pool eficiente) | > 0 e ≤ 5% custo_direto | > 5% custo_direto |
| `custo_mob_window_total` | ≤ 2% custo_direto | 2–5% custo_direto | > 5% custo_direto |

**Classificação O do cenário** = pior dimensão individual:
- Se qualquer dimensão é CRITICO → classificacao_O = CRITICO
- Se alguma é ATENCAO e nenhuma é CRITICO → classificacao_O = ATENCAO
- Todas IDEAL → classificacao_O = IDEAL

### 4b.4 Critérios de Classificação no Espaço EF/F

Cada métrica recebe `DENTRO_EXPECTATIVA | ATENCAO | FORA_EXPECTATIVA`, parametrizado pelo `perfil_expectativas` da campanha:

| Métrica | DENTRO_EXPECTATIVA | ATENCAO | FORA_EXPECTATIVA |
|---|---|---|---|
| `margem_pct` | ≥ meta_margem | meta_margem − tolerancia ≤ margem < meta_margem | < meta_margem − tolerancia |
| `ratio_pool_vs_cat` | ≤ 1.0 (pool abaixo do mercado) | 1.0 < ratio ≤ 1.10 | > 1.10 (pool mais caro que mercado) |
| `fidelidade_gates` | True (APROVADO ou APROVADO_COM_RESSALVAS) | — | False (BLOQUEADO_*) |

Defaults do `perfil_expectativas` quando não especificados:
```
meta_margem = 0.10     (10%)
tolerancia  = 0.03     (3 p.p. — ATENCAO entre 7% e 10%)
```

**Classificação EF do cenário** = pior métrica individual (mesma lógica do O-space).

### 4b.5 Regra de Viabilidade do Cenário

```
viabilidade = quality_gates.decision (reutiliza semáforo oficial — D4)

Para Pareto e shortlist, apenas cenários com:
    viabilidade ∈ {APROVADO, APROVADO_COM_RESSALVAS}  →  "viável"
```

Um cenário com `classificacao_EF = FORA_EXPECTATIVA` pode ainda ser `viabilidade = APROVADO` — ele entra no Pareto mas não no shortlist recomendado.

### 4b.6 Fronteira de Pareto

**Pareto O** — minimizar `(prazo_semanas, fe_nec_medio, gap_pool_total)`:

> Cenário x domina y se: x ≤ y em todas as dimensões AND x < y em pelo menos uma.

Apenas cenários viáveis entram no Pareto O.

**Pareto EF** — maximizar `margem_pct`, minimizar `custo_indireto`:

> Cenário x domina y se: x ≥ y em margem AND x ≤ y em custo_indireto AND estrito em pelo menos um.

**Interseção Pareto** = `pareto_O ∩ pareto_EF` — candidatos preferenciais para o shortlist.

### 4b.7 Curadoria e Ranking do Shortlist

```python
def curar_shortlist(cenarios: list[CenarioAvaliado], top_k: int,
                    perfil: PerfilExpectativas) -> list[CenarioRankeado]:
    # 1. Filtro duro: viabilidade
    viaveis = [c for c in cenarios if c.viabilidade in {APROVADO, APROVADO_COM_RESSALVAS}]

    # 2. Pareto
    pareto_O  = calcular_pareto(viaveis, dims_minimizar=["prazo_semanas","fe_nec_medio","gap_pool_total"])
    pareto_EF = calcular_pareto(viaveis, dims_maximizar=["margem_pct"],
                                         dims_minimizar=["custo_indireto"])
    intersecao = [c for c in viaveis if c.pareto_O and c.pareto_EF]

    # 3. Pool de candidatos: interseção preferida; fallback para Pareto EF
    pool = intersecao if intersecao else [c for c in viaveis if c.pareto_EF]

    # 4. Tie-break determinístico estável (sem escalar único — D6)
    ranked = sorted(pool, key=lambda c: (
        c.classificacao_O != "IDEAL",          # IDEAL primeiro
        c.classificacao_EF != "DENTRO",        # DENTRO_EXPECTATIVA primeiro
        -c.vetor_EF.margem_pct,                # maior margem
         c.vetor_O.prazo_semanas,              # menor prazo
         c.vetor_O.fe_nec_medio,               # menor fe_nec
         c.cenario_id,                         # hash estável (reproducibilidade)
    ))
    return [CenarioRankeado(rank=i+1, cenario=c, justificativa=_build_justificativa(c))
            for i, c in enumerate(ranked[:top_k])]
```

### 4b.8 Status do Bundle (Classificação Agregada)

O status do `CampaignOutputBundle` classifica o resultado da campanha inteira:

| Status | Condição |
|---|---|
| `SUCESSO` | ≥ 1 cenário em `pareto_intersecao` com `viabilidade ∈ {APROVADO, APROVADO_COM_RESSALVAS}` |
| `SUCESSO_PARCIAL` | ≥ 1 cenário viável, mas nenhum em `pareto_intersecao` |
| `FRONTEIRA_UNICA` | ≥ 1 cenário em `pareto_O` ou `pareto_EF`, mas sem interseção — trade-off irreconciliável |
| `INFEASIBLE` | 0 cenários viáveis após avaliação completa |
| `INCONCLUSO` | ≥ 1 falha de avaliação E 0 cenários viáveis confirmados |
| `ABORTADO` | Todas as avaliações falharam |

**`FRONTEIRA_UNICA`** é um caso relevante: indica que maximizar margem e minimizar prazo são objetivos conflitantes no espaço explorado — o engenheiro precisa decidir explicitamente qual dimensão priorizar. O bundle apresenta os top-k da fronteira mais relevante com a divergência documentada.

### 4b.9 Justificativa por Cenário (Explainability)

Cada `CenarioRankeado` inclui justificativa estruturada:

```python
@dataclass
class JustificativaCenario:
    rank: int
    motivo_inclusao: str          # "pareto_intersecao" | "pareto_EF_fallback" | etc.
    destaques_O: list[str]        # ex: ["prazo 2 sem antes do contrato", "0 itens críticos"]
    destaques_EF: list[str]       # ex: ["margem 13.2% (meta: 10%)", "pool 8% abaixo mercado"]
    alertas: list[str]            # dimensões em ATENCAO
    parametros_chave: dict        # quais parâmetros variados distinguem este cenário
```

### 4b.10 Mapeamento de Campos → Fontes no Canonical

| Campo | Fonte no canonical | Disponível desde |
|---|---|---|
| `prazo_semanas` | `cronograma.makespan_semanas` | ADR-091 (fix 2026-06-11) |
| `fe_nec_medio` | `mean(ponto_equilibrio[].frentes_equivalentes_necessarias)` | ADR-076 |
| `gap_pool_total` | `sum(ponto_equilibrio[].gap_pool_overhead)` | ADR-076 |
| `custo_mob_window_total` | `sum(equipes_diretas[].custo_inst_mob_demob)` | ADR-106 F5 |
| `margem_pct` | `resultado.margem_pct` | ADR-085 |
| `custo_execucao_pool` | `resultado.custo.direto_equipes` | NEP-043 (fix 2026-06-11) |
| `ratio_pool_vs_cat` | `custo_execucao_pool / venda.total_sem_bdi` | NEP-042 |
| `fidelidade_gates` | `quality_gates.decision` | ADR-051 |

---

## 5. Plano de Implementação Revisado

As fases foram reordenadas para aproveitar a infra existente e validar valor incremental antes de investir em complexidade.

### Fase 1 — Contrato e infra mínima (F1 revisado)

```python
@dataclass
class ParametroSweep:
    campo: str           # "escopos[0].cronograma[0].n_equipes.n_max"
    valores: list[Any]   # [1, 2, 3, 4] ou range discreto

@dataclass
class GoResearchCampaignBundle:
    base_spec: dict              # ProjetoSpec canônico
    sweep: list[ParametroSweep]
    constraints: list[str]       # ex: ["n_max >= n_inicial", "prazo <= deadline"]
    top_k: int = 5
    campaign_version: str = "v1"
```

DoD: Bundle versionado e persistido. Geração do grid de cenários (produto cartesiano de `sweep`). Pruning por `constraints`.

### Fase 2 — Motor de avaliação real (F2 revisado)

Adaptar o CLI `benchmark plan-space` para consumir `GoResearchCampaignBundle`:
1. Gerar `ProjetoSpec` variantes a partir do sweep
2. Executar pipeline completo para cada variante (workers paralelos — ADR-102)
3. Coletar `I_O(x)` e `I_EF(x)` do canonical resultante

DoD: 10 cenários avaliados em paralelo com canonical completo por cenário. Trilha de auditoria por run.

### Fase 3 — Curadoria Pareto (F3 revisado)

```python
def curar_pareto(cenarios: list[CenarioAvaliado], top_k: int) -> list[CenarioRankeado]:
    viaveis = [c for c in cenarios if c.ief["fidelidade_gates"]]
    pareto_O  = fronteira_pareto(viaveis, dims=["prazo_semanas", "gap_pool_total", "custo_mob_window"])
    pareto_EF = fronteira_pareto(viaveis, dims=["margem_pct", "custo_indireto"])
    intersecao = set(pareto_O) & set(pareto_EF)
    ranked = sorted(intersecao or pareto_EF,
                    key=lambda c: (-c.ief["margem_pct"], c.io["prazo_semanas"], c.hash))
    return ranked[:top_k]
```

DoD: Top-k com justificativa explícita por dimensão. Replay reproduz mesmo ranking com mesmo seed/inputs.

### Fase 4 — Templates de equipe (F4)

Em vez de composição livre, usar `producao.composicao_padrao_equipe` do catálogo como template canônico. Sweep D3 é sobre seleção entre CPUs alternativos para o mesmo item (ex: escavação 1ª cat. DMT2000 vs DMT3000), não sobre composição livre.

DoD: Catálogo de CPUs alternativos por tipo de serviço. Sweep discreta entre CPUs — bloqueio de combinações inválidas.

### Fase 5 — MCP tool e relatório (F5)

```python
explorar_configuracoes_go(
    project_id: str,
    parametros_sweep: dict,   # ex: {"n_max": [1,2,3], "leadtime_mob": [1,2,3]}
    top_k: int = 5
) -> GoSearchResult
```

DoD: MCP tool registrado. Resultado renderizado no app diagnóstico-pe (aba nova "Exploração GO").

---

## 6. Definition of Done Revisado

### Fase 1
- [ ] `GoResearchCampaignBundle` tipado com validação
- [ ] Geração de grid de `ProjetoSpec` variantes
- [ ] Pruning por constraints antes da avaliação
- [ ] Persistência com `campaign_version`

### Fase 2
- [ ] Pipeline completo por variante (não estimativa linear)
- [ ] `I_O` e `I_EF` coletados automaticamente do canonical
- [ ] Execução paralela com worker pool (ADR-102)
- [ ] Trilha de auditoria JSON por run

### Fase 3
- [ ] Pareto O-space com dims `(prazo, gap_pool, mob_window)`
- [ ] Pareto EF/F-space com dims `(margem, custo_indireto)`
- [ ] Tie-break estável por `(margem DESC, prazo ASC, hash)`
- [ ] Replay produz top-k idêntico

### Fase 4
- [ ] Catálogo de CPUs alternativos por tipo de serviço
- [ ] Sweep discreta entre CPUs com validação semântica

### Fase 5
- [ ] MCP tool `explorar_configuracoes_go`
- [ ] Aba "Exploração GO" no app diagnóstico-pe

---

## 7. Consequências (atualizadas)

### Positivas novas (pós-reavaliação)

1. **ProjetoSpec como base natural do bundle** — sem contratos proprietários; sweep é só uma forma de variar o mesmo documento que o engenheiro já conhece
2. **NEP-043 garante métricas confiáveis** — comparações entre cenários são agora matematicamente defensáveis
3. **Infra paralela já existe** — `plan_space` CLI + worker pool (ADR-102) são reutilizáveis diretamente
4. **Sliders como "Fase 0"** — `simular_cenario_replan` com `lever_adjust` já dá preview linear antes do pipeline completo; pode ser o gatilho de decisão de executar a campanha completa

### Riscos mantidos

1. Explosão combinatória para sweeps amplos — mitigar com pruning por constraints antes da avaliação
2. Custo computacional — mitigar com amostragem inicial (Latin Hypercube) + refinamento local nas regiões Pareto-ativas

---

## 8. Política de Governança (original — preservada)

1. Toda variação de parâmetro deve declarar fonte, limite e responsável
2. Toda mudança da função de ranking deve incrementar `campaign_version`
3. Nenhum resultado sem trilha de auditoria pode ser promovido como recomendação
4. Curadoria por agente é opcional; curadoria determinística é obrigatória
5. Toda campanha deve explicitar perfil de expectativas EF/F versionado no bundle
