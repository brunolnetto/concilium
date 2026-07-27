# ADR-159 — Wiring Real: Popular `composicao_funcoes_mo`/`composicao_equipamentos_eq` no Pipeline de Skill-05

**Status:** Implementado
**Data:** 2026-07-27
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-156 (`composicao_funcoes_mo`), ADR-157 (`composicao_equipamentos_eq`), ADR-071 (Resource Contract Model — `_tipo_recurso_fungivel`)

---

## Contexto

### Problema

P1. `RecursoContrato.composicao_funcoes_mo`/`composicao_equipamentos_eq` (ADR-156/157) existem no schema desde ontem, mas ficam sempre `{}` — nenhum builder do pipeline real os popula. Sem esse dado, `aplicar_roster_custo_real_mo`/`_eq` nunca conseguem ativar (a verificação de cobertura sempre falha vazio) e `custo_real_instancia_semanal` (ADR-158) não tem como saber quais funções/equipamentos uma instância representa.

P2. A composição bruta (`composicao_padrao_equipe`, dict cru do catálogo: `{funcoes: [...], equipamentos: [...]}`) só existe efêmera dentro de `_derive_item_tipo_requerido`/`_tipo_recurso_fungivel` (`_pool_contrato_construcao.py`) — usada para gerar o hash `tipo_id` e descartada logo em seguida. Por essa altura do pipeline (`_build_tipo_contrato`/`_build_contrato_entry`), só sobra `tipo` (string) e `required` (int); a composição já não está mais acessível.

---

## Decisão

### D1 — Nova função `enriquecer_composicao_por_tipo` (pós-processamento, sem tocar `_tipo_recurso_fungivel`)

```python
def enriquecer_composicao_por_tipo(
    contratos: list[RecursoContrato],
    eap_items: Any,
    sched_lookup: dict,
    cpu_lookup: dict,
    prod_lookup: dict,
) -> None:
    """Popula composicao_funcoes_mo/composicao_equipamentos_eq em cada RecursoContrato
    (ADR-156/157) — mutação in-place, mesmo padrão de outros enriquecimentos pós-hoc
    de skill-05 (ex.: _aplicar_custo_instancial, _enrich_particao_overhead).

    Puramente descritivo: nenhum campo de custo é alterado. Reaproveita a mesma
    cadeia cpu->produção->composição já usada por _derive_item_tipo_requerido, e
    _tipo_recurso_fungivel (importada, não reimplementada) para recuperar o
    tipo_id de cada item — garantindo casamento byte-idêntico com o tipo_id já
    usado para construir os contratos, sem risco de divergência de hash.
    """
```

Implementação: para cada item da EAP com atividade agendada (`sched_lookup`), recupera a composição bruta (mesmos 3 lookups de `_derive_item_tipo_requerido`: `cpu_lookup[item.cpu_id] → prod_lookup[producao_id_ref] → composicao_padrao_equipe`), calcula `tipo_id = _tipo_recurso_fungivel(cpu_id, composicao)` (função já existente, importada) e, se esse `tipo_id` corresponde a um contrato ainda não enriquecido, extrai `{funcao_id: num_pessoas}`/`{equip_id: num_unidades}` da composição bruta (acesso via dict, sem exigir `ComposicaoPadraoEquipe` validado — a composição real do catálogo é sempre um dict cru nesse ponto do pipeline, nunca um objeto Pydantic hidratado) e escreve nos dois campos do contrato.

### D2 — Localização

Novo arquivo `_skill_helpers/_composicao_por_tipo.py` (não em `_pool_contrato_construcao.py`, para não misturar a lógica de construção de contrato — já grande — com este enriquecimento independente).

### D3 — Ponto de wiring: uma linha em `skill.py`, zero mudança de função existente

```python
if rcpsp_spec:
    contratos_recurso, cadeias_perpetuacao = _processar_pool_contratos(...)
    enriquecer_composicao_por_tipo(contratos_recurso, canonical_in.eap, cron_lookup, cpu_lookup, prod_lookup)
```

`canonical_in.eap`, `cron_lookup`, `cpu_lookup`, `prod_lookup` já estão todos disponíveis nesse ponto de `skill.py` (usados por chamadas vizinhas) — nenhuma assinatura de função existente muda; a nova função só é chamada, nunca substitui nada.

### D4 — Sem efeito em custo (validação de regressão zero)

Esta ADR não ativa `aplicar_roster_custo_real_mo`/`_eq` nem `custo_real_instancia_semanal` — só preenche os dois campos descritivos. Nenhum `custo_total_contrato`/`custo_unit_semanal_*` de nenhum projeto muda. A suíte completa deve reproduzir exatamente os mesmos valores de custo de antes desta ADR — só `composicao_funcoes_mo`/`composicao_equipamentos_eq` deixam de ser `{}` em contratos reais que tiverem composição de catálogo.

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Thread a composição pelo pipeline inteiro (`_derive_item_tipo_requerido` → `rcpsp_spec` → `_build_tipo_contrato` → `_build_contrato_entry`) | Rejeitado — exigiria mudar a assinatura de várias funções já testadas (`_derive_rcpsp_from_canonical`, `_setup_contratos_context`, `_build_tipo_contrato`, `_build_contrato_entry`), maior superfície de risco para o mesmo resultado |
| A2 | Reimplementar o hash de `_tipo_recurso_fungivel` dentro da nova função, em vez de importar | Rejeitado — reimplementação arrisca divergir do hash real (mesmo que sutilmente), quebrando o casamento tipo_id↔contrato; importar a função existente garante identidade bit-a-bit |
| A3 | Validar a composição como `ComposicaoPadraoEquipe` (Pydantic, `extra="forbid"`) antes de extrair | Rejeitado — dado real de catálogo pode ter campos não estritamente conformes; `_tipo_recurso_fungivel` já opera sobre o dict cru sem validação, e esta função segue a mesma convenção para não introduzir um novo modo de falha em dado de produção |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Destrava ADR-156/157/158 para uso real | `aplicar_roster_custo_real_mo`/`_eq` e `custo_real_instancia_semanal` passam a ter dado real para operar, quando chamados |
| Zero risco ao pipeline de custo existente | Só popula 2 campos descritivos; nenhuma fórmula de custo é tocada |
| Reaproveita hash já testado | `_tipo_recurso_fungivel` importada, garantindo casamento correto tipo_id↔contrato |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Ainda não ativa a substituição de custo nem o cubo por instância | Escopo desta ADR é só popular o dado — F2/F3 (aplicar roster de fato, expor timeline) continuam pendentes, decisões separadas |
| Pequena duplicação da cadeia de lookup cpu→produção→composição (já existe em `_derive_item_tipo_requerido`) | Aceitável — 3 linhas de lookup, não lógica de decisão; evita mudar assinatura de função existente (ver A1) |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 | `enriquecer_composicao_por_tipo` + wiring em `skill.py` + testes (unitários + regressão zero de custo) | ✅ |
| F2 (futura) | Ativar `aplicar_roster_custo_real_mo`/`_eq` no pipeline real (exige registro de roster — decisão de produto pendente) | ⬜ (não iniciada) |

## Definition of Done

### Fase 1 (TDD — teste antes da implementação)

- [x] `enriquecer_composicao_por_tipo` popula `composicao_funcoes_mo` corretamente a partir de `composicao_padrao_equipe.funcoes`
- [x] `enriquecer_composicao_por_tipo` popula `composicao_equipamentos_eq` corretamente a partir de `composicao_padrao_equipe.equipamentos`
- [x] Item sem correspondência de tipo_id em nenhum contrato é ignorado (sem erro)
- [x] Contrato cujo tipo nunca aparece na EAP mantém os campos vazios (`{}`)
- [x] Múltiplos contratos de tipos diferentes são enriquecidos corretamente e de forma independente
- [x] Nenhum campo de custo (`custo_unit_semanal_*`, `custo_total_contrato`) muda de valor — suíte completa reproduz os mesmos números de antes desta ADR
- [x] Suíte completa sem regressão

---

## Relacionados

- ADR-156 — Composição de Funções por Tipo de Pool (campo populado aqui)
- ADR-157 — Composição de Equipamentos por Tipo de Pool (campo populado aqui)
- ADR-158 — Custo Real por Instância (consumidor futuro deste dado)
- ADR-071 — Resource Contract Model (`_tipo_recurso_fungivel`, reaproveitada sem modificação)
