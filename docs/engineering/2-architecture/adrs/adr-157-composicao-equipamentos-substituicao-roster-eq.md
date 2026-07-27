# ADR-157 — Composição de Equipamentos por Tipo de Pool: Substituição Segura de EQ (Espelho da ADR-156)

**Status:** Implementado
**Data:** 2026-07-27
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-156 (Composição de Funções — MO, estrutura irmã), ADR-155 (Roster Real de Equipamento), ADR-046 (RCPSP — tipos de equipe fungíveis)

---

## Contexto

### Problema

P1. ADR-156 corrigiu, para MO, o risco de `RecursoContrato.tipo_id` representar uma **equipe inteira** (hash de `_tipo_recurso_fungivel`, combinando funções + equipamentos), não uma função isolada. A mesma lacuna nunca foi corrigida para equipamento: `AtivoEquipamentoReal.tipo_id` (ADR-155) foi desenhado assumindo que `tipo_id` mapeia limpo para "um tipo de equipamento" — mas pela mesma investigação da ADR-156, um `tipo_id` como "ESC-3CAT" pode bundlar um `equip_id` específico (ex: "EQ-E0019") dentro de uma composição maior com múltiplas funções de MO. Substituir `custo_unit_semanal_eq` por um roster de "um" equipamento seria inseguro pela mesma razão que motivou a ADR-156.

P2. Esta ADR resolve exatamente o mesmo problema da ADR-156, trocando `funcao_id`/`FuncaoEquipe` por `equip_id`/`EquipamentoEquipe`. Nenhuma decisão nova de escopo — é a aplicação mecânica do mesmo padrão já validado.

---

## Decisão

### D1 — Novo campo `RecursoContrato.composicao_equipamentos_eq: dict[str, int] = {}`

```python
composicao_equipamentos_eq: dict[str, int] = Field(default_factory=dict)
# {equip_id: num_unidades} por UMA instância de equipe deste tipo (não multiplicado
# por quantidade_contratada). Default {} preserva comportamento — ver ADR-156 D1/D4.
```

### D2 — Função pura `extrair_composicao_equipamentos_eq`

```python
def extrair_composicao_equipamentos_eq(composicao: ComposicaoPadraoEquipe) -> dict[str, int]:
    """Extrai {equip_id: num_unidades} de uma ComposicaoPadraoEquipe do catálogo.

    Espelho de extrair_composicao_funcoes_mo (ADR-156 D2) para o lado de
    equipamento — mesma informação usada por _tipo_recurso_fungivel para gerar o
    hash do tipo_id, exposta aqui sem tocar o pipeline real.
    """
```

### D3 — Função pura `aplicar_roster_custo_real_eq` (com verificação de cobertura)

```python
def aplicar_roster_custo_real_eq(
    contrato: RecursoContrato,
    roster: list[AtivoEquipamentoReal],
) -> RecursoContrato:
    """Espelho de aplicar_roster_custo_real_mo (ADR-156 D3) para equipamento.

    Verificação de cobertura por equip_id: count(ativos distintos no roster com
    aquele equip_id) >= num_unidades_por_equipe × quantidade_contratada. Sem
    cobertura total, retorna o contrato inalterado (fallback seguro).

    custo_unit_semanal_eq_novo = Σ custo_real_eq_total(roster, equip_id, ...)
                                  / (quantidade_contratada × semanas_contrato)
    custo_unit_semanal_novo = cus_mo + custo_unit_semanal_eq_novo + cus_comb + cus_mat
    custo_total_contrato_novo = quantidade_contratada × custo_unit_semanal_novo
                                 × semanas_contrato
    """
```

### D4 — Escopo fechado (idêntico à ADR-156 D4)

Sem wiring ao orquestrador real, sem campo em `Escopo`, sem chamada dentro de `_tipo_recurso_fungivel`. `composicao_equipamentos_eq` fica `{}` em todo `RecursoContrato` do pipeline real hoje — zero mudança de comportamento.

---

## Alternativas Rejeitadas

Idênticas à ADR-156 (A1–A5), aplicadas ao lado de equipamento em vez de MO — não repetidas aqui por brevidade; ver ADR-156 §Alternativas Rejeitadas.

---

## Consequências

Idênticas em natureza à ADR-156 — resolve o caso geral (equipe mista) para o lado de equipamento, com o mesmo risco residual (campo vazio até um ADR de wiring futuro popular) e a mesma mitigação (fallback seguro, nunca substituição parcial).

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 | `composicao_equipamentos_eq` (campo) + `extrair_composicao_equipamentos_eq` + `aplicar_roster_custo_real_eq` + testes | ✅ |
| F2 (futura) | Wiring real — mesma decisão pendente da ADR-156 F2, agora também para equipamento | ⬜ (não iniciada) |

## Definition of Done

### Fase 1 (TDD — teste antes da implementação)

- [x] `extrair_composicao_equipamentos_eq` extrai `{equip_id: num_unidades}` corretamente, ignorando entradas sem `equip_id`
- [x] `aplicar_roster_custo_real_eq` substitui quando o roster cobre TODOS os equipamentos com headcount suficiente (`quantidade_contratada` considerado)
- [x] `aplicar_roster_custo_real_eq` NÃO substitui quando qualquer equipamento tem cobertura insuficiente
- [x] `aplicar_roster_custo_real_eq` NÃO substitui quando `composicao_equipamentos_eq` está vazio
- [x] `custo_unit_semanal_eq`/`custo_unit_semanal`/`custo_total_contrato` recalculados consistentemente (`_mo`/`_comb`/`_mat` preservados)
- [x] Contrato original não é mutado
- [x] Suíte completa sem regressão

---

## Relacionados

- ADR-156 — Composição de Funções por Tipo de Pool (estrutura espelhada por esta ADR, para MO)
- ADR-155 — Roster Real de Equipamento (`custo_real_eq_total`, reaproveitada aqui)
- ADR-046 — RCPSP Completo (fundamenta o risco de tipo_id ser equipe mista)
- ADR-158 (futura) — Custo real por instância combinando esta ADR + ADR-156 + ADR-152 (timelapse) + metodologia prod/idle/off do pool
