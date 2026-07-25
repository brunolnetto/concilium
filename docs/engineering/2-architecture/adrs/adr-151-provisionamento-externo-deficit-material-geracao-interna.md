# ADR-151 — Provisionamento Externo de Déficit em Materiais de Geração Interna

**Status:** Proposta
**Data:** 2026-07-25
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-139 (origem de material — `AQUISICAO_EXTERNA` × `GERACAO_INTERNA`, padrão produtor-consumidor), ADR-128 (disponibilidade de recursos consumíveis, `DisponibilidadeConsumivel`, `Escopo.logistica_consumiveis`)

---

## Contexto

### Problema

P1. **ADR-139 modela só dois modos de origem de material** — `AQUISICAO_EXTERNA` (comprado) e `GERACAO_INTERNA` (produzido internamente por uma atividade-par, ex.: escavação → aterro, padrão produtor-consumidor D3). Não existe hoje um terceiro caso, real e comum em terraplenagem: um material `GERACAO_INTERNA` cuja demanda **agregada do projeto** excede o que as atividades produtoras conseguem gerar — não por erro de catálogo/pareamento, mas porque a obra genuinamente precisa de **mais** material do que o processo produtor-consumidor natural fornece.

P2. **Achado concreto que motivou esta ADR** (investigação do benchmark AGIS, `MA-SOLO-ESCAVADO-3CAT`): a EAP tem duas atividades consumindo o mesmo material de geração interna —

| Item | CPU | Descrição | Quantitativo | Precedência |
|---|---|---|---|---|
| `eap-1_9` | `CPU-TERRA-CORPO-ATERRO-3CAT` | Construção do corpo do aterro (3ª categoria, oriundo de corte) | 981.153,5 m³ | — |
| `eap-1_10` | `CPU-TERRA-COMPAC-FINAL-ROCHA` | Compactação da camada final de aterro de rocha | 24.721,17 m³ | FS após 85% de `eap-1_9` |

A precedência (FS, threshold 85%) confirma que a "camada final" é uma **fase construtiva sequencial e distinta** — não uma redundância de cálculo sobre o mesmo material do corpo: primeiro constrói-se o volume grosso do aterro, depois aplica-se uma camada de acabamento por cima, com compactação mais criteriosa (preço unitário 2,4× maior: R$ 17,30/m³ vs R$ 7,09/m³ do corpo). A produção de 3ª categoria (via escavação, `eap-1_5`+`eap-1_6` = 981.153,5 m³) cobre exatamente o corpo do aterro sozinho — sem sobra para a camada final. O déficit (24.721,17 m³) é **estrutural e genuíno**: reflete que a obra precisa de mais rocha do que o corte disponibiliza, não um bug de pareamento (ao contrário do achado anterior, ADR-139 F5-bis, que era de fato um bug de pareamento incompleto).

P3. **O motor RCPSP hoje não tem como representar esse déficit.** `apply_replenishable_delay` (ADR-128 D2) só sabe atrasar a atividade consumidora — mas atrasar não ajuda quando o déficit é de **quantidade**, não de **timing**: por mais que se adie a compactação da camada final, a produção total (fixa) nunca alcança a demanda total (maior). O resultado hoje é `VAL-ESTOQUE-DELAY-02` (ERRO, cronograma marcado infeasible), sem nenhuma indicação de que a causa é "este material precisa ser provisionado de fora" — o usuário só vê "cronograma inviável", sem ação clara a tomar.

---

## Decisão

### D1 — Novo campo em `DisponibilidadeConsumivel`: `deficit_provisionado_externamente`

```python
@dataclass
class DisponibilidadeConsumivel:
    capacidade_armazenamento: float | None = None
    estoque_inicial: float = 0.0
    taxa_reabastecimento_max: float | None = None
    lead_time_reabastecimento_dias: float | None = None
    deficit_provisionado_externamente: float = 0.0  # NOVO
```

Semanticamente distinto de `estoque_inicial` (que representa estoque já em mãos, fisicamente presente, no início do projeto) e de `taxa_reabastecimento_max` (fluxo contínuo de reabastecimento externo, ex.: comboio de diesel): `deficit_provisionado_externamente` é uma **quantidade planejada e conhecida antecipadamente** — o valor exato do déficit estrutural entre demanda e produção interna, que o orçamentista/engenheiro de obra declara explicitamente ao montar o projeto, sabendo que essa quantidade terá que vir de fora (compra adicional de material, jazida externa, etc.) para a obra ser fisicamente executável. Tratado, no motor de projeção de estoque, como disponível desde o início (mesma posição de `estoque_inicial` na fórmula de projeção) — o efeito prático é permitir que o cronograma feche sem exigir atraso impossível.

**Por que não reaproveitar `estoque_inicial` diretamente:** mecanicamente equivalente, mas perde rastreabilidade — um `estoque_inicial` de 24.721,17 m³ para um material que normalmente começa vazio (`estoque_inicial=0.0`, convenção de `GERACAO_INTERNA` desde ADR-139 F5) pareceria um erro de dado ou estoque "surgido do nada" para quem audita depois. Um campo nomeado, com validação (AVISO) dedicada (D3), documenta a intenção.

**Por que não usar `taxa_reabastecimento_max`:** esse campo modela uma **taxa semanal contínua** (ex.: capacidade de comboio de diesel) — reaproveitá-lo para representar uma quantidade total fixa e conhecida exigiria calcular uma taxa artificial (`déficit / N semanas`), o que adicionaria material indefinidamente além do necessário se o cronograma se estender, ou insuficientemente se N for mal estimado. Uma quantidade fixa "disponível desde o início" modela a intenção real (provisionamento antecipado) com mais precisão.

### D2 — Onde a decisão de provisionar vive: `Escopo.logistica_consumiveis` (projeto), não o catálogo

Segue o precedente já estabelecido em ADR-128 D3/F5: disponibilidade de consumíveis é dado de **projeto/canteiro** (condições logísticas do sítio de obra), não do catálogo mestre. `deficit_provisionado_externamente` é adicionado a `_CAMPOS_DISPONIBILIDADE` (`replenishable_builder.py`) — herda automaticamente o mecanismo de override já existente via `Escopo.logistica_consumiveis[insumo_id]`, sem nenhuma mudança de API/schema adicional. Não é um valor auto-computado pelo sistema: é uma declaração explícita do engenheiro de obra, feita conscientemente ao identificar (como neste achado) que um material de geração interna tem demanda estrutural maior que a produção pareada.

### D3 — Visibilidade: nova validação `VAL-ESTOQUE-PROVISIONAMENTO-01` (AVISO)

Quando `deficit_provisionado_externamente > 0` para um recurso efetivamente usado no cronograma, emite um `AVISO` (não bloqueia, análogo a `VAL-ESTOQUE-CAP-01`) reportando o material e a quantidade provisionada — torna visível, no relatório do projeto, que aquele material tem uma parcela que precisa ser adquirida/providenciada além do que o processo produtor-consumidor interno cobre. Substitui o comportamento atual de simplesmente falhar (`VAL-ESTOQUE-DELAY-02`) sem explicar que a causa é um déficit estrutural conhecido e já provisionado.

### D4 — Custo do material provisionado: fora de escopo desta ADR

`GERACAO_INTERNA` tem `preco_unitario=0.0` por convenção (ADR-139 D1: custo já capturado na CPU produtora). A parcela provisionada externamente não tem uma CPU produtora cobrindo seu custo — precisaria de um preço de aquisição próprio. Esta ADR resolve a **viabilidade do cronograma** (o motor RCPSP conseguir fechar); a atribuição de custo da parcela provisionada é um problema de precificação genuíno mas distinto, deixado para uma ADR de continuação caso se mostre necessário (ex.: se o valor for material para o resultado financeiro do projeto).

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Reaproveitar `estoque_inicial` diretamente, sem campo novo | Mecanicamente idêntico, mas perde rastreabilidade/auditoria — estoque inicial não-zero num material que normalmente começa vazio parece erro de dado, não decisão deliberada (ver D1) |
| A2 | Reaproveitar `taxa_reabastecimento_max` (taxa semanal) | Modela fluxo contínuo, não quantidade fixa conhecida — adicionaria material indefinidamente ou de forma mal calibrada (ver D1) |
| A3 | Auto-computar o déficit (produção total vs consumo total) e aplicá-lo automaticamente, sem input do engenheiro | Rejeitado — mascararia bugs reais de pareamento (como o achado anterior, ADR-139 F5-bis) atrás de um "conserto" automático; a decisão de que um déficit é genuíno (não um bug) exige julgamento humano |
| A4 | Modelar como uma terceira categoria de `origem_material` (enum) | Rejeitado — a origem física do material continua sendo geração interna (corte); o que muda é que uma FRAÇÃO da demanda tem uma segunda fonte de suprimento, não a natureza do material em si |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Cronogramas com déficit estrutural genuíno deixam de falhar silenciosamente | `VAL-ESTOQUE-PROVISIONAMENTO-01` torna a causa e a quantidade explícitas, em vez de só "cronograma inviável" |
| Reaproveita infraestrutura já testada | `Escopo.logistica_consumiveis`/`_CAMPOS_DISPONIBILIDADE` já existem (ADR-128 F5); nenhuma nova API |
| Não mascara bugs de pareamento reais | Provisionamento é declaração explícita do engenheiro, não auto-correção — preserva o valor de `VAL-ESTOQUE-DELAY-02` como sinal de alerta para casos que são de fato bug |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Custo da parcela provisionada não é modelado (D4) | Documentado como fora de escopo; revisitar se o valor se mostrar material |
| Engenheiro pode provisionar um valor errado (chute, não déficit real) | Fora do controle do sistema — mesma classe de risco que qualquer dado de entrada de projeto; `VAL-ESTOQUE-PROVISIONAMENTO-01` pelo menos torna o valor visível para revisão |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 | `DisponibilidadeConsumivel.deficit_provisionado_externamente` (campo + validação) | ⬜ |
| F2 | `_project`/`project_estoque_semanal` (replenishable.py) soma o déficit ao estoque inicial | ⬜ |
| F3 | `deficit_provisionado_externamente` em `_CAMPOS_DISPONIBILIDADE` (replenishable_builder.py) — herda override via `Escopo.logistica_consumiveis` | ⬜ |
| F4 | `VAL-ESTOQUE-PROVISIONAMENTO-01` (AVISO) reportado quando o campo é usado | ⬜ |
| F5 | Aplicação concreta: `MA-SOLO-ESCAVADO-3CAT` no projeto AGIS provisionado em 24.721,17 m³; benchmark AGIS feasible; baseline de custo dos 2 testes `xfail` atualizado | ⬜ |

## Definition of Done

### Fase 1-4 (TDD — teste antes da implementação)
- [ ] `DisponibilidadeConsumivel(deficit_provisionado_externamente=X)` aceita `X >= 0`, rejeita negativo
- [ ] `_project`/`project_estoque_semanal`: estoque em t=0 inclui `estoque_inicial + deficit_provisionado_externamente`
- [ ] `_CAMPOS_DISPONIBILIDADE` inclui o novo campo — override via `logistica_consumiveis` funciona fim a fim
- [ ] `VAL-ESTOQUE-PROVISIONAMENTO-01` emitido (AVISO) quando o campo é não-zero para um recurso usado; ausente quando zero (regressão zero)

### Fase 5
- [ ] `concilium benchmark run --slug AGIS --reset`: `MA-SOLO-ESCAVADO-3CAT` deixa de aparecer no erro; `GATE Status final` deixa de ser `INVIAVEL` (ou fica `INVIAVEL` só por razão de negócio não relacionada a estoque, ex. margem)
- [ ] `tests/integration/cost/test_cost_decomposition_adr104.py`: os 2 testes `xfail` destravados, com baseline de custo atualizado e justificado (novo `custo_direto` reflete o material provisionado)
- [ ] Suíte completa (`make test`) sem regressão

---

## Relacionados

- ADR-139 — Origem de Materiais Consumíveis e Produtor-Consumidor entre Atividades (F5-ter fechou o bug de pareamento; esta ADR trata o caso de déficit genuíno, não-bug)
- ADR-128 — Disponibilidade de Recursos Consumíveis (F7 fechou o gap pool×reparo; `Escopo.logistica_consumiveis` reaproveitado aqui)
- Issue #118 — auditoria mendeslobo×rfi-r02, onde o achado do `eap-1_10` foi originalmente registrado
