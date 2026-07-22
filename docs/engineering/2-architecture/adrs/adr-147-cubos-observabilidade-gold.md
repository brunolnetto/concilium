# ADR-147 — Cubos de Observabilidade Gold

**Status:** Implementado
**Data:** 2026-07-21
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-087 (CuboAnalitico — padrão que este ADR generaliza para observabilidade), ADR-112 (Pipeline Medallion), ADR-146 (Contrato de Labels de Métricas — pré-requisito de CuboMetricas)

---

## Contexto

### Problema

P1. **`GoldAggregator` pré-computa relatórios em vez de expor um modelo consultável.** `build_sli_diario`, `build_fallback_rate_por_skill` e `CrossDomainBuilder.build()` cada um lê Silver, monta sua própria tabela DuckDB com colunas fixas e roda uma SQL própria fixa em `(date, skill_id)` ou `project_id`. Perguntar "SLI por tool" ou "fallback rate por usuário" exige escrever uma função nova.

P2. **A leitura de Silver estava triplicada.** `ObservabilityWorker.read_silver`, `GoldAggregator._read_silver` e `CrossDomainBuilder._read_silver_logs` tinham corpo byte-idêntico (listar blobs do prefixo, ler NDJSON, deduplicar) — os três docstrings já reconheciam isso ("mesmo motivo de...").

P3. **Gold nunca usou metrics.** Com o gap 2 fechado (ADR-146), `skill_id`/`tool_name`/`project_id` já são colunas de primeira classe em Silver metrics — mas nenhum consumidor Gold lia esse sinal.

### Precedente já resolvido no sistema

`CuboAnalitico`/`CelulaAnalitica` (`domain/models/analytics/cubo_analitico.py`, ADR-087) já resolveu exatamente este problema para custo/BDI: tupla imutável de células no grão atômico + `.slice()`/`.group_by()` derivam qualquer projeção sob demanda, expostas via `/cubo-analitico/projecao` + `/projecao/contrato`. Este ADR generaliza o mesmo padrão para observabilidade.

## Decisão

D1. **`read_silver_records(storage, signal_type)`** (`pipeline.py`) — extraída das três cópias idênticas. `ObservabilityWorker.read_silver`, `GoldAggregator._read_silver` e `CrossDomainBuilder._read_silver_logs` viram wrappers finos que delegam a ela, preservando as assinaturas existentes (usadas por testes).

D2. **`Cubo[CelulaT]`** genérica (`cubo_base.py`) — tupla imutável de células + duas operações:
- `slice(**filtros)`: filtro por igualdade exata em Python puro, mesma semântica de `CuboAnalitico.slice()`. Filtros com valor `None` são ignorados (permite `cubo.slice(project_id=talvez_none)` sem `if` externo).
- `query(group_by, aggs, where=None, order_by=None)`: agregação via DuckDB in-process — reaproveita o motor que `build_sli_diario` já usava para percentis, generalizado por dimensão em vez de fixo. `group_by` aceita expressões com alias (`"COALESCE(skill_id, 'unknown') AS skill_id"`); internamente usa `GROUP BY ALL` (DuckDB agrupa por todo item não-agregado do SELECT), então expressões com alias funcionam sem repetir a expressão inteira no GROUP BY.

D3. **Diferença deliberada de `CuboAnalitico`:** lá, uma única medida (`valor_rs`) cobre todas as categorias de custo e `group_by()` só soma, em Python puro. Aqui as medidas são heterogêneas — percentil (spans), contagem (logs), valor livre (metrics), duração calculada (tool_invocations) — o que já exigia DuckDB antes deste ADR (`build_sli_diario`). `query()` generaliza esse motor em vez de reescrevê-lo por relatório.

D4. **Quatro cubos concretos, um por fato do ERD** (não um cubo unificado — confirmado com o usuário): `CuboSpans`, `CuboLogs`, `CuboMetricas`, `CuboToolInvocations`, cada um com sua célula (`CelulaSpan`, `CelulaLog`, `CelulaMetrica`, `CelulaToolInvocation`) e um `from_silver(records) -> CuboX` que mapeia o schema Silver já existente (nenhuma mudança de schema Silver foi necessária — as 4 normalizações já produzem exatamente os campos que as células precisam). `CuboToolInvocations.duration_ms` é a única medida calculada na construção da célula (`finished_at - started_at`, parseado com `datetime.fromisoformat`, tolerante a timestamps ausentes/malformados — retorna 0, nunca lança).

D5. **`GoldAggregator` e `CrossDomainBuilder` migrados, comportamento preservado byte a byte.** `build_sli_diario`/`build_fallback_rate_por_skill`/`CrossDomainBuilder.build()` agora constroem o cubo apropriado e chamam `.query()` com os mesmos `group_by`/`aggs`/`where`/`order_by` que a SQL manual anterior continha — nenhum teste existente precisou mudar (a suíte pré-existente é a prova de não-regressão). `build_alertas_ativos` não mudou (já era lógica Python pura sobre os outros dois).

D6. **`_aggregate_fallback_by_project` removida.** Virou código morto assim que `CrossDomainBuilder.build()` passou a usar `CuboLogs.query()` diretamente — sem teste direto dependendo dela, foi removida em vez de mantida ao lado do caminho novo.

D7. **CuboMetricas ainda não tem um `GoldAggregator.build_*` que o consuma.** É o primeiro cubo cujo sinal de origem (metrics) nunca teve um relatório Gold — implementado e testado, mas nenhuma tabela Gold nova foi adicionada nesta ADR (fora de escopo: qual relatório de metrics vale a pena é uma decisão de produto, não de arquitetura).

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Um cubo unificado para os 4 sinais | Medidas incompatíveis (duração vs. contagem vs. valor livre) tornariam a célula um dicionário de campos majoritariamente vazios por linha — confirmado com o usuário que 4 cubos separados é o desenho certo |
| A2 | `Cubo.query()` construir SQL só com colunas simples (sem suportar alias) | `build_fallback_rate_por_skill` já precisa de `COALESCE(skill_id, 'unknown')` no GROUP BY — sem suporte a alias, essa migração exigiria manter esse relatório fora do padrão novo |
| A3 | Registrar as células como `pandas.DataFrame` para o DuckDB ler via replacement scan | `pandas` não é dependência declarada do projeto (só transitiva); `CREATE TABLE` + `executemany` tipado é o padrão que `build_sli_diario` já usava, sem dependência nova |
| A4 | Manter `_read_silver`/`_read_silver_logs` como cópias, só documentando a duplicação | Motivo de existir deste ADR incluía consolidar antes de crescer para uma 4ª/5ª/6ª/7ª cópia — os cubos são justamente esses novos consumidores |

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Perguntas novas sem função nova | "fallback rate por usuário", "duração média de tool por device" — qualquer combinação de dimensões vira uma chamada `.query()`, não um método novo em `GoldAggregator` |
| Triplicação eliminada | `read_silver_records` tem um único dono; os 3 call-sites e os 4 cubos novos compartilham a mesma implementação |
| CuboMetricas existe | Gold pode, quando houver decisão de produto, expor uso de tools/skills a partir de metrics — sem precisar desenhar o pipeline de leitura do zero |
| Zero regressão | Toda a suíte pré-existente de `GoldAggregator`/`CrossDomainBuilder` passou sem alteração — prova de que a migração preservou saída byte a byte |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| `query()` monta SQL por f-string a partir de `group_by`/`aggs`/`where`/`order_by` | Todos os call-sites são código interno (literais no próprio repositório), nunca input de usuário — mesmo risco que a SQL manual anterior já tinha |
| Extração de alias em `group_by` exige exatamente `" AS "` maiúsculo | Documentado na docstring de `query()`; único formato usado pelos call-sites internos |
| `CuboMetricas` sem consumidor Gold ainda | Aceitável como F1 — implementar um relatório sem um caso de uso definido seria escopo especulativo; a decisão de qual relatório fica para quando houver necessidade de produto |

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 | `read_silver_records` extraída; `Cubo` base genérica (`slice`/`query`) | ✅ Implementado |
| F2 | `CuboSpans`/`CuboLogs`/`CuboMetricas`/`CuboToolInvocations` + células | ✅ Implementado |
| F3 | `GoldAggregator.build_sli_diario`/`build_fallback_rate_por_skill` migrados | ✅ Implementado |
| F4 | `CrossDomainBuilder.build()` migrado; `_aggregate_fallback_by_project` removida | ✅ Implementado |

## Definition of Done

- [x] `read_silver_records` com teste próprio; os 3 wrappers delegam sem duplicar lógica
- [x] `Cubo.slice()`/`Cubo.query()` testados (filtro composto, `None` ignorado, GROUP BY ALL com alias, percentil, ORDER BY, WHERE)
- [x] Os 4 cubos com teste de `from_silver` (mapeamento completo + campos ausentes) e ao menos uma `query()` de integração
- [x] Suíte pré-existente de `GoldAggregator`/`CrossDomainBuilder` passa sem alteração
- [x] Nenhum código morto deixado ao lado do caminho novo (`_aggregate_fallback_by_project` removida)

---

## Relacionados

- ADR-087 — CuboAnalitico (padrão de célula imutável + slice/group_by que este ADR generaliza)
- ADR-112 — Pipeline Medallion (Silver que os 4 cubos consomem)
- ADR-146 — Contrato de Labels de Métricas (pré-requisito de `CuboMetricas` — sem ele, `skill_id`/`tool_name`/`project_id` não existiam em Silver metrics)
- ERD Gold de observabilidade (artifact da sessão 2026-07-20/21) — este ADR implementa a seção "Gold como cubo" do ERD
