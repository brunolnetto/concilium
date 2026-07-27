# ADR-160 — Cubo de Pool Real: Composição Transiente, Sem Registro Persistente de Roster

**Status:** Implementado
**Data:** 2026-07-27
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-154/155 (Roster Real MO/EQ), ADR-156/157 (Substituição Segura), ADR-158 (Custo Real por Instância), ADR-159 (Wiring de Composição)

---

## Contexto

### Problema

P1. **Correção de rumo confirmada em conversa**: a linha ADR-154→159 assumia, implicitamente, que o próximo passo seria um *registro* de roster (pessoas/ativos reais) persistido em algum lugar — catálogo mestre, projeto, ou banco. O usuário corrigiu essa direção: não quer **nenhum** registro de instância/indivíduo persistido em lugar nenhum (nem catálogo, nem `Escopo`, nem tabela própria) — quer só uma **granularidade adicional no cubo analítico de pool** (ADR-086), calculada a partir de um roster passado **transientemente** no momento de gerar o cubo, nunca salvo.

P2. Boa notícia confirmada por inspeção: `custo_real_mo_semanal`/`custo_real_eq_semanal` (ADR-154/155) e `custo_real_instancia_semanal` (ADR-158) **já satisfazem essa restrição** — são funções puras que recebem `roster: list[...]` como parâmetro simples, nunca leem de armazenamento algum. Nenhuma rework é necessária nessas três ADRs.

P3. Falta só a peça de composição: gerar, para um `RecursoContrato` real (com `composicao_funcoes_mo`/`composicao_equipamentos_eq` já populados pela ADR-159) e um roster fornecido na chamada, a timeline de custo real por instância — reaproveitando `aplicar_roster_custo_real_mo`/`_eq` (ADR-156/157) como um cálculo de "taxa sombra" (nunca persistido de volta no contrato oficial) e `custo_real_instancia_semanal` (ADR-158) para o timeline final.

---

## Decisão

### D1 — Nova função `taxa_media_eq_idle_real` (taxa ociosa real, faltava)

```python
def taxa_media_eq_idle_real(contrato: RecursoContrato, roster: list[AtivoEquipamentoReal]) -> float:
    """Taxa média real de EQ ocioso (só locação, custo_real_eq_idle_semanal, ADR-158
    D1) — mesma lógica de agregação de aplicar_roster_custo_real_eq (ADR-157),
    trocando o numerador para o idle. Não verifica cobertura — isso é
    responsabilidade do chamador (ver D3)."""
```

Localização: `domain/services/financial/roster_custo_equipamento.py`, ao lado de `custo_real_eq_idle_semanal` (mesmo módulo — trata de taxas de equipamento).

### D2 — Expor as verificações de cobertura já existentes como funções públicas

`_roster_cobre_composicao` (em `roster_custo_mo_substituicao.py` e `roster_custo_eq_substituicao.py`, ADR-156/157) perdem o underscore — viram `roster_cobre_composicao_mo`/`roster_cobre_composicao_eq`. Mudança de nome apenas (nenhuma mudança de comportamento) — necessário para que a nova função de composição (D3) possa checar cobertura sem inferir por comparação de valores (frágil).

### D3 — Nova função `gerar_timeline_real_instancias` (composição, transiente)

```python
def gerar_timeline_real_instancias(
    contrato: RecursoContrato,
    instancias: list[InstanciaRecurso],
    roster_mo: list[MembroEquipeReal],
    roster_eq: list[AtivoEquipamentoReal],
) -> dict[str, dict[str, float]] | None:
    """Gera a timeline de custo real (ADR-158) de cada instância de um contrato,
    a partir de um roster passado transientemente nesta chamada — nunca lido de
    catálogo, Escopo ou qualquer armazenamento persistente.

    Retorna None se o roster não cobrir integralmente a composição de MO OU de
    equipamento do contrato (quando declaradas) — nunca mistura número real
    parcial com calibrado; melhor não ter o dado do que ter um dado enganoso.

    Não persiste nada: `aplicar_roster_custo_real_mo`/`_eq` são usadas aqui só
    como cálculo de taxa "sombra" (contrato_real, uma cópia local) — o
    RecursoContrato oficial passado como argumento nunca é modificado nem salvo.
    """
```

Localização: `application/scheduling/cubo_pool_real.py` (novo módulo — camada de composição, ao lado de `pool_timelapse.py`/`custo_real_instancia.py`).

### D4 — Sem persistência, sem wiring ao catálogo/Escopo (reafirmado)

Esta ADR não cria nenhuma entidade de catálogo, nenhum campo em `Escopo`, nenhuma tabela. `gerar_timeline_real_instancias` é uma função pura — quem quiser usá-la fornece o roster na hora (upload pontual, parâmetro de uma tool MCP futura, script ad-hoc), e o resultado (o "cubo real") também não é persistido por esta ADR — fica para uma decisão de apresentação futura (extensão do `CuboPoolInstancial`, ADR-086) se e quando fizer sentido.

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Registro de roster no catálogo mestre (proposta anterior, corrigida nesta conversa) | Rejeitado explicitamente pelo usuário — não quer nenhum registro de indivíduo/ativo persistido em lugar nenhum |
| A2 | Retornar dado parcial (real onde cobre, calibrado onde não) misturado no mesmo timeline | Rejeitado — misturaria real com calibrado silenciosamente no mesmo número, enganoso para análise; melhor `None` explícito |
| A3 | Persistir o resultado do cubo real (cache) | Rejeitado — fora de escopo desta ADR; se algum dia for necessário, é decisão de apresentação separada, não de modelagem de custo |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Fecha o pedido correto do usuário | Granularidade real no cubo, sem nenhum registro persistente de identidade |
| Reaproveita 100% do que já existe | Nenhuma mudança em ADR-154/155/158; só uma peça nova de composição + 1 função pequena (idle) + 2 renames |
| Honestidade sobre cobertura parcial | `None` explícito em vez de número enganoso |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Ainda não há um jeito de fato de "fornecer" o roster (upload, tool MCP) | Fora de escopo — decisão de interface/produto separada, quando houver caso de uso concreto |
| Cubo real gerado não é persistido — precisa ser recalculado a cada consulta | Aceitável — mesmo princípio de `project_ocupacao_semanal` (ADR-152), que também é recomputado sob demanda |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 | `taxa_media_eq_idle_real` + renomes de cobertura pública + `gerar_timeline_real_instancias` + testes | ✅ |
| F2 (futura) | Interface de fornecimento do roster (upload/tool MCP) e/ou persistência do cubo gerado | ⬜ (não iniciada — sem caso de uso concreto ainda) |

## Definition of Done

### Fase 1 (TDD — teste antes da implementação)

- [x] `taxa_media_eq_idle_real` calcula a média correta a partir de `custo_real_eq_idle_semanal`
- [x] `gerar_timeline_real_instancias` retorna `None` quando roster de MO não cobre `composicao_funcoes_mo`
- [x] `gerar_timeline_real_instancias` retorna `None` quando roster de EQ não cobre `composicao_equipamentos_eq`
- [x] `gerar_timeline_real_instancias` retorna timeline por instância quando ambos cobrem (ou quando a composição correspondente está vazia — nada a cobrir)
- [x] `RecursoContrato` original passado como argumento nunca é mutado
- [x] Suíte completa sem regressão

---

## Relacionados

- ADR-154/155 — Roster Real de MO/Equipamento (transientes, sem mudança)
- ADR-156/157 — Substituição Segura (reaproveitadas como cálculo de taxa sombra)
- ADR-158 — Custo Real por Instância (timeline final)
- ADR-159 — Wiring de Composição (fonte de `composicao_funcoes_mo`/`composicao_equipamentos_eq` reais)
- ADR-086 — Cubo de Pool Instancial (destino conceitual futuro deste dado, não implementado aqui)
