# ADR-086 — Cubo de Pool Instancial: Exploração Honesta e Descritiva da Decomposição Composicional-Temporal de Recursos

**Status:** Implementado
**Data:** 2026-05-29
**Autores:** Bruno Peixoto / Concilium
**Dependências:** ADR-085, ADR-077, ADR-073, ADR-083, ADR-084, ADR-069 (padrão de faces), ADR-021 (exploração honesta), ADR-037 (fachada MCP), ADR-018 (artefatos tipados)

---

## 1. Contexto

### 1.1 O ativo subutilizado

A linha ADR-071→085 produziu uma decomposição **rica** do pool de recursos em três eixos:

- **Composicional:** custo por componente (MO / EQ / combustível / material) — ADR-085 D2/D4.
- **Temporal:** ciclo de vida de cada instância (mobilização tardia, semanas produtivas, ociosas, *off*, desmobilização antecipada) — ADR-085 D1/D3, ADR-077.
- **Causal:** partição do custo por atividade (produtivo exclusivo/compartilhado, ocioso imputado, mob/demob, economia vs. autônomo) — ADR-083/084.

Porém essa riqueza está **espalhada e majoritariamente oculta**. Levantamento do estado atual:

| Modelo | Campos expostos hoje | Lacuna |
|---|---|---|
| `ResumoUtilizacaoContrato` | 100% (model_dump bruto) | sem interpretação |
| `InstanciaRecurso` | ~62% (campos ADR-077) | todos os campos ADR-085 (off, idle/ativo por componente, ciclo de vida) ocultos |
| `CustoParticionadoItem` | ~36% | exclusivo/compartilhado (Euler), categorial ADR-085, economia_vs_autonomo ocultos |
| `RecursoContrato` | **0%** | a entidade central do pool é invisível em relatórios |
| `ComposicaoEquipeAtividade` | **0%** | rastreabilidade atividade↔slot inexistente |
| `CadeiaPerpetuacao` | **0%** | a narrativa de perpetuação (o insight do ADR-073) ausente |

Não há nenhuma **narrativa** das economias de pool (mob/demob, idle, off, perpetuação), nem superfície de **consulta estruturada** para um agente investigar "por que esta atividade custou isso".

### 1.2 O problema de honestidade

Os números do pool são fáceis de apresentar de forma **enganosa**:

- Cobrar uma instância pelo span inteiro do contrato esconde as semanas *off* (recurso liberado).
- Reportar "custo de ociosidade" sem dizer que a MO é cobrada integral por CLT enquanto EQ tem taxa reduzida confunde o leitor.
- Atribuir custo de gap a uma atividade (causal) sem distinguir do que aquela atividade *fisicamente* consumiu mistura duas perguntas diferentes.
- Apresentar "economia de pool" sem o baseline autônomo explícito é não-falsificável.

Precisamos de uma exploração **honesta** (cada R$ rastreável à sua origem física e à sua imputação causal, com os caveats explícitos) e **descritiva** (navegável por faces, com narração que serve tanto o humano quanto o agente que consulta).

### 1.3 O que já existe e devemos seguir

- **ADR-069 (CuboAnalitico):** padrão de *faces × granularidades × measures × aggregation modes* com contrato de projeção (`rows`, `columns` com `role`, `chart_hint`, `unit_type`, `operator_meta`, `totais`) e endpoint de contrato. **Reutilizamos esse contrato de projeção.**
- **ADR-021 (PlanSpace):** princípio de exploração honesta — cada item expõe o-que + porquê + quanto + confiança + como-verificar.
- **ADR-037 (MCP):** fachada de consulta em nível de negócio para agentes.

---

## 2. Decisão

Criar o **Cubo de Pool Instancial** (`CuboPoolInstancial`): uma lente exploratória honesta sobre a
decomposição de pool, irmã do `CuboAnalitico` (ADR-069), com eixos próprios e **separação rígida
entre verdade física e imputação causal**.

### D1 — Grão atômico físico: a célula instância-semana

A fonte única de verdade **física** é a tupla (instância × semana × estado), com custo por componente:

```python
@dataclass(frozen=True)
class CelulaPoolInstancial:
    contrato_id: str
    tipo_id: str
    instancia_numero: int          # slot 1..N do pool
    semana_iso: str
    estado: Literal["prod", "idle", "off"]   # ADR-085 σ_k(j)
    atividade_id: str | None       # preenchido apenas quando estado == "prod"
    custo_mo: float                # R$ na instância-semana (MO integral em prod e idle)
    custo_eq: float                # EQ: cheio em prod, reduzido (c_idle) em idle, 0 em off
    custo_comb: float              # combustível: apenas prod
    custo_mat: float               # material: apenas prod
```

Invariante de honestidade: **toda** semana do span do contrato de **toda** instância gera exatamente
uma célula (prod, idle ou off). Off ⇒ todos os custos zero (recurso liberado, não faturado). A soma
de `custo_*` sobre todas as células de um contrato == `custo_total_contrato` (ADR-085 D3).

### D2 — Container e proveniência

```python
@dataclass(frozen=True)
class CuboPoolInstancial:
    projeto_id: str
    gerado_em: str
    celulas: tuple[CelulaPoolInstancial, ...]
    # Proveniência: ligação às estruturas causais/estruturais (não recomputadas aqui)
    particao_por_item: tuple[CustoParticionadoItem, ...]   # causal (ADR-083/084)
    cadeias: tuple[CadeiaPerpetuacao, ...]                  # estrutural (ADR-073)
    contratos: tuple[RecursoContrato, ...]                  # taxas, baseline autônomo
```

### D3 — Builder determinístico

`CuboPoolInstancialBuilder.build(canonical) → CuboPoolInstancial` materializa as células a partir de
`InstanciaRecurso` (ciclo de vida + `segmentos_atividade` + custos por componente ADR-085) e
`RecursoContrato` (rates, span). A classificação prod/idle/off **reusa** a já computada no
`_build_instancias_recurso` (não reinventa a economia idle/off). Determinístico e idempotente.

### D4 — Faces (projeções), seguindo o contrato do ADR-069

Cada face retorna `{face, granularidade, unit_type, chart_hint, columns[], rows[], operator_meta, totais, narrativa[]}`.

**Faces físicas** (derivadas das células — o que cada slot *fez*):

| Face | Pergunta honesta | Grão da linha |
|---|---|---|
| `utilizacao_temporal` | Quantos slots ativos/ociosos/off por período? | (periodo, estado, n_slots, machine_weeks) |
| `custo_estado_componente` | Quanto custou cada estado, por componente? | (estado, componente, valor_rs) |
| `instancia_ciclo_vida` | Qual o ciclo de vida e custo de cada slot? | (instancia_id, mob, demob, prod_w, idle_w, off_w, custo_mo/eq/comb/mat) |
| `atividade_instancia` | Quais slots serviram cada atividade e quando? | (atividade_id, instancia_id, semana_inicio, semana_fim, machine_weeks) |

**Faces causais/estruturais** (derivadas de `particao_por_item` / `cadeias` — a quem *imputamos*):

| Face | Pergunta honesta | Grão da linha |
|---|---|---|
| `causa_custo` | Por que esta atividade custou isso? (Euler) | (atividade_id, exclusivo, compartilhado, ocioso_imputado, mob_demob_imputado) |
| `economia_pool` | Quanto o pool economiza vs. execução autônoma? | (atividade_id, custo_autonomo, custo_instancial, economia, %) |
| `cadeia_perpetuacao` | Quais atividades compartilham frota perpetuada? | (cadeia_id, tipo, item_ids, semanas_ativas/ociosas, n_mob/demob, custo_standby) |

### D5 — Narração honesta (humano + agente)

Cada face produz, além das linhas, um campo `narrativa: list[str]` — frases descritivas geradas
deterministicamente dos próprios dados, com **caveats explícitos**. Exemplos:

- `instancia_ciclo_vida`: *"ESC-3CAT-03: mobilizada na sem. 33 (tardia, +32 sem. após início do contrato), 18 sem. produtivas, 0 ociosas, 33 sem. off (liberada). Custo R$ 4,2M — MO R$ 2,8M (integral), EQ R$ 1,4M."*
- `custo_estado_componente`: *"Ociosidade: R$ 120k — 100% mão-de-obra (cobrada integral por CLT); equipamento a taxa de locação reduzida (ρ=0,19). Combustível/material zerados (sem operação)."*
- `economia_pool`: *"eap-1_10: autônomo R$ 1,1M vs. instancial R$ 0,9M → economia R$ 200k (18%) por compartilhamento de frota com eap-1_8."*

A narração distingue **sempre** física (o que aconteceu) de causal (a quem imputamos), e nunca
apresenta "economia" sem o baseline autônomo ao lado.

### D6 — Superfícies de exposição

1. **API:** `GET /api/projects/{id}/cubo-pool/projecao?face=...&granularidade=...` + endpoint de
   contrato `/cubo-pool/projecao/contrato` (matriz de faces × granularidades × unit_types), espelhando
   o padrão ADR-069. Via `ConciliumService.get_cubo_pool_projection(...)`.
2. **MCP:** ferramenta `explorar_pool_recursos(project_id, face?, atividade_id?, instancia_id?)` na
   fachada (ADR-037), retornando linhas + narrativa para consulta do agente.
3. **Relatório (skill-09):** nova seção "Decomposição de Pool de Recursos" com as faces-chave
   (ciclo de vida, custo por estado, economia, cadeias) renderizadas em tabela + narrativa.

### D7 — Garantias de honestidade (invariantes verificáveis)

| ID | Invariante | Validação |
|---|---|---|
| H1 | Σ custo das células == Σ `custo_total_contrato` | `VAL-POOL-CUBO-SOMA` |
| H2 | Toda semana de toda instância tem exatamente 1 célula (cobertura total do span) | `VAL-POOL-CUBO-COBERTURA` |
| H3 | Células off têm todos os custos = 0 | `VAL-POOL-CUBO-OFF-ZERO` |
| H4 | Física ≠ causal: faces físicas nunca imputam idle/mob a atividade; causais sempre citam baseline | revisão de contrato |
| H5 | Sem truncamento silencioso: `top_n` aplicado marca `operator_meta.truncado` + total real | contrato de projeção |

---

## 3. Modelo de Dados

`CelulaPoolInstancial` e `CuboPoolInstancial` em `src/concilium/domain/models/cubo_pool.py` (novo
módulo, paralelo a `cubo_analitico.py`). Os modelos canônicos existentes (ADR-077/083/085) **não
mudam** — o cubo é uma projeção derivada, não uma nova fonte.

---

## 4. Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| 0 | Utilitário `week_sequence` (enumeração Snnn/ISO) + `InstanciaRecurso.segmentos_idle` (registro dos gaps-ponte no ADR-085) | ✅ Implementado |
| 1 | `cubo_pool.py`: `CelulaPoolInstancial`, `CuboPoolInstancial` + `slice`/`group_by`/projeções físicas | ✅ Implementado |
| 2 | `cubo_pool_builder.py`: `CuboPoolInstancialBuilder` + `validar_invariantes_cubo_pool` (H1/H3) | ✅ Implementado |
| 3 | `cubo_pool_projection.py`: 7 faces (físicas + causais + estruturais) + narração honesta (D5) | ✅ Implementado |
| 4 | `ConciliumService.get_cubo_pool_projection` + contrato + rotas `GET /cubo-pool/projecao[/contrato]` | ✅ Implementado |
| 5 | Ferramenta MCP `explorar_pool_recursos` (D6.2) | ✅ Implementado |
| 6 | Seção `decomposicao_pool` no relatório skill-09 (D6.3) + 16 testes + AGIS ponta-a-ponta | ✅ Implementado |

**Nota de implementação (R3 — ler, não recomputar):** a classificação idle/off já decidida pelo
ADR-085 é persistida em `InstanciaRecurso.segmentos_idle` (gaps-ponte) + `segmentos_atividade`
(prod). O builder enumera o span e marca cada semana prod/idle/off a partir desses segmentos,
distribuindo os custos por componente **já gravados** na instância (`custo_ativo_*`/`custo_idle_*`)
uniformemente pelas semanas — garantindo H1 (Σ células == `custo_total_contrato`) por construção,
sem recomputar a economia.

**Nota de implementação (baseline da face `economia_pool`):** o baseline autônomo autoritativo é
`EquipeDireta.custo_total_autonomo` (ADR-085), não o `CustoParticionadoItem.custo_total_autonomo`
(que pode estar zerado no caminho de partição). No AGIS isso revela honestamente economia ≈ −0,1%
(o pool custa ~igual ao autônomo; o ganho real foi eliminar a superestimação monolítica span×pico,
não reduzir trabalho), com a narrativa explicitando isso em vez de mascarar.

## 5. Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| R1 | Estender o `CuboAnalitico` (ADR-069) com eixos de pool | Eixos distintos (instância/estado/causa vs. categoria/BDI); acoplaria duas lentes ortogonais. Irmão é mais limpo. |
| R2 | Expor só `model_dump()` bruto dos modelos | Não é honesto nem descritivo — sem narração, sem separação física/causal, sem invariantes. |
| R3 | Recomputar a economia idle/off no builder | Duplicaria a lógica do ADR-085 (`_build_instancias_recurso`), risco de divergência. O cubo **lê**, não recomputa. |
| R4 | Atribuir idle/mob a atividades nas faces físicas | Conflundiria física com causal (viola H4). A imputação causal vive nas faces causais (ADR-083/084). |

## 6. Consequências

### Positivas
| Efeito | Descrição |
|---|---|
| Decomposição navegável | A riqueza ADR-071→085 deixa de ser beco sem saída |
| Honestidade auditável | Cada R$ rastreável (física) + imputação explícita (causal) + caveats |
| Consumo por agente | MCP + contrato de projeção permitem investigação estruturada |
| Narrativa para humano | Frases descritivas geradas dos dados, com baseline e caveats |

### Negativas / Riscos
| Risco | Mitigação |
|---|---|
| Materialização de células pode crescer (instâncias × semanas) | Determinístico e limitado (slots × span ≤ ~milhares); `top_n` nas faces |
| Mais uma superfície de API/MCP para manter | Reutiliza o contrato de projeção do ADR-069 (mesma forma de resposta) |

## 7. Definition of Done

- [ ] Fase 1–2: cubo + builder + invariantes H1–H3 com testes
- [ ] Fase 3: faces causais/estruturais + narração com caveats
- [ ] Fase 4: projeção via serviço + contrato + rotas API
- [ ] Fase 5: ferramenta MCP de exploração
- [ ] Fase 6: seção de relatório + AGIS exercitado + ≥ 25 testes

## 8. Relacionados

[[adr085-custo-instancial-composicional-temporal]] [[adr077-recurso-instancial-utilizacao]]
[[adr083-custo-particionado-pool-muitos-para-muitos]] [[adr084-custo-particionado-pool-predecessao-parcial]]
[[adr069-cubo-analitico-faces-granularidades-ux]] [[adr073-instance-matching-perpetuacao]]
