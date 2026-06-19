# ADR-113 — Desacoplamento do Pipeline de Otimização de Persistência e Análise

**Status:** Proposta  
**Data:** 2026-06-19  
**Contexto:** MendesLobo Construtora — Concilium  
**Dependências:** ADR-046 (RCPSP), ADR-075 (Pipeline-Motor), ADR-078 (Pré-Processamento), ADR-079 (Ativação Econômica), ADR-091 (Pool Mínimo como Variável)

---

## Contexto

### Problema

**P1. ADR-079 implementado mas não conectado — LNS otimiza sem feedback de custo real.**

`explore_schedules()` em `selector.py` instancia `MatchingOracle(mob_costs={})` hardcoded vazio em duas
chamadas (linhas 143 e 252). A skill-04 (`skill.py:1355, 1368`) nunca passa `initial_lambdas` vindos
do `RelatorioOportunidades` (ADR-078). O resultado prático:

- LNS converge em relação a makespan estrutural, não a `C_total = C_op + C_mob`
- Multi-projeto com compartilhamento de pool recebe a mesma qualidade de solução que mono-projeto
- ADR-079 (pre-warming de λ₀ a partir de oportunidades) declarado como implementado, mas inerte

```python
# selector.py:143 — mob_costs sempre vazio
oracle = MatchingOracle(mob_costs={})
lns = LnsScheduler(oracle=oracle, initial_lambdas=initial_lambdas or None)

# skill.py:1355 — initial_lambdas nunca fornecido
explored = explore_schedules(
    activities=activities,
    dag=dag,
    pool=pool,
    deadline_weeks=deadline_weeks,
    ...
    # initial_lambdas ausente → LNS não recebe λ₀ do RelatorioOportunidades
)
```

**P2. Pipeline de skills monolítico — não há "fast path" de scheduling sem análise financeira.**

O `BenchmarkRunner.run()` tem dois modos:
- `skip_artifacts=False`: skills 01–13 (completo)
- `skip_artifacts=True`: skills 01–06 (ainda inclui 05/06 de custo)

Não existe modo que pare após skill-04 (só agendamento, sem custo). Para uma campanha de exploração
que precisa avaliar N cronogramas antes de escolher o melhor para análise financeira completa:

```
Atual (ineficiente):
  N × (01→02→03→04→05→06) = N execuções de custo completo

Ideal:
  1 × (01→02→03)                     [once: catalog + EAP]
  N × (04_schedule_only)             [N vezes: só scheduling]
  K × (04_replay + 05→06)            [K vezes: análise nos K melhores]
```

Sem esse fast path, a campanha de exploração (ADR-070) corre N pipelines completos, sendo 80% do
tempo gasto em custo para cronogramas descartados.

**P3. ScheduleOutput não distingue resultado de otimização de configuração de replay.**

Não há como re-executar as skills 05-06 sobre um cronograma já computado (replay) sem refazer o
RCPSP. Isso impede:
- Recalcular custos com BDI diferente sem re-agendar
- Comparar preços de catálogo alternativos sobre o mesmo cronograma
- Análise de sensibilidade financeira mantendo o schedule fixo

---

## Decisão

### Eixo 1 — Conectar mob_costs e initial_lambdas ao LNS (ADR-079 operacional)

**D1 — `explore_schedules()` aceita mob_costs opcionais e repassa ao MatchingOracle.**

```python
def explore_schedules(
    ...,
    initial_lambdas: dict | None = None,
    mob_costs: dict[str, float] | None = None,   # NOVO: {resource_id: C_mob}
) -> list[ExploreResult]:
    ...
    oracle = MatchingOracle(mob_costs=mob_costs or {})
    lns = LnsScheduler(oracle=oracle, initial_lambdas=initial_lambdas or None)
```

**D2 — Skill-04 extrai `mob_costs` do canonical existente (run anterior) e os passa ao LNS.**

Se existe canonical de uma run anterior (re-planejamento ou campanha incremental), skill-04 lê
`eq.custo_mob_desmob_total` por recurso e monta o dicionário `mob_costs`:

```python
mob_costs = {
    eq.equip_id: eq.custo_mob_desmob_total
    for eq in canonical_anterior.equipes_diretas
    if eq.custo_mob_desmob_total
} if canonical_anterior else {}
```

**D3 — Skill-04 extrai `initial_lambdas` do RelatorioOportunidades quando disponível.**

Se ADR-078 já foi executado (canonical tem `relatorio_oportunidades`), skill-04 mapeia
`(atividade_i, atividade_j, tipo_id) → λ₀` e passa ao `explore_schedules()`.

### Eixo 2 — Fast path de scheduling e replay financeiro

**D4 — Skill-04 expõe modo `scheduling_only=True`.**

Quando `scheduling_only=True`, skill-04 executa o RCPSP e persiste `scheduled_activities` no
canonical, mas não calcula `distribuicao_semanal` completa nem prepara inputs para skill-05/06:

```python
# Inputs de skill-04 que ativam fast path
{
    "scheduling_only": True    # parar após ScheduleOutput; pular expansão para distribs
}
```

**D5 — `BenchmarkRunner` expõe terceiro modo: `schedule_only=True`.**

```python
runner.run(spec, skip_artifacts=False)      # completo (01-13)
runner.run(spec, skip_artifacts=True)       # financeiro (01-06)
runner.run(spec, schedule_only=True)        # só scheduling (01-04)
```

Tempo estimado do modo `schedule_only` para benchmark típico: 2–5s vs 20–40s do `skip_artifacts`.

**D6 — Skill-04 e BenchmarkRunner aceitam `schedule_input` para replay financeiro.**

Para re-executar custo sobre um cronograma já computado:

```python
runner.run(spec, replay_schedule_from=version_id)
```

Internamente:
1. Lê `ScheduleOutput` do canonical da versão `version_id`
2. Cria nova versão no store
3. Pula skill-01 a 04, começa da skill-05 com o schedule fixo
4. Persiste novo canonical com custo diferente mas mesmo cronograma

Isso permite análise de sensibilidade: "qual o impacto financeiro de mudar o BDI de material de 4%
para 6% neste cronograma?" sem re-agendar.

### Eixo 3 — Separação conceptual: SchedulingSpec vs AnalysisSpec

**D7 — `ProjectSpec` passa a ter seção `rcpsp_override` explícita, separada de `bdi_override`.**

```python
@dataclass
class ProjectSpec:
    # Existente
    inputs_cronograma: dict     # controla skill-04
    inputs_indiretos: dict      # controla skill-05/06
    ...
    # Novo: override explícito de schedule sem re-agendar
    rcpsp_override: dict | None = None    # se presente, pula RCPSP e usa schedule fornecido
```

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Extrair scheduler como microserviço separado | Over-engineering; o problema é de fast-path e feedback de custo, não de deployment |
| A2 | Refatorar todo o pipeline de skills | Risco de regressão elevado; os dois eixos cobrem o problema sem quebrar o contrato das skills |
| A3 | Manter ADR-079 inerte e só documentar | O feedback de custo é arquiteturalmente fundamental para otimização multi-projeto real |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| LNS otimiza custo real | mob_costs wired → solução melhora para projetos com pool compartilhado |
| Campanhas 10–20× mais rápidas | `schedule_only` mode evita skills 05-06 para N cronogramas descartados |
| Análise de sensibilidade habilitada | `replay_schedule_from` permite variar BDI/catálogo sem re-agendar |
| ADR-079 operacional | Pre-warming de lambdas finalmente conectado ao LNS |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| `mob_costs` do canonical anterior pode ser de um projeto diferente | Validar que canonical é do mesmo `contexto_id` antes de usar; fallback para `{}` |
| `scheduling_only=True` cria canônicos incompletos (sem equipes/custos) | Marcar canonical com `scheduling_state: "partial"` para evitar uso indevido |
| Replay financeiro pode divergir de um run completo se skills 01-03 mudaram | Incluir hash do catálogo/perfil no canonical; avisar quando o replay usa catálogo diferente |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 | `explore_schedules()` aceita `mob_costs` opcionais; `selector.py` repassa ao oracle | ⬜ Pendente |
| F2 | Skill-04 extrai `mob_costs` do canonical anterior e passa a `explore_schedules` | ⬜ Pendente |
| F3 | Skill-04 extrai `initial_lambdas` do `relatorio_oportunidades` quando disponível | ⬜ Pendente |
| F4 | `BenchmarkRunner.run(schedule_only=True)` — fast path 01-04 | ⬜ Pendente |
| F5 | `BenchmarkRunner.run(replay_schedule_from=version_id)` — replay financeiro | ⬜ Pendente |
| F6 | `ProjectSpec.rcpsp_override` — spec explícita para replay sem RCPSP | ⬜ Pendente |

**Invariante:** cada fase preserva comportamento para callers que não passam os novos parâmetros.

---

## Definition of Done

### Fase 1–3 (ADR-079 operacional)
- [ ] `explore_schedules(mob_costs={"E0027": 6500.0}, ...)` produz makespan ≤ run sem mob_costs em problema multi-projeto com sobreposição
- [ ] Skill-04 lê `mob_costs` do canonical anterior quando disponível
- [ ] Benchmark AGIS re-executado com mob_costs: LNS muda estratégia de alocação (log `_log.info`)
- [ ] `pytest tests/` verde

### Fase 4–5 (Fast path e replay)
- [ ] `runner.run(spec, schedule_only=True)` para AGIS completa em < 5s
- [ ] `runner.run(spec, replay_schedule_from="v1")` produz canonical com `scheduling_state: "replay"` e mesmo `makespan_weeks` de v1
- [ ] `pytest tests/` verde

---

## Relacionados

- ADR-075 — Pipeline-Motor (selector.py — ponto de injeção de mob_costs)
- ADR-079 — Ativação Econômica (initial_lambdas — conectar ao LNS)
- ADR-078 — Pré-Processamento (RelatorioOportunidades — fonte de λ₀)
- ADR-070 — Cardinalidade do Espaço GO (campanha beneficia do fast path)
- ADR-046 — RCPSP (contrato de entrada/saída do scheduler)
