# ADR-070: Exploração Determinística do Espaço de Configuração Operacional para Viabilidade de GO

**Status:** ⚠️ Parcialmente Implementado — reavaliado 2026-06-11  
**Data original:** 2026-05-23  
**Reavaliação:** 2026-06-11 — correção de status + mapeamento ao estado atual + path revisado  
**Relacionado:** ADR-004, ADR-005, ADR-006, ADR-020, ADR-021, ADR-022, ADR-051, ADR-060, ADR-061, NEP-042, NEP-043

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
