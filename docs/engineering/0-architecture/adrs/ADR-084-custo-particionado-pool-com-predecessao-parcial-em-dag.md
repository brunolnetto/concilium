# ADR-084 — Partição de Custo em Pool Compartilhado: Atribuição Causal com Predecessão Parcial em DAG

**Status:** Parcialmente Implementado (Fase 3 concluída)
**Data:** 2026-05-28
**Contexto:** MendesLobo Construtora — Concilium
**Supersede:** ADR-083 (Partição de Custo em Pool Compartilhado: Atribuição Temporal Causal Muitos-para-Muitos)
**Dependências:** ADR-071 (Resource Contract Model), ADR-073 (Perpetuação de Instâncias), ADR-082 (Levers de Ponto de Equilíbrio)

---

## Contexto

### Problema

**P1 — O gap_pool era opaco e unidimensional (herdado do ADR-083)**

O `gap_pool_overhead = custo_operacional_real − custo_total_autonomo` reportava um número único sem distinguir se o compartilhamento gerou economia de mob/demob (perpetuação, ADR-073) ou overhead de ociosidade entre atividades. O lever `fechar_gap_pool` no painel de equilíbrio não apontava qual variável operacional atacar.

**P2 — A atribuição causal do ADR-083 foi incorretamente descrita como "aproximação de Shapley"**

O ADR-083 chamava a atribuição causal de "atribuição causal simplificada como aproximação do Shapley" e declarava Shapley inviável para n > 3 com complexidade O(2ⁿ). Ambas as partes estavam incorretas, mas por razões distintas:

- **A complexidade O(2ⁿ) era incorreta**: existem classes de jogos com Shapley computável em O(n) — por exemplo, Airport Games (Littlechild & Owen, 1973), onde `v(S) = f(max S)`. O ADR-083 generalizou indevidamente um limite do Shapley simétrico geral para todo n.

- **O jogo de pool NÃO é um Airport Game**: no Airport Game estrito, `v(S)` depende *exclusivamente* do membro de maior custo da coalizão. No jogo de pool com gaps, `v(S) = c_unit × (T_end(max S) − T_start(min S)) + gaps(S)`, que depende de *ambos* o membro inicial e o final, além da estrutura de gaps interna. A condição `v(S) = f(max S)` só se satisfaz sob a hipótese artificial de que o contrato sempre começa em `T_start_contract` fixo independentemente de quais atividades compõem S — o que implica que uma atividade isolada pagaria pela duração integral desde o início do projeto, não apenas pela sua própria janela. Isso é economicamente incorreto.

- **A atribuição causal NÃO é o Shapley exato do Airport Game**: para uma cadeia `A=5w, B=3w` (sem gap, c=1), o Shapley do Airport Game (formulação cumulativa `c_A=5, c_{AB}=8`) resulta em φ_A = 5.5, φ_B = 2.5 — diferente da atribuição causal que dá φ_A = 5, φ_B = 3. O Airport Game cobra A acima de sua duração produtiva porque A "habilita" o contrato para B; a atribuição causal cobra cada atividade apenas pelo tempo em que o recurso trabalhou para ela.

**A atribuição causal é uma axiomatização independente e correta para o domínio de construção**, satisfazendo:
- *Eficiência*: `Σ custo_total_particionado = C_contrato` (invariante de conservação, exato)
- *Responsabilidade causal de gap*: gap imputado ao sucessor que não pôde iniciar antes — o predecessor já havia terminado sua obrigação
- *Igualitarismo de mob/demob por cadeia*: Shapley igualitário para o custo fixo de mobilização dentro de uma cadeia de perpetuação

Esta axiomatização é O(n) por construção (iteração sobre itens na ordem da cadeia) e não é uma aproximação de nada — é a regra correta para este domínio.

**P3 — A cadeia sequencial assumida no ADR-083 é inválida com predecessão parcial**

O modelo canônico evoluiu para suportar predecessão parcial `p ∈ (0, 1]`: a atividade sucessora pode iniciar quando o predecessor atingiu `p × Q_predecessor`, sem aguardar 100% do quantitativo. Isso introduz três efeitos que invalidam as fórmulas de partição baseadas em spans sequenciais disjuntos:

- **Sobreposição temporal produtiva**: predecessor e sucessor podem estar ativos simultaneamente, e o custo do recurso durante o overlap precisa ser fracionado entre ambos — o gap entre atividades pode ser negativo (paralelismo produtivo, não ociosidade).
- **DAG com múltiplos predecessores**: o instante de início de uma atividade é determinado pelo **predecessor crítico** `aᵢ* = argmax{ T_start(aᵢ) + p_ij × duration_i }`. Predecessores não-críticos chegam antes do necessário e não geram custo de gap para o sucessor.
- **Decomposição por segmento, não por span**: com sobreposição, a partição por "span do contrato ÷ machine-weeks" subestima o custo de atividades que operam em paralelo com outras. A decomposição correta precisa operar sobre o intervalo real de ativação de cada atividade (que pode sobrepor outros intervalos), não sobre o span do contrato como um todo.

**P4 — O gap_praticabilidade era zero estrutural (herdado, corrigido em sprint anterior)**

`gap_praticabilidade = custo_total_autonomo − (custo_fixo_mensal × permanencia_efetiva) ≡ 0` por identidade aritmética — a duração estendida pelo clima aparecia em ambos os lados. Corrigido para `gap_praticabilidade_abs = custo_total_autonomo × (1 − η̄)` onde `η̄` é a média ponderada por team-weeks do fator climático semanal. Esta correção permanece válida e **ortogonal** à decomposição de pool.

---

## Decisão

### D1 — Substituir o sweep line manual por `euler()` sobre `IntervalSet` contínuo

A partição de custo entre atividades é implementada via `eule[interval]`, que computa o **diagrama de Euler** sobre `IntervalSet` nativos. Cada chave da saída é uma tupla de IDs de atividades ativas naquela região; o valor é um `IntervalSet` cuja `.measure()` retorna a duração contínua exata em semanas — sem discretização.

```python
# pip install "eule[interval]"
from interval_sets import Interval, IntervalSet
from eule import euler

def _build_diagram(atividades: list[AtividadeNoContrato]) -> dict:
    """
    Constrói o diagrama de Euler sobre as janelas temporais das atividades.
    Retorna dict[tuple[str, ...], IntervalSet] com regiões disjuntas.
    Cada região representa um conjunto de atividades ativas simultaneamente.
    """
    sets = {
        a.id: IntervalSet([Interval(a.T_start, a.T_end)])
        for a in atividades
    }
    return euler(sets)  # O(n log n)
```

**Contrato da saída de `euler()`:**

| Campo | Tipo | Semântica |
|---|---|---|
| `keys` (chave do dict) | `tuple[str, ...]` | IDs das atividades ativas na região |
| `region` (valor) | `IntervalSet` | Intervalo contínuo da região; `.measure()` = duração em semanas |
| Cobertura | — | Toda semana produtiva do contrato está em exatamente uma região |
| Gaps | — | Semanas ociosas (recurso ativo, sem produção) **não aparecem** no diagrama |

Para `p = 1` (cadeias sequenciais sem sobreposição) — caso atual de todos os benchmarks — `euler()` produz apenas regiões com `|keys| == 1`, sendo equivalente à atribuição causal já implementada via `_compute_particao_por_tipo` + `_enrich_particao_overhead`. Para `p < 1`, produz regiões de sobreposição automaticamente, sem código extra.

### D2 — Partição completa: produtivo + mob/demob + gaps causais

```python
def particionar_contrato(
    atividades: list[AtividadeNoContrato],
    c_mob: float,
    c_demob: float,
    c_unit_semana: float,
    T_contrato_start: float,
    T_contrato_end: float,
) -> dict[str, CustoParticionadoItem]:
    """
    Partição exata de custo por atividade. Complexidade O(n log n).
    Invariante: Σ custo_total_particionado == C_contrato_total.
    """
    diagram = _build_diagram(atividades)
    phi = {a.id: 0.0 for a in atividades}
    overlap_semanas = {a.id: 0.0 for a in atividades}
    custo_exclusivo = {a.id: 0.0 for a in atividades}
    custo_compartilhado = {a.id: 0.0 for a in atividades}

    # 1. Regiões produtivas: exclusivas (|keys|=1) e compartilhadas (|keys|>1)
    for ids_ativas, region in diagram.items():
        duracao = region.measure()
        custo = duracao * c_unit_semana
        n_ativas = len(ids_ativas)
        for aid in ids_ativas:
            parcela = custo / n_ativas
            phi[aid] += parcela
            if n_ativas == 1:
                custo_exclusivo[aid] += parcela
            else:
                custo_compartilhado[aid] += parcela
                overlap_semanas[aid] += duracao

    # 2. Mob e demob: divididos igualmente (Shapley igualitário por cadeia — ADR-073)
    n = len(atividades)
    mob_por_item = c_mob / n
    demob_por_item = c_demob / n
    for a in atividades:
        phi[a.id] += mob_por_item + demob_por_item

    # 3. Gaps (recurso ativo, nenhuma atividade produtiva):
    #    janela_contrato − união_produtiva → imputar ao sucessor crítico de cada gap
    all_ivs = [iv for _, region in diagram.items() for iv in region]
    uniao_produtiva = IntervalSet(all_ivs)
    janela = IntervalSet([Interval(T_contrato_start, T_contrato_end)])
    gaps_obj = janela - uniao_produtiva

    custo_ocioso = {a.id: 0.0 for a in atividades}
    for gap_iv in _iter_intervals(gaps_obj):
        critico_id = _sucessor_critico(gap_iv.end, atividades)
        if critico_id:
            custo_gap = gap_iv.length() * c_unit_semana
            phi[critico_id] += custo_gap
            custo_ocioso[critico_id] += custo_gap

    # 4. Montar CustoParticionadoItem por atividade
    resultado = {}
    for a in atividades:
        custo_autonomo = (a.T_end - a.T_start) * c_unit_semana + c_mob + c_demob
        total = phi[a.id]
        resultado[a.id] = CustoParticionadoItem(
            item_id=a.id,
            custo_produtivo_exclusivo=custo_exclusivo[a.id],
            custo_produtivo_compartilhado=custo_compartilhado[a.id],
            custo_mob_imputado=mob_por_item,
            custo_demob_imputado=demob_por_item,
            custo_ocioso_imputado=custo_ocioso[a.id],
            custo_total_particionado=total,
            custo_total_autonomo=custo_autonomo,
            economia_vs_autonomo=custo_autonomo - total,
            predecessor_critico_id=_predecessor_critico_id(a, atividades),
            overlap_semanas=overlap_semanas[a.id],
        )
    return resultado


def _iter_intervals(obj) -> list:
    """Normaliza Interval | IntervalSet para lista de Interval."""
    if isinstance(obj, IntervalSet):
        return [] if obj.is_empty() else list(obj)
    return [] if obj.is_empty() else [obj]


def _sucessor_critico(gap_end: float, atividades: list) -> str | None:
    """Primeira atividade que inicia em ou após gap_end."""
    candidatos = [(a.id, a.T_start) for a in atividades if a.T_start >= gap_end - 1e-9]
    return min(candidatos, key=lambda x: x[1])[0] if candidatos else None


def _predecessor_critico_id(aj: AtividadeNoContrato, todas: list) -> str | None:
    """
    Predecessor que maximiza T_start(aᵢ) + p_ij × duration_i,
    determinando o T_start de aj na DAG.
    """
    predecessores = [a for a in todas if a.T_end <= aj.T_start + 1e-9 and a.id != aj.id]
    if not predecessores:
        return None
    return max(predecessores, key=lambda a: a.T_end).id
```

### D3 — `CustoParticionadoItem` com componentes diagnósticos

**Estado atual (Fase 2A/2B — implementado):** campos `custo_produtivo`, `custo_mob_imputado`, `custo_ocioso_imputado`, `custo_total_particionado`, `economia_mob`, `overhead_ocioso`.

**Alvo (Fase 3 — pendente):** modelo expandido com todos os componentes abaixo.

```python
class CustoParticionadoItem(BaseModel):
    item_id: str

    custo_produtivo_exclusivo: float
    # Custo nos segmentos em que SOMENTE esta atividade está ativa
    # Fonte: regiões com |keys| == 1 no diagrama de Euler

    custo_produtivo_compartilhado: float
    # Custo nos segmentos de sobreposição atribuídos a esta atividade
    # Fonte: regiões com |keys| > 1 no diagrama de Euler, dividido por |keys|

    custo_mob_imputado: float   # C_mob / n  (Shapley igualitário por cadeia)
    custo_demob_imputado: float # C_demob / n

    custo_ocioso_imputado: float
    # Custo dos gaps [janela_contrato − união_produtiva] imputados causalmente
    # ao sucessor crítico de cada gap

    custo_total_particionado: float
    # = soma dos 5 componentes acima

    custo_total_autonomo: float
    # Custo se a atividade contratasse o recurso exclusivamente (baseline)

    economia_vs_autonomo: float
    # = custo_total_autonomo − custo_total_particionado
    # > 0 → pool economizou para este item
    # < 0 → pool foi mais caro para este item

    predecessor_critico_id: str | None
    # ID da atividade que determinou o T_start desta na DAG
    # None para a primeira atividade na cadeia

    overlap_semanas: float
    # Semanas em que esta atividade operou simultaneamente com outra
```

### D4 — `gap_pool_abs` como indicador signed com decomposição (implementado)

`gap_pool_overhead` (ADR-083, em `PontoEquilibrio`) e `gap_pool_abs` são complementares e já implementados:

```python
# PontoEquilibrio (canonical.py)
gap_pool_overhead: float  # custo_operacional_real − custo_total_autonomo (signed)
gap_pool_abs: float       # custo_total − custo_total_autonomo (overhead de pool)

# gap_pool_abs > 0: item paga MAIS no pool do que pagaria sozinho
#   → overhead de ociosidade supera economia de mob/demob
#   → lever fechar_gap_pool deve aparecer no painel

# gap_pool_abs < 0: item ECONOMIZA com o pool
#   → mob/demob evitados superam custo de gaps
#   → lever fechar_gap_pool NÃO aparece (pool é vantajoso)
```

A decomposição via `CustoParticionadoItem.overhead_ocioso` e `economia_mob` permite apontar qual das duas fontes domina, tornando o lever acionável.

### D5 — Decomposição do lever `fechar_gap_pool` no painel de equilíbrio

Quando `gap_pool_abs > 0`, o lever expõe os três componentes diagnósticos:

```python
restricoes = [
    f"Ociosidade imputada:      R$ {custo_ocioso_imputado:,.0f}",
    f"Custo em sobreposição:    R$ {custo_produtivo_compartilhado:,.0f}",
    f"Economia mob/demob:      −R$ {(c_mob + c_demob) - (mob_imputado + demob_imputado):,.0f}",
    f"Predecessor crítico:       {predecessor_critico_id or '—'}",
    f"Saldo líquido: {'overhead' if gap_pool_abs > 0 else 'economia'}"
    f" R$ {abs(gap_pool_abs):,.0f}",
]
```

Quando `gap_pool_abs ≤ 0`, o lever é **omitido** do painel — o pool é vantajoso e não deve ser perturbado.

### D6 — Dependência de biblioteca

```toml
# pyproject.toml
[project.dependencies]
"eule[interval]" = ">=0.1.3"   # puxa interval-sets automaticamente
```

`eule[interval]` ativa o protocolo `SetLike` para `IntervalSet`, permitindo que `euler()` opere sobre intervalos contínuos em ℝ. Sem o extra `[interval]`, `euler()` aceita apenas `set` Python e ignora `IntervalSet`.

### D7 — Identificação do predecessor crítico na DAG

Para cada atividade `aⱼ` com múltiplos predecessores `{aᵢ₁, aᵢ₂, …, aᵢₖ}`:

```python
def predecessor_critico(
    aj: Atividade,
    predecessores: list[tuple[Atividade, float]],  # (aᵢ, p_ij)
) -> Atividade:
    """
    Retorna o predecessor que determina o T_start de aj.
    Os demais chegaram antes do necessário e não geram custo de gap para aj.
    """
    return max(
        predecessores,
        key=lambda ap: ap[0].T_start + ap[1] * ap[0].duration_semanas
    )[0]
```

O custo de gap de `aⱼ` é imputado exclusivamente a `aⱼ` (causalidade do sucessor, ADR-083 §2.2 mantido). O diagnóstico aponta o predecessor crítico, mas não o responsabiliza financeiramente — a imputação permanece no sucessor que não conseguiu iniciar antes.

### D8 — Invariante de conservação (obrigatório em testes)

```python
assert abs(
    sum(item.custo_total_particionado for item in contrato.particao_por_item)
    - contrato.custo_total_contrato
) < 0.02  # tolerância R$ 2 centavos
```

A partição via `euler()` satisfaz este invariante por construção: `euler()` produz regiões **disjuntas e exaustivas** sobre a união das janelas produtivas, e os gaps são calculados como complemento dessa união na janela do contrato — nenhum centavo é contado duas vezes ou omitido.

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Machine-weeks proporcional sem decomposição (ADR-071 D3) | Opaca: não distingue economia de mob/demob de custo de ociosidade; ignora sobreposição |
| A2 | Airport Game (Littlechild-Owen) estrito | Inaplicável: o jogo de pool não satisfaz `v(S) = f(max S)` sob a definição natural (custo standalone de uma atividade é sua própria duração, não o span cumulativo desde o início do projeto). Além disso, o Shapley do Airport Game e a atribuição causal dão valores distintos mesmo para n=2 sem gap — são axiomatizações diferentes |
| A3 | Shapley simétrico por enumeração O(2ⁿ) | Desnecessário e axiomaticamente inadequado: Shapley simétrico distribui mob/demob proporcionalmente à "contribuição marginal" de cada atividade à coalizão, o que inclui creditar a atividade inicial por "habilitar" o contrato para as seguintes — economicamente incorreto para o domínio de construção onde cada atividade paga pelo que usa |
| A4 | Atribuição de gap ao predecessor | Economicamente incorreto: o gap existe porque o sucessor não pôde iniciar (restrição do sucessor); o predecessor já havia terminado sua obrigação |
| A5 | Custo produtivo puro sem mob/demob/gap | Subavalia custo real; `Σ partições < C_contrato` — violação do invariante de conservação |
| A6 | `eule` puro (sem extra `[interval]`) com discretização de semanas | Erro de arredondamento proporcional à granularidade; testado: erro de R$25 por atividade com grade de 0,5 semanas em T não-alinhados |
| A7 | Sweep line manual com eventos (implementação anterior do ADR-084) | Substituído por `euler()`: mesma complexidade O(n log n), menos código, fronteiras abertas/fechadas tratadas corretamente pela biblioteca |

---

## Consequências

### Positivas

| Consequência | Detalhe |
|---|---|
| `gap_pool` torna-se diagnóstico bilateral | Positivo = agenda operacional; negativo = vantagem a preservar |
| Overhead decomosto em componentes acionáveis | `overhead_ocioso` aponta gaps de escalonamento; `economia_mob` aponta perpetuação efetiva |
| Economia de paralelismo visível (Fase 3) | Com `p < 1`, `custo_produtivo_compartilhado` captura ganhos que antes eram invisíveis |
| O(n log n) exato para todo n | Elimina o limite prático de n ≤ 3 declarado no ADR-083; funciona para cadeias com n = 10+ atividades (AGIS) |
| Fronteiras abertas/fechadas corretas | `interval-sets` trata `[a,b)` vs `(a,b]` rigorosamente — sem bugs de off-by-epsilon no limite entre atividades consecutivas |
| Menos código próprio a manter | `euler()` substitui ~40 linhas de manipulação de eventos do sweep line manual |
| Axiomatização formal coerente | A atribuição causal satisfaz eficiência, responsabilidade causal e igualitarismo de mob/demob — axiomas adequados ao domínio de construção, independentes de Shapley |
| `gap_praticabilidade` permanece correto e ortogonal | Fórmula `custo_total_autonomo × (1 − η̄)` não depende da estrutura de pool |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| `_build_contratos_recurso` precisa de `T_start` e `T_end` por atividade | Disponível via `cron_lookup`; requer que RCPSP tenha sido executado antes da partição |
| Com `p < 1`, `T_start` de uma atividade depende de `T_end × p` do predecessor — ciclo potencial | DAG por definição não tem ciclos; validação de DAG já existe em `rcpsp_spec` |
| `janela - uniao_produtiva` retorna `Interval` ou `IntervalSet` dependendo do número de gaps | Helper `_iter_intervals()` normaliza os dois casos; coberto em testes unitários |
| `eule` é biblioteca pequena (dependência externa) | Risco de manutenção baixo: a dependência real é `interval-sets` (mais consolidada); `eule[interval]` pode ser substituído por implementação própria de partição de Euler em <30 linhas se necessário |
| Para `p` muito pequeno (ex.: 0.05), sobreposições longas diluem o custo entre muitas atividades — pode parecer que nenhuma "possui" o recurso | Diagnóstico de `overlap_semanas` no `CustoParticionadoItem` torna isso explícito ao planner |
| Modo MANUAL_ALLOCATION sem `rcpsp_spec` | `gap_pool_abs = 0`, decomposição não computada — comportamento correto, sem contrato de pool |
| Predecessor crítico pode mudar entre re-planejamentos | Campo `predecessor_critico_id` é recalculado a cada rebuild do contrato — sem cache |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| **Fase 1** | Correção do `gap_praticabilidade_abs = custo_total_autonomo × (1 − η̄)` em skill-08; reordenação de `fator_clima_v` antes do cálculo de gap | ✅ Implementado |
| **Fase 2A** | `CustoParticionadoItem` em canonical.py; campo `particao_por_item` em `RecursoContrato`; atribuição causal O(n) via `_compute_particao_por_tipo` para cadeias sequenciais (`p = 1`); decomposição no lever `fechar_gap_pool`; omissão do lever quando `gap_pool_abs ≤ 0` | ✅ Implementado |
| **Fase 2B** | `SegmentoAtividade` em canonical.py; campo `segmentos_atividade` em `InstanciaRecurso`; rastreio semana-a-semana por slot (`instance_week_map`) em `_build_instancias_recurso`; `_compress_to_segments` para compressão em segmentos contínuos; `_enrich_particao_overhead` para enriquecimento de `overhead_ocioso`/`custo_ocioso_imputado` via gaps reais instanciais (ADR-083/ADR-084) | ✅ Implementado |
| **Fase 3** | Adicionar `"eule[interval]"` ao `pyproject.toml`; implementar `particionar_contrato()` (D2) em skill-05 substituindo `_compute_particao_por_tipo`; preencher todos os campos de `CustoParticionadoItem` incluindo `overlap_semanas` e `predecessor_critico_id` | ✅ Implementado |
| **Fase 4** | Decomposição expandida no lever com `predecessor_critico_id` e `overlap_semanas`; atualização de testes em `test_adr076_pe_calibracao.py` para cobrir casos com `p < 1` e múltiplos predecessores | ✅ Implementado |

---

## Definition of Done

### Fase 2B (já implementado — checklist de verificação)

- [x] `SegmentoAtividade` definido em canonical.py com `activity_id`, `semana_inicio`, `semana_fim`, `machine_weeks`
- [x] `segmentos_atividade: list[SegmentoAtividade]` em `InstanciaRecurso`
- [x] `instance_week_map` rastreado em `_build_instancias_recurso` (slot→semana→activity_id)
- [x] `_compress_to_segments` comprime mapa de semanas em segmentos contínuos
- [x] `_enrich_particao_overhead` atualiza `overhead_ocioso` / `custo_ocioso_imputado` via gaps reais instanciais
- [x] Benchmark AGIS roda sem erros; `segmentos_atividade` presentes no canonical
- [x] `overhead_ocioso = 0` para AGIS é matematicamente correto (cadeias back-to-back sem gap real)

### Fase 3 ✅

- [x] `"eule[interval]"` adicionado ao `pyproject.toml`
- [x] `particionar_contrato()` (D2) implementado em skill-05, substituindo `_compute_particao_por_tipo`
- [x] Sobreposições (`p < 1`) geram `custo_produtivo_compartilhado > 0` nos itens participantes
- [x] Gaps reais identificados via `janela_contrato − uniao_produtiva` e imputados ao `_sucessor_critico` de cada gap
- [x] `predecessor_critico_id` preenchido para toda atividade com predecessores no mesmo contrato
- [x] `overlap_semanas` calculado e armazenado em `CustoParticionadoItem`
- [x] Invariante de conservação: `|Σ custo_total_particionado − C_contrato_total| < R$ 0,02`
- [x] Teste unitário `test_euler_interval_tres_atividades`: contrato com `a1=[0,3.5]`, `a2=[2.1,6.0]`, `a3=[5.0,9.3]`; verifica phi exato (tolerância 0,01)
- [x] Teste unitário `test_euler_interval_gap_imputado`: contrato com `a1=[0,3]`, `a2=[5,9]`; verifica que gap `[3,5]` é imputado integralmente a `a2`
- [x] Teste unitário `test_dag_predecessor_critico`: atividade `a3` com predecessores `a1=[0,4]` e `a2=[0,3]`; verifica que `predecessor_critico_id = 'a1'`
- [x] Teste unitário `test_iter_intervals_polimorfismo`: `_iter_intervals()` retorna lista correta para `Interval`, `IntervalSet` não-vazio e `IntervalSet` vazio

### Fase 4 ✅

- [x] Lever `fechar_gap_pool` exibe `predecessor_critico_id` e `overlap_semanas` quando disponíveis
- [x] Lever omitido quando `gap_pool_abs ≤ 0` (pool vantajoso por qualquer combinação de fonte)
- [x] Regressão: todos os testes da Fase 2 permanecem verdes com a nova implementação
- [x] Documentação inline em `particionar_contrato()` referencia ADR-084 e nomeia as três fontes de custo: produtivo exclusivo, produtivo compartilhado (overlap), ocioso (gap)